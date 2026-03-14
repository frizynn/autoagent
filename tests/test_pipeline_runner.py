"""Tests for PipelineRunner — dynamic pipeline loading, execution, and error handling."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from autoagent.pipeline import PipelineRunner
from autoagent.primitives import MetricsCollector, MockLLM, MockRetriever, PrimitivesContext

FIXTURES = Path(__file__).parent / "fixtures"


def _make_primitives() -> PrimitivesContext:
    """Build a PrimitivesContext with mock primitives sharing a collector."""
    collector = MetricsCollector()
    # Use a model with known cost config so cost_usd > 0
    llm = MockLLM(
        response="summarized answer",
        tokens_in=10,
        tokens_out=20,
        model="gpt-4o-mini",
        latency_ms=5.0,
        collector=collector,
    )
    retriever = MockRetriever(
        documents=["doc alpha", "doc beta"],
        tokens_in=5,
        tokens_out=0,
        model="mock-retriever",
        latency_ms=2.0,
        collector=collector,
    )
    return PrimitivesContext(llm=llm, retriever=retriever, collector=collector)


class TestSuccessfulExecution:
    """Toy pipeline runs through runner and produces real metrics."""

    def test_toy_pipeline_returns_success(self) -> None:
        runner = PipelineRunner(allowed_root=FIXTURES)
        ctx = _make_primitives()
        result = runner.run(FIXTURES / "toy_pipeline.py", "test query", ctx)

        assert result.success is True
        assert result.error is None
        assert result.output is not None
        assert result.output["answer"] == "summarized answer"
        assert result.output["sources"] == ["doc alpha", "doc beta"]

    def test_toy_pipeline_metrics_nonzero(self) -> None:
        runner = PipelineRunner(allowed_root=FIXTURES)
        ctx = _make_primitives()
        result = runner.run(FIXTURES / "toy_pipeline.py", "test query", ctx)

        assert result.metrics is not None
        assert result.metrics.tokens_in > 0
        assert result.metrics.tokens_out > 0
        assert result.metrics.cost_usd > 0
        assert result.metrics.latency_ms > 0

    def test_duration_ms_positive(self) -> None:
        runner = PipelineRunner(allowed_root=FIXTURES)
        ctx = _make_primitives()
        result = runner.run(FIXTURES / "toy_pipeline.py", "test query", ctx)

        assert result.duration_ms > 0


class TestErrorPaths:
    """All failure modes produce PipelineResult(success=False) with ErrorInfo."""

    def test_missing_file(self) -> None:
        runner = PipelineRunner(allowed_root=FIXTURES)
        result = runner.run(FIXTURES / "nonexistent.py")

        assert result.success is False
        assert result.error is not None
        assert result.error.type == "FileNotFoundError"
        assert "not found" in result.error.message
        assert result.duration_ms > 0

    def test_missing_run_function(self) -> None:
        runner = PipelineRunner(allowed_root=FIXTURES)
        result = runner.run(FIXTURES / "bad_pipeline.py")

        assert result.success is False
        assert result.error is not None
        assert result.error.type == "AttributeError"
        assert "run" in result.error.message

    def test_exception_in_pipeline(self) -> None:
        runner = PipelineRunner(allowed_root=FIXTURES)
        result = runner.run(FIXTURES / "crash_pipeline.py")

        assert result.success is False
        assert result.error is not None
        assert result.error.type == "ValueError"
        assert "something went wrong" in result.error.message
        assert result.error.traceback is not None
        assert "ValueError" in result.error.traceback

    def test_path_outside_allowed_root(self, tmp_path: Path) -> None:
        # Pipeline exists but is outside allowed_root
        outside_pipeline = tmp_path / "rogue_pipeline.py"
        outside_pipeline.write_text("def run(d, p): return 'hacked'")

        runner = PipelineRunner(allowed_root=FIXTURES)
        result = runner.run(outside_pipeline)

        assert result.success is False
        assert result.error is not None
        assert result.error.type == "PermissionError"
        assert "outside allowed root" in result.error.message

    def test_non_py_file_rejected(self) -> None:
        runner = PipelineRunner(allowed_root=FIXTURES)
        result = runner.run(FIXTURES / "bad_pipeline.txt")

        assert result.success is False
        assert result.error is not None
        assert result.error.type == "ValueError"
        assert ".py" in result.error.message


class TestFreshModuleLoading:
    """Each run() loads the module fresh — no stale code from previous runs."""

    def test_modified_pipeline_reflects_changes(self, tmp_path: Path) -> None:
        pipeline = tmp_path / "evolving.py"

        # Version 1
        pipeline.write_text(textwrap.dedent("""\
            def run(input_data, primitives):
                return {"version": 1}
        """))

        runner = PipelineRunner(allowed_root=tmp_path)
        r1 = runner.run(pipeline)
        assert r1.success is True
        assert r1.output["version"] == 1

        # Version 2 — same file path, different code
        pipeline.write_text(textwrap.dedent("""\
            def run(input_data, primitives):
                return {"version": 2}
        """))

        r2 = runner.run(pipeline)
        assert r2.success is True
        assert r2.output["version"] == 2
