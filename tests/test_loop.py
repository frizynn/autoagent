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
        archive_summary: str = "",
        strategy_signals: str = "",
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

    # ------------------------------------------------------------------
    # Budget & Resume tests
    # ------------------------------------------------------------------

    def test_budget_pause(self, tmp_path: Path) -> None:
        """Loop pauses when total cost exceeds budget."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        # Each proposal costs $0.01, budget is $0.02 → should run 2 then pause
        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.01, success=True),
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.01, success=True),
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.01, success=True),
        ]
        meta = SequentialMockMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            budget_usd=0.02,
        )

        final = loop.run()

        assert final.phase == "paused"
        assert final.current_iteration == 2
        assert final.total_cost_usd >= 0.02

    def test_budget_estimation_pause(self, tmp_path: Path) -> None:
        """Loop pauses before starting an iteration that would exceed budget."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        # Each proposal costs $0.01, budget $0.025 — after 2 iterations
        # cost is ~$0.02, avg ~$0.01, estimated next total ~$0.03 > $0.025
        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.01, success=True),
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.01, success=True),
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.01, success=True),
        ]
        meta = SequentialMockMetaAgent(proposals)

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            budget_usd=0.025,
        )

        final = loop.run()

        assert final.phase == "paused"
        assert final.current_iteration == 2

    def test_resume_from_state(self, tmp_path: Path) -> None:
        """Run 2 iterations, create new loop, run 2 more → iteration=4."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
        ]
        meta = SequentialMockMetaAgent(proposals)

        loop1 = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=2,
        )
        loop1.run()

        state_after_1 = sm.read_state()
        assert state_after_1.current_iteration == 2

        # Create a new loop with the same state/archive
        meta2 = SequentialMockMetaAgent(proposals)
        loop2 = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta2,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=2,
        )
        final = loop2.run()

        assert final.current_iteration == 4
        assert len(archive) == 4

    def test_resume_reconstructs_best_score(self, tmp_path: Path) -> None:
        """After resume, keep/discard decisions reflect archive history."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        # V1 scores high (exact match), run 1 iteration to establish best
        proposals1 = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
        ]
        meta1 = SequentialMockMetaAgent(proposals1)

        loop1 = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta1,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
        )
        loop1.run()

        # V1 had score ~1.0 (exact match). Resume with V2 (uppercase, score 0).
        # If best_score is reconstructed, V2 should be discarded.
        proposals2 = [
            ProposalResult(proposed_source=_PIPELINE_V2, rationale="v2", cost_usd=0.001, success=True),
        ]
        meta2 = SequentialMockMetaAgent(proposals2)

        loop2 = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta2,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
        )
        loop2.run()

        entries = archive.query()
        assert len(entries) == 2
        assert entries[0].decision == "keep"    # V1
        assert entries[1].decision == "discard"  # V2 (worse than reconstructed best)

    def test_resume_restores_pipeline_from_archive(self, tmp_path: Path) -> None:
        """After crash with stale source on disk, resume restores from archive."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        # Run 1 iteration to establish best (V1)
        proposals1 = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
        ]
        meta1 = SequentialMockMetaAgent(proposals1)

        loop1 = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta1,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
        )
        loop1.run()

        # Simulate crash: write stale/wrong source to pipeline.py
        sm.pipeline_path.write_text("# STALE CRASH ARTIFACT", encoding="utf-8")

        # Resume — should restore V1 from archive
        proposals2 = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1 again", cost_usd=0.001, success=True),
        ]
        meta2 = SequentialMockMetaAgent(proposals2)

        loop2 = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta2,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
        )
        loop2.run()

        # Pipeline on disk should NOT have the stale content
        on_disk = sm.pipeline_path.read_text(encoding="utf-8")
        assert "STALE" not in on_disk
        assert "V1" in on_disk

    def test_resume_from_paused_phase(self, tmp_path: Path) -> None:
        """Phase='paused' → running on resume with higher budget."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        proposals = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.01, success=True),
        ]
        meta = SequentialMockMetaAgent(proposals)

        # Budget $0.01 — will run 1 then pause
        loop1 = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            budget_usd=0.01,
        )
        state1 = loop1.run()
        assert state1.phase == "paused"

        # Resume with higher budget
        meta2 = SequentialMockMetaAgent(proposals)
        loop2 = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta2,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            budget_usd=1.00,
            max_iterations=2,
        )
        state2 = loop2.run()

        # Should have continued past the paused state
        assert state2.phase == "completed"
        assert state2.current_iteration > state1.current_iteration

    def test_resume_all_discards(self, tmp_path: Path) -> None:
        """Resume when all archive entries are discards → best_score stays None."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        # Run 1 iteration with a failing proposal → discard only
        proposals1 = [
            ProposalResult(proposed_source="", rationale="", cost_usd=0.001, success=False, error="bad"),
        ]
        meta1 = SequentialMockMetaAgent(proposals1)

        loop1 = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta1,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
        )
        loop1.run()

        # All entries are discards
        assert all(e.decision == "discard" for e in archive.query())

        # Resume — V1 should be kept as first good eval
        proposals2 = [
            ProposalResult(proposed_source=_PIPELINE_V1, rationale="v1", cost_usd=0.001, success=True),
        ]
        meta2 = SequentialMockMetaAgent(proposals2)

        loop2 = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta2,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
        )
        loop2.run()

        entries = archive.query()
        assert len(entries) == 2
        # The resumed iteration should be kept (first good eval, best_score was None)
        assert entries[1].decision == "keep"
