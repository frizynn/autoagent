"""Integration tests for leakage detection gate in OptimizationLoop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autoagent.archive import Archive, ArchiveEntry
from autoagent.benchmark import Benchmark, BenchmarkExample, ScoringResult
from autoagent.evaluation import Evaluator
from autoagent.leakage import LeakageChecker, LeakageResult
from autoagent.loop import OptimizationLoop
from autoagent.meta_agent import MetaAgent, ProposalResult
from autoagent.pipeline import PipelineRunner
from autoagent.primitives import (
    MetricsCollector,
    MockLLM,
    MockRetriever,
    PrimitivesContext,
)
from autoagent.state import StateManager


# ---------------------------------------------------------------------------
# Helpers — reuse patterns from test_loop_verification.py
# ---------------------------------------------------------------------------

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


class SequentialMockMetaAgent:
    """Returns a sequence of predetermined proposals."""

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


class MockLeakageChecker:
    """Mock LeakageChecker returning predetermined LeakageResult values."""

    def __init__(self, results: list[LeakageResult]) -> None:
        self._results = results
        self._call_count = 0

    def check(self, benchmark: Any, pipeline_source: str) -> LeakageResult:
        idx = self._call_count % len(self._results)
        self._call_count += 1
        return self._results[idx]


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
    return Evaluator(runner=PipelineRunner(allowed_root=tmp_path))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoopLeakageGate:
    """Integration tests for the leakage detection gate in the loop."""

    def test_blocked_iteration_discarded_without_evaluation(
        self, tmp_path: Path,
    ) -> None:
        """When leakage checker blocks, proposal is discarded without eval.
        Archive entry has leakage_check with blocked=True."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        proposals = [
            ProposalResult(
                proposed_source=_PIPELINE_V1, rationale="v1",
                cost_usd=0.001, success=True,
            ),
            ProposalResult(
                proposed_source=_PIPELINE_V1, rationale="v1 retry",
                cost_usd=0.001, success=True,
            ),
        ]
        meta = SequentialMockMetaAgent(proposals)

        checker = MockLeakageChecker(results=[
            LeakageResult(
                blocked=True, exact_matches=3,
                fuzzy_warnings=[], cost_usd=0.0,
            ),
            # Second iteration passes — proves loop continues after discard
            LeakageResult(
                blocked=False, exact_matches=0,
                fuzzy_warnings=[], cost_usd=0.0,
            ),
        ])

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=2,
            leakage_checker=checker,
        )

        final = loop.run()
        assert final.phase == "completed"
        assert final.current_iteration == 2

        entries = archive.query()
        assert len(entries) == 2

        # First entry: discarded due to leakage
        first = entries[0]
        assert first.decision == "discard"
        assert first.leakage_check is not None
        assert first.leakage_check["blocked"] is True
        assert first.leakage_check["exact_matches"] == 3
        assert "leakage_blocked" in first.rationale
        # Evaluation result should be the zero-score placeholder
        assert first.evaluation_result["primary_score"] == 0.0

        # Second entry: kept (leakage passed, then evaluated)
        second = entries[1]
        assert second.decision == "keep"
        assert second.leakage_check is not None
        assert second.leakage_check["blocked"] is False

    def test_warning_iteration_proceeds_to_evaluation(
        self, tmp_path: Path,
    ) -> None:
        """When leakage checker warns but doesn't block, proposal proceeds.
        Archive entry has leakage_check with warnings."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        proposals = [
            ProposalResult(
                proposed_source=_PIPELINE_V1, rationale="v1",
                cost_usd=0.001, success=True,
            ),
        ]
        meta = SequentialMockMetaAgent(proposals)

        warnings = ["Example ex1: n-gram overlap 0.45 exceeds threshold 0.30"]
        checker = MockLeakageChecker(results=[
            LeakageResult(
                blocked=False, exact_matches=0,
                fuzzy_warnings=warnings, cost_usd=0.0,
            ),
        ])

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
            leakage_checker=checker,
        )

        final = loop.run()
        assert final.phase == "completed"

        entries = archive.query()
        assert len(entries) == 1
        entry = entries[0]
        # Evaluation happened (not blocked)
        assert entry.decision == "keep"
        assert entry.leakage_check is not None
        assert entry.leakage_check["blocked"] is False
        assert entry.leakage_check["fuzzy_warnings"] == warnings

    def test_no_checker_gate_skipped(self, tmp_path: Path) -> None:
        """leakage_checker=None → no gate, loop works as before.
        Archive entries have leakage_check=None."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        proposals = [
            ProposalResult(
                proposed_source=_PIPELINE_V1, rationale="v1",
                cost_usd=0.001, success=True,
            ),
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

        entries = archive.query()
        assert len(entries) == 1
        assert entries[0].leakage_check is None

    def test_leakage_cost_tracked_in_total_cost(
        self, tmp_path: Path,
    ) -> None:
        """LeakageResult.cost_usd is accumulated into total_cost_usd."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        proposals = [
            ProposalResult(
                proposed_source=_PIPELINE_V1, rationale="v1",
                cost_usd=0.001, success=True,
            ),
        ]
        meta = SequentialMockMetaAgent(proposals)

        leakage_cost = 0.003
        checker = MockLeakageChecker(results=[
            LeakageResult(
                blocked=False, exact_matches=0,
                fuzzy_warnings=[], cost_usd=leakage_cost,
            ),
        ])

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
            leakage_checker=checker,
        )

        final = loop.run()
        # Total cost should include proposal cost + leakage cost
        assert final.total_cost_usd >= 0.001 + leakage_cost

    def test_leakage_check_persisted_in_json(self, tmp_path: Path) -> None:
        """leakage_check dict appears in archive JSON files on disk."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        proposals = [
            ProposalResult(
                proposed_source=_PIPELINE_V1, rationale="v1",
                cost_usd=0.001, success=True,
            ),
        ]
        meta = SequentialMockMetaAgent(proposals)

        checker = MockLeakageChecker(results=[
            LeakageResult(
                blocked=False, exact_matches=0,
                fuzzy_warnings=["warn1"], cost_usd=0.0,
            ),
        ])

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
            leakage_checker=checker,
        )

        loop.run()

        # Read raw JSON from disk
        json_files = list(sm.archive_dir.glob("*-keep.json"))
        assert len(json_files) == 1
        data = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert "leakage_check" in data
        assert data["leakage_check"]["blocked"] is False
        assert data["leakage_check"]["fuzzy_warnings"] == ["warn1"]
