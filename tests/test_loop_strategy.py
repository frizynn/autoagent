"""Integration tests for strategy signal wiring in OptimizationLoop.

Verifies that:
- analyze_strategy() is called with recent archive entries during each iteration
- Strategy signals flow from detector → propose()
- Archive entries get mutation_type set after evaluation
- Strategy detection works alongside archive summaries
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

import pytest

from autoagent.archive import Archive, ArchiveEntry
from autoagent.benchmark import Benchmark
from autoagent.evaluation import Evaluator
from autoagent.loop import OptimizationLoop
from autoagent.meta_agent import MetaAgent, ProposalResult
from autoagent.primitives import (
    MetricsCollector,
    MockLLM,
    MockRetriever,
    PrimitivesContext,
)
from autoagent.pipeline import PipelineRunner
from autoagent.state import StateManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PIPELINE_V1 = '''\
def run(input_data, primitives=None):
    """V1 — baseline."""
    return {"echo": input_data}
'''

_PIPELINE_V2 = '''\
def run(input_data, primitives=None):
    """V2 — uppercase."""
    return {"echo": str(input_data).upper()}
'''


class CapturingMockMetaAgent:
    """Mock meta-agent that captures propose() arguments."""

    def __init__(self, proposals: list[ProposalResult]) -> None:
        self._proposals = proposals
        self._call_count = 0
        self.calls: list[dict[str, Any]] = []

    @property
    def llm(self):
        return MockLLM(collector=MetricsCollector())

    def propose(
        self,
        current_source: str,
        kept_entries: list[ArchiveEntry] | None = None,
        discarded_entries: list[ArchiveEntry] | None = None,
        benchmark_description: str = "",
        archive_summary: str = "",
        strategy_signals: str = "",
    ) -> ProposalResult:
        self.calls.append({
            "current_source": current_source,
            "kept_entries": kept_entries or [],
            "discarded_entries": discarded_entries or [],
            "archive_summary": archive_summary,
            "strategy_signals": strategy_signals,
        })
        idx = self._call_count % len(self._proposals)
        self._call_count += 1
        return self._proposals[idx]


def _make_benchmark(tmp_path: Path) -> Benchmark:
    """Create a simple benchmark where exact_match on 'hello' succeeds."""
    data = [
        {"input": "hello", "expected": "{'echo': 'hello'}", "id": "ex1"},
    ]
    bf = tmp_path / "bench.json"
    bf.write_text(json.dumps(data), encoding="utf-8")
    return Benchmark.from_file(bf, scoring_function="exact_match")


def _make_evaluator(tmp_path: Path) -> Evaluator:
    return Evaluator(runner=PipelineRunner(allowed_root=tmp_path))


def _init_project(tmp_path: Path) -> StateManager:
    sm = StateManager(tmp_path)
    sm.init_project()
    return sm


def _make_primitives() -> PrimitivesContext:
    collector = MetricsCollector()
    return PrimitivesContext(
        llm=MockLLM(collector=collector),
        retriever=MockRetriever(collector=collector),
        collector=collector,
    )


def _make_loop(
    tmp_path: Path,
    meta_agent: Any,
    max_iterations: int = 2,
) -> tuple[OptimizationLoop, StateManager]:
    sm = _init_project(tmp_path)
    benchmark = _make_benchmark(tmp_path)
    archive = Archive(sm.archive_dir)
    evaluator = _make_evaluator(tmp_path)

    loop = OptimizationLoop(
        state_manager=sm,
        archive=archive,
        evaluator=evaluator,
        meta_agent=meta_agent,
        benchmark=benchmark,
        primitives_factory=_make_primitives,
        max_iterations=max_iterations,
    )
    return loop, sm


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoopStrategyDetector:
    """Verify analyze_strategy() is called during loop iteration."""

    def test_loop_calls_strategy_detector(self, tmp_path: Path) -> None:
        """analyze_strategy is called with recent entries during each iteration."""
        proposals = [
            ProposalResult(
                proposed_source=_PIPELINE_V1,
                rationale="keep baseline",
                cost_usd=0.0,
                success=True,
            ),
        ]
        meta_agent = CapturingMockMetaAgent(proposals)
        loop, sm = _make_loop(tmp_path, meta_agent, max_iterations=2)

        with patch("autoagent.loop.analyze_strategy", wraps=lambda entries: "") as mock_analyze:
            loop.run()
            assert mock_analyze.call_count >= 2
            # Each call receives a list of ArchiveEntry objects
            for call in mock_analyze.call_args_list:
                entries = call[0][0]
                assert isinstance(entries, list)

    def test_loop_passes_strategy_signals_to_propose(self, tmp_path: Path) -> None:
        """Strategy signals from detector flow through to propose()."""
        proposals = [
            ProposalResult(
                proposed_source=_PIPELINE_V1,
                rationale="keep baseline",
                cost_usd=0.0,
                success=True,
            ),
        ]
        meta_agent = CapturingMockMetaAgent(proposals)
        loop, sm = _make_loop(tmp_path, meta_agent, max_iterations=2)

        fake_signal = "Scores plateaued for 5 iterations — try structural changes."

        with patch("autoagent.loop.analyze_strategy", return_value=fake_signal):
            loop.run()

        # Every propose() call should have received the strategy signal
        assert len(meta_agent.calls) >= 2
        for call in meta_agent.calls:
            assert call["strategy_signals"] == fake_signal

    def test_loop_sets_mutation_type_on_archive_entry(self, tmp_path: Path) -> None:
        """Archive entries have mutation_type set after evaluation."""
        proposals = [
            ProposalResult(
                proposed_source=_PIPELINE_V1,
                rationale="keep baseline",
                cost_usd=0.0,
                success=True,
            ),
            ProposalResult(
                proposed_source=_PIPELINE_V2,
                rationale="structural change",
                cost_usd=0.0,
                success=True,
            ),
        ]
        meta_agent = CapturingMockMetaAgent(proposals)
        loop, sm = _make_loop(tmp_path, meta_agent, max_iterations=2)

        loop.run()

        archive = Archive(sm.archive_dir)
        entries = archive.query()
        assert len(entries) >= 2
        for entry in entries:
            assert entry.mutation_type is not None
            assert entry.mutation_type in ("structural", "parametric")

    def test_loop_strategy_with_summary(self, tmp_path: Path) -> None:
        """Strategy detection works alongside archive summaries (not conflicting)."""
        proposals = [
            ProposalResult(
                proposed_source=_PIPELINE_V1,
                rationale="keep baseline",
                cost_usd=0.0,
                success=True,
            ),
        ]
        meta_agent = CapturingMockMetaAgent(proposals)
        loop, sm = _make_loop(tmp_path, meta_agent, max_iterations=3)

        # Pre-populate archive with entries to trigger summary threshold
        # (default threshold is 10, but we'll set a low one)
        loop.summary_threshold = 1

        fake_signal = "Consider structural exploration."

        with patch("autoagent.loop.analyze_strategy", return_value=fake_signal):
            loop.run()

        # Strategy signals should still be passed even when summaries are active
        for call in meta_agent.calls:
            assert call["strategy_signals"] == fake_signal

    def test_loop_strategy_detector_failure_graceful(self, tmp_path: Path) -> None:
        """If analyze_strategy raises, loop continues with empty signals."""
        proposals = [
            ProposalResult(
                proposed_source=_PIPELINE_V1,
                rationale="keep baseline",
                cost_usd=0.0,
                success=True,
            ),
        ]
        meta_agent = CapturingMockMetaAgent(proposals)
        loop, sm = _make_loop(tmp_path, meta_agent, max_iterations=1)

        with patch("autoagent.loop.analyze_strategy", side_effect=RuntimeError("boom")):
            # Should not raise
            state = loop.run()

        assert state.phase == "completed"
        # Strategy signals should be empty due to error
        for call in meta_agent.calls:
            assert call["strategy_signals"] == ""
