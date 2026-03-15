"""Integration tests for OptimizationLoop — proves ≥3 autonomous iterations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autoagent.archive import Archive, ArchiveEntry
from autoagent.benchmark import Benchmark, BenchmarkExample, ScoringResult
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
# Helpers — deterministic mock meta-agent
# ---------------------------------------------------------------------------

# Pipeline source templates with varying quality
_PIPELINE_V1 = '''\
def run(input_data, primitives=None):
    """V1 — baseline echo."""
    return {"echo": input_data}
'''

_PIPELINE_V2 = '''\
def run(input_data, primitives=None):
    """V2 — uppercase."""
    return {"echo": str(input_data).upper()}
'''

_PIPELINE_V3 = '''\
def run(input_data, primitives=None):
    """V3 — lower (worse for exact match)."""
    return {"echo": str(input_data).lower()}
'''

_PIPELINE_BAD = "this is not valid python {{{"


class SequentialMockMetaAgent:
    """Returns a sequence of predetermined proposals.

    Cycles through the sequence if iterations exceed len(proposals).
    """

    def __init__(self, proposals: list[ProposalResult]) -> None:
        self._proposals = proposals
        self._call_count = 0

    def propose(
        self,
        current_source: str,
        kept_entries: list[ArchiveEntry] | None = None,
        discarded_entries: list[ArchiveEntry] | None = None,
        benchmark_description: str = "",
    ) -> ProposalResult:
        idx = self._call_count % len(self._proposals)
        self._call_count += 1
        return self._proposals[idx]


def _make_benchmark(tmp_path: Path) -> Benchmark:
    """Create a simple benchmark where exact_match on 'hello' succeeds."""
    data = [
        {"input": "hello", "expected": "{'echo': 'hello'}", "id": "ex1"},
        {"input": "world", "expected": "{'echo': 'world'}", "id": "ex2"},
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
    """Create an evaluator with allowed_root set to tmp_path."""
    return Evaluator(runner=PipelineRunner(allowed_root=tmp_path))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOptimizationLoop:
    """Integration tests for the full propose→evaluate→keep/discard cycle."""

    def test_three_iterations_complete(self, tmp_path: Path) -> None:
        """≥3 iterations complete, archive has ≥3 entries, state matches."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
            ProposalResult(proposed_source=_PIPELINE_V2, rationale="v2", cost_usd=0.002, success=True),
            ProposalResult(proposed_source=_PIPELINE_V3, rationale="v3", cost_usd=0.001, success=True),
        ]
        meta = SequentialMockMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=3,
        )

        final = loop.run()

        assert final.current_iteration == 3
        assert len(archive) == 3
        assert final.phase == "completed"

    def test_keep_discard_decisions(self, tmp_path: Path) -> None:
        """Keep/discard decisions are based on primary_score comparison."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        # V1 matches exactly → score ~1.0 for exact_match
        # V2 uppercases → won't match expected → score 0.0
        # V3 lowercases → matches for lowercase inputs → partial
        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
            ProposalResult(proposed_source=_PIPELINE_V2, rationale="v2", cost_usd=0.002, success=True),
            ProposalResult(proposed_source=_PIPELINE_V3, rationale="v3", cost_usd=0.001, success=True),
        ]
        meta = SequentialMockMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=3,
        )

        loop.run()

        entries = archive.query()
        assert len(entries) == 3

        # First iteration is always kept
        assert entries[0].decision == "keep"
        # Second (uppercase, worse) should be discarded
        assert entries[1].decision == "discard"
        # Third (lowercase) — depends on score vs V1; V1 had score 1.0,
        # V3 lowercases so "hello" stays "hello" but wrapping differs
        # In any case, we have at least one keep and one discard
        decisions = [e.decision for e in entries]
        assert "keep" in decisions
        assert "discard" in decisions

    def test_state_persistence(self, tmp_path: Path) -> None:
        """State persisted correctly: iteration, best_iteration_id, phase."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
        ]
        meta = SequentialMockMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=3,
        )

        loop.run()

        # Read state from disk — verify persistence
        state = sm.read_state()
        assert state.current_iteration == 3
        assert state.best_iteration_id is not None
        assert state.phase == "completed"
        assert state.updated_at != ""

    def test_meta_agent_failure_discard(self, tmp_path: Path) -> None:
        """MetaAgent failure (invalid source) → discard entry with error rationale."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
            ProposalResult(proposed_source="", rationale="", cost_usd=0.001, success=False, error="syntax error: invalid"),
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1 again", cost_usd=0.001, success=True),
        ]
        meta = SequentialMockMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=3,
        )

        final = loop.run()

        # Loop didn't halt — all 3 iterations completed
        assert final.current_iteration == 3
        assert len(archive) == 3

        entries = archive.query()
        # Second entry is the failed proposal
        failed_entry = entries[1]
        assert failed_entry.decision == "discard"
        assert "proposal_error" in failed_entry.rationale

    def test_first_iteration_always_kept(self, tmp_path: Path) -> None:
        """First iteration is always kept (baseline establishment)."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        # Even a low-scoring pipeline should be kept as first
        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V2, rationale="v2 first", cost_usd=0.001, success=True),
        ]
        meta = SequentialMockMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
        )

        loop.run()

        entries = archive.query()
        assert len(entries) == 1
        assert entries[0].decision == "keep"

    def test_total_cost_accumulates(self, tmp_path: Path) -> None:
        """total_cost_usd accumulates meta-agent + evaluation costs."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.01, success=True),
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.02, success=True),
        ]
        meta = SequentialMockMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=2,
        )

        loop.run()

        state = sm.read_state()
        # Should be > 0 and include both meta-agent costs
        assert state.total_cost_usd >= 0.03  # at least the proposal costs

    def test_pipeline_on_disk_reflects_best(self, tmp_path: Path) -> None:
        """Pipeline on disk reflects current best after each iteration."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        # V1 matches → keep, V2 uppercase → discard
        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
            ProposalResult(proposed_source=_PIPELINE_V2, rationale="v2", cost_usd=0.001, success=True),
        ]
        meta = SequentialMockMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=2,
        )

        loop.run()

        # After discard, disk should have the V1 source (the kept one), not V2
        on_disk = sm.pipeline_path.read_text(encoding="utf-8")
        assert "V1" in on_disk
        assert "V2" not in on_disk

    def test_phase_transitions(self, tmp_path: Path) -> None:
        """Phase transitions: initialized → running → completed."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        # Verify initial phase
        initial_state = sm.read_state()
        assert initial_state.phase == "initialized"

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
        ]
        meta = SequentialMockMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
        )

        final = loop.run()
        assert final.phase == "completed"

    def test_archive_entries_have_required_fields(self, tmp_path: Path) -> None:
        """Each archive entry has metrics, diff, rationale, and decision."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1 change", cost_usd=0.001, success=True),
            ProposalResult(proposed_source=_PIPELINE_V2, rationale="v2 change", cost_usd=0.002, success=True),
            ProposalResult(proposed_source=_PIPELINE_V3, rationale="v3 change", cost_usd=0.001, success=True),
        ]
        meta = SequentialMockMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=3,
        )

        loop.run()

        for entry in archive.query():
            assert entry.decision in ("keep", "discard")
            assert entry.rationale != ""
            assert isinstance(entry.evaluation_result, dict)
            assert "primary_score" in entry.evaluation_result
            assert entry.iteration_id > 0

    def test_lock_released_on_exception(self, tmp_path: Path) -> None:
        """Lock is released even if an unexpected error occurs."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        class ExplodingMetaAgent:
            def propose(self, *args, **kwargs):
                raise RuntimeError("boom")

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=ExplodingMetaAgent(),
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
        )

        with pytest.raises(RuntimeError, match="boom"):
            loop.run()

        # Lock should be released
        assert not sm.lock_path.exists()
