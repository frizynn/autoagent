"""Final assembly integration test — all four safety gates active in one loop run.

Capstone test for Milestone M003: exercises TLA+ verification, leakage detection,
Pareto multi-objective, and sandbox isolation across four iterations.

Iteration 1: TLA+ verification fails → discarded
Iteration 2: Leakage check blocks → discarded
Iteration 3: Passes TLA+/leakage, Pareto discards (score regresses)
Iteration 4: Passes all gates, sandbox-wrapped evaluation succeeds → kept
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autoagent.archive import Archive, ArchiveEntry
from autoagent.benchmark import Benchmark, BenchmarkExample, ScoringResult
from autoagent.evaluation import Evaluator
from autoagent.leakage import LeakageResult
from autoagent.loop import OptimizationLoop
from autoagent.meta_agent import MetaAgent, ProposalResult
from autoagent.pipeline import PipelineRunner
from autoagent.primitives import (
    MetricsCollector,
    MockLLM,
    MockRetriever,
    PrimitivesContext,
)
from autoagent.sandbox import SandboxRunner
from autoagent.state import StateManager
from autoagent.types import PipelineResult
from autoagent.verification import VerificationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# V1: correct pipeline that scores well with exact_match
_PIPELINE_V1 = '''\
def run(input_data, primitives=None):
    """V1 — baseline echo."""
    return {"echo": input_data}
'''

# V1b: simpler variant — lower complexity so Pareto keeps it
_PIPELINE_V1B = '''\
def run(d, p=None):
    return {"echo": d}
'''

# V2: pipeline that scores 0 AND is more complex (so Pareto dominance applies)
_PIPELINE_REGRESSED = '''\
def run(input_data, primitives=None):
    """Regressed — returns wrong format with extra complexity."""
    import hashlib
    import base64
    data = str(input_data)
    digest = hashlib.sha256(data.encode()).hexdigest()
    encoded = base64.b64encode(digest.encode()).decode()
    intermediate = {k: v for k, v in enumerate(encoded)}
    filtered = {k: v for k, v in intermediate.items() if k % 2 == 0}
    return {"wrong": "format", "hash": digest, "filtered": filtered}
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

    def __init__(self, results: list[VerificationResult]) -> None:
        self._results = results
        self._call_count = 0

    def available(self) -> bool:
        return True

    def verify(self, source: str) -> VerificationResult:
        idx = self._call_count % len(self._results)
        self._call_count += 1
        return self._results[idx]


class MockLeakageChecker:
    """Mock LeakageChecker returning predetermined results per call."""

    def __init__(self, results: list[LeakageResult]) -> None:
        self._results = results
        self._call_count = 0

    def check(self, benchmark: Any, pipeline_source: str) -> LeakageResult:
        idx = self._call_count % len(self._results)
        self._call_count += 1
        return self._results[idx]


class AvailableMockSandboxRunner:
    """Mock sandbox runner that reports Docker as available."""

    def __init__(self) -> None:
        self.run_call_count = 0

    @staticmethod
    def available() -> bool:
        return True

    @staticmethod
    def _diagnose_unavailability() -> str:
        return ""

    def run(
        self,
        pipeline_path: Any = None,
        input_data: Any = None,
        primitives_context: Any = None,
        *,
        timeout: float | None = None,
    ) -> PipelineResult:
        self.run_call_count += 1
        runner = PipelineRunner()
        return runner.run(pipeline_path, input_data, primitives_context, timeout=timeout)


def _make_benchmark(tmp_path: Path) -> Benchmark:
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
# Test
# ---------------------------------------------------------------------------


class TestFinalAssembly:
    """Capstone: all four safety gates active in one loop run."""

    def test_four_gates_all_active(self, tmp_path: Path) -> None:
        """Five iterations, each gate exercised, all results in archive.

        Iteration 1: V1 passes all gates → keep (establishes baseline)
        Iteration 2: TLA+ fails → discard
        Iteration 3: Leakage blocks → discard
        Iteration 4: TLA+/leakage pass, Pareto discards (regressed score)
        Iteration 5: Passes all gates, sandbox eval succeeds → keep
        """
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        proposals = [
            # Iter 1: good pipeline, establishes baseline
            ProposalResult(
                proposed_source=_PIPELINE_V1, rationale="iter1-baseline",
                cost_usd=0.001, success=True,
            ),
            # Iter 2: good pipeline, but TLA+ will fail
            ProposalResult(
                proposed_source=_PIPELINE_V1, rationale="iter2-tla-fail",
                cost_usd=0.001, success=True,
            ),
            # Iter 3: good pipeline, but leakage will block
            ProposalResult(
                proposed_source=_PIPELINE_V1, rationale="iter3-leakage",
                cost_usd=0.001, success=True,
            ),
            # Iter 4: regressed pipeline, Pareto will discard
            ProposalResult(
                proposed_source=_PIPELINE_REGRESSED, rationale="iter4-regressed",
                cost_usd=0.001, success=True,
            ),
            # Iter 5: simpler good pipeline, all gates pass
            ProposalResult(
                proposed_source=_PIPELINE_V1B, rationale="iter5-all-pass",
                cost_usd=0.001, success=True,
            ),
        ]
        meta = SequentialMockMetaAgent(proposals)

        # TLA+ verifier: pass iter 1, fail iter 2, pass iters 3-5
        tla_verifier = MockTLAVerifier(results=[
            VerificationResult(
                passed=True, violations=[], spec_text="spec",
                attempts=1, cost_usd=0.0,
            ),
            VerificationResult(
                passed=False,
                violations=["invariant violated: no output type annotation"],
                spec_text="spec", attempts=1, cost_usd=0.0,
            ),
            VerificationResult(
                passed=True, violations=[], spec_text="spec",
                attempts=1, cost_usd=0.0,
            ),
            VerificationResult(
                passed=True, violations=[], spec_text="spec",
                attempts=1, cost_usd=0.0,
            ),
            VerificationResult(
                passed=True, violations=[], spec_text="spec",
                attempts=1, cost_usd=0.0,
            ),
        ])

        # Leakage checker: pass iter 1, block iter 3, pass iters 4-5
        # (iter 2 won't reach leakage — discarded by TLA+)
        leakage_checker = MockLeakageChecker(results=[
            LeakageResult(
                blocked=False, exact_matches=0,
                fuzzy_warnings=[], cost_usd=0.0,
            ),
            LeakageResult(
                blocked=True, exact_matches=5,
                fuzzy_warnings=[], cost_usd=0.0,
            ),
            LeakageResult(
                blocked=False, exact_matches=0,
                fuzzy_warnings=[], cost_usd=0.0,
            ),
            LeakageResult(
                blocked=False, exact_matches=0,
                fuzzy_warnings=[], cost_usd=0.0,
            ),
        ])

        # Sandbox runner: available, wraps evaluation
        sandbox = AvailableMockSandboxRunner()

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=5,
            tla_verifier=tla_verifier,
            leakage_checker=leakage_checker,
            sandbox_runner=sandbox,
        )

        final = loop.run()
        assert final.phase == "completed"
        assert final.current_iteration == 5

        entries = archive.query()
        assert len(entries) == 5

        # --- Iteration 1: All pass → kept (baseline) ---
        e1 = entries[0]
        assert e1.decision == "keep"
        assert e1.tla_verification is not None
        assert e1.tla_verification["passed"] is True
        assert e1.leakage_check is not None
        assert e1.leakage_check["blocked"] is False
        assert e1.pareto_evaluation is not None
        assert e1.pareto_evaluation["decision"] == "keep"
        assert e1.sandbox_execution is not None
        assert e1.sandbox_execution["sandbox_used"] is True

        # --- Iteration 2: TLA+ failed → discarded ---
        e2 = entries[1]
        assert e2.decision == "discard"
        assert e2.tla_verification is not None
        assert e2.tla_verification["passed"] is False
        assert len(e2.tla_verification["violations"]) > 0
        # Leakage was not reached (TLA+ failed first)
        assert e2.leakage_check is None
        assert e2.sandbox_execution is not None

        # --- Iteration 3: Leakage blocked → discarded ---
        e3 = entries[2]
        assert e3.decision == "discard"
        assert e3.tla_verification is not None
        assert e3.tla_verification["passed"] is True
        assert e3.leakage_check is not None
        assert e3.leakage_check["blocked"] is True
        assert e3.leakage_check["exact_matches"] == 5
        assert e3.sandbox_execution is not None

        # --- Iteration 4: Pareto discards (regressed score) ---
        e4 = entries[3]
        assert e4.decision == "discard"
        assert e4.tla_verification is not None
        assert e4.tla_verification["passed"] is True
        assert e4.leakage_check is not None
        assert e4.leakage_check["blocked"] is False
        assert e4.pareto_evaluation is not None
        assert e4.pareto_evaluation["decision"] == "discard"
        assert e4.sandbox_execution is not None

        # --- Iteration 5: All gates pass → kept ---
        e5 = entries[4]
        assert e5.decision == "keep"
        assert e5.tla_verification is not None
        assert e5.tla_verification["passed"] is True
        assert e5.leakage_check is not None
        assert e5.leakage_check["blocked"] is False
        assert e5.pareto_evaluation is not None
        assert e5.pareto_evaluation["decision"] == "keep"
        assert e5.sandbox_execution is not None
        assert e5.sandbox_execution["sandbox_used"] is True

        # Sandbox was used for evaluation (iters 1, 4, 5 reached eval)
        assert sandbox.run_call_count >= 3

    def test_archive_json_has_all_gate_fields(self, tmp_path: Path) -> None:
        """Verify gate results are persisted in raw JSON on disk."""
        sm = _init_project(tmp_path)
        benchmark = _make_benchmark(tmp_path)
        archive = Archive(sm.archive_dir)

        # Single iteration with all gates passing
        proposals = [
            ProposalResult(
                proposed_source=_PIPELINE_V1, rationale="all-pass",
                cost_usd=0.001, success=True,
            ),
        ]
        meta = SequentialMockMetaAgent(proposals)

        tla_verifier = MockTLAVerifier(results=[
            VerificationResult(
                passed=True, violations=[], spec_text="spec",
                attempts=1, cost_usd=0.0,
            ),
        ])
        leakage_checker = MockLeakageChecker(results=[
            LeakageResult(
                blocked=False, exact_matches=0,
                fuzzy_warnings=[], cost_usd=0.0,
            ),
        ])
        sandbox = AvailableMockSandboxRunner()

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
            tla_verifier=tla_verifier,
            leakage_checker=leakage_checker,
            sandbox_runner=sandbox,
        )

        loop.run()

        json_files = list(sm.archive_dir.glob("*-keep.json"))
        assert len(json_files) == 1
        data = json.loads(json_files[0].read_text(encoding="utf-8"))

        # All four gate fields present in raw JSON
        assert "tla_verification" in data
        assert data["tla_verification"]["passed"] is True
        assert "leakage_check" in data
        assert data["leakage_check"]["blocked"] is False
        assert "pareto_evaluation" in data
        assert data["pareto_evaluation"]["decision"] == "keep"
        assert "sandbox_execution" in data
        assert data["sandbox_execution"]["sandbox_used"] is True
