"""Integration tests for TLA+ verification gate in OptimizationLoop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from autoagent.archive import Archive, ArchiveEntry
from autoagent.benchmark import Benchmark, BenchmarkExample, ScoringResult
from autoagent.evaluation import Evaluator
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
from autoagent.verification import TLAVerifier, VerificationResult


# ---------------------------------------------------------------------------
# Helpers — reuse patterns from test_loop.py
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


class MockTLAVerifier:
    """Mock TLAVerifier returning predetermined results per call."""

    def __init__(
        self,
        results: list[VerificationResult],
        is_available: bool = True,
    ) -> None:
        self._results = results
        self._call_count = 0
        self._is_available = is_available

    def available(self) -> bool:
        return self._is_available

    def verify(self, source: str) -> VerificationResult:
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


class TestLoopVerificationGate:
    """Integration tests for the TLA+ verification gate in the loop."""

    def test_proposal_passes_tla_evaluated_normally(self, tmp_path: Path) -> None:
        """When TLA+ passes, proposal proceeds to evaluation and archive
        entry has tla_verification with passed=True."""
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

        verifier = MockTLAVerifier(results=[
            VerificationResult(
                passed=True, spec_text="MODULE Spec ...", attempts=1,
                cost_usd=0.0005,
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
            tla_verifier=verifier,
        )

        final = loop.run()
        assert final.phase == "completed"
        assert final.current_iteration == 1

        entries = archive.query()
        assert len(entries) == 1
        entry = entries[0]
        # Since V1 is an exact echo, it should be kept
        assert entry.decision == "keep"
        # tla_verification present with passed=True
        assert entry.tla_verification is not None
        assert entry.tla_verification["passed"] is True
        assert entry.tla_verification["attempts"] == 1
        assert entry.tla_verification["cost_usd"] == 0.0005
        assert entry.tla_verification["skipped"] is False

    def test_proposal_fails_tla_discarded_without_evaluation(self, tmp_path: Path) -> None:
        """When TLA+ fails, proposal is discarded without evaluation.
        Archive entry has tla_verification with passed=False and violations."""
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

        violations = ["Error: Invariant SafetyProp is violated"]
        verifier = MockTLAVerifier(results=[
            VerificationResult(
                passed=False, violations=violations,
                spec_text="MODULE Spec ...", attempts=3, cost_usd=0.002,
            ),
            # Second iteration passes — proves loop continues after discard
            VerificationResult(
                passed=True, spec_text="MODULE Spec2 ...", attempts=1,
                cost_usd=0.001,
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
            tla_verifier=verifier,
        )

        final = loop.run()
        assert final.phase == "completed"
        assert final.current_iteration == 2

        entries = archive.query()
        assert len(entries) == 2

        # First entry: discarded due to TLA+ failure
        first = entries[0]
        assert first.decision == "discard"
        assert first.tla_verification is not None
        assert first.tla_verification["passed"] is False
        assert first.tla_verification["violations"] == violations
        assert first.tla_verification["attempts"] == 3
        assert "tla_verification_failed" in first.rationale
        # Evaluation result should be the zero-score placeholder
        assert first.evaluation_result["primary_score"] == 0.0

        # Second entry: kept (TLA+ passed, then evaluated)
        second = entries[1]
        assert second.decision == "keep"
        assert second.tla_verification is not None
        assert second.tla_verification["passed"] is True

    def test_no_verifier_loop_works_as_before(self, tmp_path: Path) -> None:
        """tla_verifier=None → no gate, loop works exactly as before.
        Archive entries have tla_verification=None."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        proposals = [
            ProposalResult(
                proposed_source=_PIPELINE_V1, rationale="v1",
                cost_usd=0.001, success=True,
            ),
            ProposalResult(
                proposed_source=_PIPELINE_V2, rationale="v2",
                cost_usd=0.002, success=True,
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
            max_iterations=2,
        )

        final = loop.run()
        assert final.phase == "completed"
        assert final.current_iteration == 2

        entries = archive.query()
        assert len(entries) == 2
        for entry in entries:
            assert entry.tla_verification is None

    def test_verifier_unavailable_gate_skipped(self, tmp_path: Path) -> None:
        """When verifier.available() returns False, the gate is skipped.
        Archive entry has tla_verification with skipped=True."""
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

        # Verifier returns skipped result (simulating Java unavailable)
        verifier = MockTLAVerifier(
            results=[
                VerificationResult(
                    passed=True, skipped=True,
                    skip_reason="Java not available on PATH",
                ),
            ],
            is_available=False,
        )

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
            tla_verifier=verifier,
        )

        final = loop.run()
        assert final.phase == "completed"

        entries = archive.query()
        assert len(entries) == 1
        entry = entries[0]
        # Evaluation happened (gate skipped, not blocked)
        assert entry.decision == "keep"
        assert entry.tla_verification is not None
        assert entry.tla_verification["skipped"] is True
        assert entry.tla_verification["passed"] is True

    def test_tla_verification_persisted_in_json(self, tmp_path: Path) -> None:
        """tla_verification dict appears in archive JSON files on disk."""
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

        verifier = MockTLAVerifier(results=[
            VerificationResult(
                passed=True, spec_text="MODULE Spec ...", attempts=1,
                cost_usd=0.0005,
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
            tla_verifier=verifier,
        )

        loop.run()

        # Read raw JSON from disk
        json_files = list(sm.archive_dir.glob("*-keep.json"))
        assert len(json_files) == 1
        data = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert "tla_verification" in data
        assert data["tla_verification"]["passed"] is True
        assert data["tla_verification"]["spec_text"] == "MODULE Spec ..."

    def test_tla_cost_accumulated_in_budget(self, tmp_path: Path) -> None:
        """TLA+ verification cost is accumulated into total_cost_usd."""
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

        tla_cost = 0.005
        verifier = MockTLAVerifier(results=[
            VerificationResult(
                passed=True, spec_text="MODULE Spec ...", attempts=1,
                cost_usd=tla_cost,
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
            tla_verifier=verifier,
        )

        final = loop.run()
        # Total cost should include proposal cost + TLA cost
        assert final.total_cost_usd >= 0.001 + tla_cost

    def test_backward_compat_old_entries_without_tla_verification(self, tmp_path: Path) -> None:
        """Old archive entries without tla_verification field deserialize
        correctly with tla_verification=None."""
        old_data = {
            "iteration_id": 1,
            "timestamp": 1234567890.0,
            "pipeline_diff": "",
            "evaluation_result": {
                "primary_score": 0.5,
                "per_example_results": [],
                "metrics": None,
                "benchmark_id": "test",
                "duration_ms": 100.0,
                "num_examples": 1,
                "num_failures": 0,
            },
            "rationale": "test",
            "decision": "keep",
            "parent_iteration_id": None,
            "mutation_type": None,
            # No tla_verification key
        }
        entry = ArchiveEntry.from_dict(old_data)
        assert entry.tla_verification is None
        # asdict should include it
        d = entry.asdict()
        assert "tla_verification" in d
        assert d["tla_verification"] is None
