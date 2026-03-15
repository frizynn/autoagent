"""Integration tests for OptimizationLoop summarizer integration.

Proves: threshold switching, summary caching, cost tracking,
regeneration interval, and graceful fallback on failure.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autoagent.archive import Archive, ArchiveEntry
from autoagent.benchmark import Benchmark
from autoagent.evaluation import EvaluationResult, Evaluator
from autoagent.loop import OptimizationLoop
from autoagent.meta_agent import MetaAgent, ProposalResult
from autoagent.primitives import (
    LLMProtocol,
    MetricsCollector,
    MockLLM,
    MockRetriever,
    PrimitivesContext,
)
from autoagent.pipeline import PipelineRunner
from autoagent.state import StateManager


from autoagent.types import MetricsSnapshot as _MetricsSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PIPELINE_V1 = '''\
def run(input_data, primitives=None):
    """V1 — baseline echo."""
    return {"echo": input_data}
'''


class RecordingMetaAgent:
    """Mock meta-agent that records what was passed to propose()."""

    def __init__(self, proposals: list[ProposalResult]) -> None:
        self._proposals = proposals
        self._call_count = 0
        self.calls: list[dict[str, Any]] = []

    @property
    def llm(self) -> MockLLM:
        """Expose a mock LLM so the loop can use it for summarization."""
        return MockLLM(collector=MetricsCollector())

    def propose(
        self,
        current_source: str,
        kept_entries: list[ArchiveEntry] | None = None,
        discarded_entries: list[ArchiveEntry] | None = None,
        benchmark_description: str = "",
        archive_summary: str = "",
    ) -> ProposalResult:
        self.calls.append({
            "current_source": current_source,
            "kept_entries": kept_entries or [],
            "discarded_entries": discarded_entries or [],
            "archive_summary": archive_summary,
        })
        idx = self._call_count % len(self._proposals)
        self._call_count += 1
        return self._proposals[idx]


class CostTrackingLLM:
    """LLM that returns a fixed summary and tracks cost via collector."""

    def __init__(self, response: str = "## Top-K Results\nIteration 1 scored 1.0",
                 cost_per_call: float = 0.005) -> None:
        self.collector = MetricsCollector()
        self._response = response
        self._cost_per_call = cost_per_call
        self.call_count = 0

    def complete(self, prompt: str, **kwargs: Any) -> str:
        self.call_count += 1
        self.collector.record(_MetricsSnapshot(
            latency_ms=10.0,
            tokens_in=100,
            tokens_out=50,
            cost_usd=self._cost_per_call,
        ))
        return self._response


class FailingLLM:
    """LLM that returns empty string to simulate failure."""

    def __init__(self) -> None:
        self.collector = MetricsCollector()

    def complete(self, prompt: str, **kwargs: Any) -> str:
        return ""


class ExplodingLLM:
    """LLM that raises an exception."""

    def __init__(self) -> None:
        self.collector = MetricsCollector()

    def complete(self, prompt: str, **kwargs: Any) -> str:
        raise RuntimeError("LLM exploded")


def _make_benchmark(tmp_path: Path) -> Benchmark:
    data = [
        {"input": "hello", "expected": "{'echo': 'hello'}", "id": "ex1"},
    ]
    bf = tmp_path / "bench.json"
    bf.write_text(json.dumps(data), encoding="utf-8")
    return Benchmark.from_file(bf, scoring_function="exact_match")


def _make_primitives_factory():
    def factory() -> PrimitivesContext:
        c = MetricsCollector()
        return PrimitivesContext(
            llm=MockLLM(collector=c),
            retriever=MockRetriever(collector=c),
            collector=c,
        )
    return factory


def _init_project(tmp_path: Path) -> StateManager:
    sm = StateManager(tmp_path)
    sm.init_project()
    return sm


def _make_evaluator(tmp_path: Path) -> Evaluator:
    return Evaluator(runner=PipelineRunner(allowed_root=tmp_path))


def _prepopulate_archive(archive: Archive, count: int) -> None:
    """Add `count` dummy entries to the archive to push past threshold."""
    for i in range(count):
        decision = "keep" if i % 3 == 0 else "discard"
        archive.add(
            pipeline_source=_PIPELINE_V1,
            evaluation_result=EvaluationResult(
                primary_score=0.5 + (i * 0.01),
                per_example_results=[],
                metrics=None,
                benchmark_id="bench",
                duration_ms=10.0,
                num_examples=1,
                num_failures=0,
            ),
            rationale=f"iteration {i + 1}",
            decision=decision,
            parent_iteration_id=i if i > 0 else None,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoopSummarizerIntegration:
    """Integration tests for archive summarization in the optimization loop."""

    def test_below_threshold_uses_raw_entries(self, tmp_path: Path) -> None:
        """When archive < threshold, raw entries are passed (no summary)."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
        ]
        meta = RecordingMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=2,
            summary_threshold=50,  # Way above what we'll produce
        )

        loop.run()

        # Every call should have empty archive_summary
        for call in meta.calls:
            assert call["archive_summary"] == ""

    def test_above_threshold_uses_summary(self, tmp_path: Path) -> None:
        """When archive >= threshold, summary is generated and passed to propose."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        # Pre-populate archive past threshold
        _prepopulate_archive(archive, 25)

        summary_llm = CostTrackingLLM(response="## Top-K Results\nBest iteration scored 0.9")

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
        ]
        meta = RecordingMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
            summary_threshold=20,
            summarizer_llm=summary_llm,
        )

        loop.run()

        # The propose call should have received an archive_summary
        assert len(meta.calls) == 1
        assert "Top-K Results" in meta.calls[0]["archive_summary"]
        # When summary is active, raw entries should be empty
        assert meta.calls[0]["kept_entries"] == []
        assert meta.calls[0]["discarded_entries"] == []

    def test_summarizer_cost_tracked_in_budget(self, tmp_path: Path) -> None:
        """Summarizer cost is added to total_cost and checked against budget."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        _prepopulate_archive(archive, 25)

        cost_per_summary = 0.005
        summary_llm = CostTrackingLLM(cost_per_call=cost_per_summary)

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
        ]
        meta = RecordingMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
            summary_threshold=20,
            summarizer_llm=summary_llm,
        )

        final = loop.run()

        # total_cost should include the summarizer cost
        assert final.total_cost_usd >= cost_per_summary

    def test_summary_cached_not_regenerated_every_iteration(self, tmp_path: Path) -> None:
        """Summary is cached and not regenerated on every iteration."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        _prepopulate_archive(archive, 25)

        summary_llm = CostTrackingLLM()

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
        ]
        meta = RecordingMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=3,
            summary_threshold=20,
            summary_interval=10,  # Won't trigger regen with just 3 new entries
            summarizer_llm=summary_llm,
        )

        loop.run()

        # Summarizer LLM should be called only once (initial generation),
        # not on every iteration
        assert summary_llm.call_count == 1
        # But all 3 propose calls should have the cached summary
        assert len(meta.calls) == 3
        for call in meta.calls:
            assert call["archive_summary"] != ""

    def test_summary_regenerated_at_interval(self, tmp_path: Path) -> None:
        """Summary is regenerated when archive grows by summary_interval entries."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        # Pre-populate just at threshold
        _prepopulate_archive(archive, 20)

        summary_llm = CostTrackingLLM()

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
        ]
        meta = RecordingMetaAgent(proposals)

        # summary_interval=2 means regenerate after 2 new entries added
        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=5,
            summary_threshold=20,
            summary_interval=2,
            summarizer_llm=summary_llm,
        )

        loop.run()

        # Initial generation at iteration 1 (archive=20, threshold=20)
        # After iteration 1: archive=21, cached at 20, delta=1 < 2 → no regen
        # After iteration 2: archive=22, cached at 20, delta=2 >= 2 → regen
        # After iteration 3: archive=23, cached at 22, delta=1 < 2 → no regen
        # After iteration 4: archive=24, cached at 22, delta=2 >= 2 → regen
        # So: 3 calls total (initial + 2 regens)
        assert summary_llm.call_count == 3

    def test_fallback_on_empty_summary(self, tmp_path: Path) -> None:
        """If summarizer returns empty text, loop falls back to raw entries."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        _prepopulate_archive(archive, 25)

        failing_llm = FailingLLM()

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
        ]
        meta = RecordingMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
            summary_threshold=20,
            summarizer_llm=failing_llm,
        )

        final = loop.run()

        # Should complete without error
        assert final.phase == "completed"
        # Raw entries should have been passed (fallback)
        assert meta.calls[0]["archive_summary"] == ""

    def test_fallback_on_summarizer_exception(self, tmp_path: Path) -> None:
        """If summarizer raises an exception, loop continues with raw entries."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        _prepopulate_archive(archive, 25)

        exploding_llm = ExplodingLLM()

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
        ]
        meta = RecordingMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
            summary_threshold=20,
            summarizer_llm=exploding_llm,
        )

        final = loop.run()

        # Should complete without error — fallback to raw entries
        assert final.phase == "completed"
        assert meta.calls[0]["archive_summary"] == ""

    def test_summarizer_cost_counted_against_budget(self, tmp_path: Path) -> None:
        """Summarizer cost pushes total past budget → loop pauses."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        _prepopulate_archive(archive, 25)

        # Summarizer costs $0.05, budget is $0.04 — after summarization
        # the total_cost will exceed budget, but the iteration still runs
        # (budget is checked at the TOP of the next iteration)
        summary_llm = CostTrackingLLM(cost_per_call=0.05)

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
        ]
        meta = RecordingMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            budget_usd=0.04,
            summary_threshold=20,
            summarizer_llm=summary_llm,
        )

        final = loop.run()

        # After first iteration: summarizer($0.05) + proposal($0.001) > budget($0.04)
        # Budget check at top of second iteration should pause
        assert final.phase == "paused"
        assert final.total_cost_usd >= 0.05
