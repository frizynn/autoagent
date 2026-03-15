"""Integration tests for sandbox runner gate in OptimizationLoop."""

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
from autoagent.pipeline import PipelineRunner
from autoagent.primitives import (
    MetricsCollector,
    MockLLM,
    MockRetriever,
    PrimitivesContext,
)
from autoagent.sandbox import SandboxResult, SandboxRunner
from autoagent.state import StateManager
from autoagent.types import PipelineResult


# ---------------------------------------------------------------------------
# Helpers — reuse patterns from test_loop_verification.py / test_loop_leakage.py
# ---------------------------------------------------------------------------

_PIPELINE_V1 = '''\
def run(input_data, primitives=None):
    """V1 — baseline echo."""
    return {"echo": input_data}
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


class MockSandboxRunner:
    """Duck-types SandboxRunner for loop integration tests.

    Controls availability and tracks whether run() was delegated through
    to the evaluator.
    """

    def __init__(
        self,
        is_available: bool = True,
        fallback_reason: str = "docker binary not found on PATH",
    ) -> None:
        self._is_available = is_available
        self._fallback_reason = fallback_reason
        self.run_call_count = 0

    @staticmethod
    def available() -> bool:
        # Will be overridden per-instance below
        raise NotImplementedError

    def _diagnose_unavailability(self) -> str:
        return self._fallback_reason

    def run(
        self,
        pipeline_path: Any = None,
        input_data: Any = None,
        primitives_context: Any = None,
        *,
        timeout: float | None = None,
    ) -> PipelineResult:
        """Delegate to PipelineRunner — we just track that we were called."""
        self.run_call_count += 1
        runner = PipelineRunner()
        return runner.run(pipeline_path, input_data, primitives_context, timeout=timeout)


class AvailableMockSandboxRunner(MockSandboxRunner):
    """Mock sandbox runner that reports Docker as available."""

    def __init__(self) -> None:
        super().__init__(is_available=True)

    @staticmethod
    def available() -> bool:
        return True


class UnavailableMockSandboxRunner(MockSandboxRunner):
    """Mock sandbox runner that reports Docker as unavailable."""

    def __init__(self, reason: str = "docker binary not found on PATH") -> None:
        super().__init__(is_available=False, fallback_reason=reason)

    @staticmethod
    def available() -> bool:
        return False


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
# Tests
# ---------------------------------------------------------------------------


class TestLoopSandbox:
    """Integration tests for sandbox runner wiring in the loop."""

    def test_sandbox_runner_passed_to_evaluator(self, tmp_path: Path) -> None:
        """When sandbox_runner is available, loop replaces evaluator's runner."""
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
        sandbox = AvailableMockSandboxRunner()

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
            sandbox_runner=sandbox,
        )

        # The loop should have replaced evaluator's runner with sandbox
        assert loop.evaluator.runner is sandbox
        assert loop._sandbox_used is True
        assert loop._sandbox_fallback_reason is None

        final = loop.run()
        assert final.phase == "completed"

        # Sandbox was used for evaluation
        assert sandbox.run_call_count >= 1

        # Archive entry has sandbox_execution metadata
        entries = archive.query()
        assert len(entries) == 1
        se = entries[0].sandbox_execution
        assert se is not None
        assert se["sandbox_used"] is True
        assert se["network_policy"] == "none"
        assert se["fallback_reason"] is None

    def test_fallback_when_unavailable(self, tmp_path: Path) -> None:
        """When Docker is unavailable, loop uses default evaluator and logs reason."""
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
        sandbox = UnavailableMockSandboxRunner(reason="docker daemon not running or not accessible")

        original_evaluator = _make_evaluator(tmp_path)
        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=original_evaluator,
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
            sandbox_runner=sandbox,
        )

        # Evaluator should NOT have been replaced
        assert loop.evaluator is original_evaluator
        assert loop._sandbox_used is False
        assert loop._sandbox_fallback_reason == "docker daemon not running or not accessible"

        final = loop.run()
        assert final.phase == "completed"

        # Sandbox run was never called
        assert sandbox.run_call_count == 0

        # Archive entry has sandbox_execution with fallback_reason
        entries = archive.query()
        assert len(entries) == 1
        se = entries[0].sandbox_execution
        assert se is not None
        assert se["sandbox_used"] is False
        assert se["fallback_reason"] == "docker daemon not running or not accessible"

    def test_no_sandbox_runner_no_metadata(self, tmp_path: Path) -> None:
        """When no sandbox_runner provided, sandbox_execution is None."""
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
        assert entries[0].sandbox_execution is None

    def test_sandbox_metadata_persisted_in_json(self, tmp_path: Path) -> None:
        """sandbox_execution dict appears in archive JSON files on disk."""
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
        sandbox = AvailableMockSandboxRunner()

        loop = OptimizationLoop(
            state_manager=sm,
            archive=archive,
            evaluator=_make_evaluator(tmp_path),
            meta_agent=meta,
            benchmark=benchmark,
            primitives_factory=_make_primitives_factory(),
            max_iterations=1,
            sandbox_runner=sandbox,
        )

        loop.run()

        # Read raw JSON from disk
        json_files = list(sm.archive_dir.glob("*-keep.json"))
        assert len(json_files) == 1
        data = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert "sandbox_execution" in data
        assert data["sandbox_execution"]["sandbox_used"] is True
        assert data["sandbox_execution"]["network_policy"] == "none"
