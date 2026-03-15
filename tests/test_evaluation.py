"""Tests for autoagent.evaluation — evaluator, timeout, scoring, and aggregation."""

import json
import time
import pytest
from pathlib import Path

from autoagent.benchmark import Benchmark, BenchmarkExample, ScoringResult
from autoagent.evaluation import (
    Evaluator,
    EvaluationResult,
    ExampleResult,
    _default_primitives_factory,
)
from autoagent.pipeline import PipelineRunner
from autoagent.primitives import MetricsCollector, MockLLM, MockRetriever, PrimitivesContext
from autoagent.types import MetricsSnapshot


FIXTURES = Path(__file__).parent / "fixtures"
TOY_PIPELINE = FIXTURES / "toy_pipeline.py"
SLOW_PIPELINE = FIXTURES / "slow_pipeline.py"
PASSTHROUGH_PIPELINE = FIXTURES / "passthrough_pipeline.py"


def _make_primitives() -> PrimitivesContext:
    """Create a fresh mock PrimitivesContext."""
    collector = MetricsCollector()
    return PrimitivesContext(
        llm=MockLLM(collector=collector),
        retriever=MockRetriever(collector=collector),
        collector=collector,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestEvaluatorHappyPath:
    def test_all_examples_pass(self):
        """All examples that expect the toy pipeline's exact output should score 1.0."""
        data = [
            {"id": "a", "input": "q1", "expected": str({"answer": "mock response", "sources": ["doc1", "doc2"]})},
            {"id": "b", "input": "q2", "expected": str({"answer": "mock response", "sources": ["doc1", "doc2"]})},
        ]
        bm = _benchmark_from_list(data, "exact_match")
        evaluator = Evaluator(runner=PipelineRunner(allowed_root=FIXTURES))
        result = evaluator.evaluate(TOY_PIPELINE, bm, primitives_factory=_make_primitives)

        assert result.primary_score == 1.0
        assert result.num_examples == 2
        assert result.num_failures == 0
        assert all(r.success for r in result.per_example_results)
        assert all(r.score == 1.0 for r in result.per_example_results)
        assert result.duration_ms > 0
        assert result.metrics is not None

    def test_mixed_results(self):
        """Mix of passing and failing examples."""
        data = [
            {"id": "pass1", "input": "q1", "expected": str({"answer": "mock response", "sources": ["doc1", "doc2"]})},
            {"id": "fail1", "input": "q2", "expected": "wrong answer"},
        ]
        bm = _benchmark_from_list(data, "exact_match")
        evaluator = Evaluator(runner=PipelineRunner(allowed_root=FIXTURES))
        result = evaluator.evaluate(TOY_PIPELINE, bm, primitives_factory=_make_primitives)

        assert result.primary_score == 0.5
        assert result.num_examples == 2
        assert result.num_failures == 1
        # Check individual results
        pass_result = result.per_example_results[0]
        fail_result = result.per_example_results[1]
        assert pass_result.score == 1.0
        assert pass_result.success is True
        assert fail_result.score == 0.0
        assert fail_result.success is False


# ---------------------------------------------------------------------------
# Timeout enforcement
# ---------------------------------------------------------------------------


class TestTimeout:
    def test_timeout_produces_score_zero(self):
        """Slow pipeline hitting timeout → score 0.0, error='timeout'."""
        data = [{"id": "slow", "input": "x", "expected": "y"}]
        bm = _benchmark_from_list(data, "exact_match")
        evaluator = Evaluator(runner=PipelineRunner(allowed_root=FIXTURES))

        t0 = time.perf_counter()
        result = evaluator.evaluate(
            SLOW_PIPELINE, bm, timeout_per_example=0.5,
            primitives_factory=_make_primitives,
        )
        elapsed = time.perf_counter() - t0

        assert result.num_examples == 1
        assert result.num_failures == 1
        assert result.primary_score == 0.0
        ex = result.per_example_results[0]
        assert ex.error == "timeout"
        assert ex.score == 0.0
        assert ex.success is False
        # Should have returned in ~0.5s, not 10s
        assert elapsed < 5.0


# ---------------------------------------------------------------------------
# Scoring error handling
# ---------------------------------------------------------------------------


class TestScoringErrors:
    def test_scorer_exception_caught(self):
        """If the scorer raises, the example gets score 0.0 with error recorded."""
        def bad_scorer(output, expected):
            raise RuntimeError("scorer exploded")

        examples = [BenchmarkExample(input="x", expected="y", id="err1")]
        bm = Benchmark(examples=examples, scorer=bad_scorer, source_path="test")
        evaluator = Evaluator(runner=PipelineRunner(allowed_root=FIXTURES))
        result = evaluator.evaluate(
            PASSTHROUGH_PIPELINE, bm, primitives_factory=_make_primitives,
        )

        assert result.num_failures == 1
        ex = result.per_example_results[0]
        assert ex.score == 0.0
        assert ex.success is False
        assert "scoring_error" in ex.error
        assert "scorer exploded" in ex.error

    def test_pipeline_failure_recorded(self):
        """If pipeline fails, error is captured and evaluation continues."""
        data = [
            {"id": "crash", "input": "x", "expected": "y"},
            {"id": "ok", "input": "q", "expected": str({"answer": "mock response", "sources": ["doc1", "doc2"]})},
        ]
        bm = _benchmark_from_list(data, "exact_match")
        crash_pipeline = FIXTURES / "crash_pipeline.py"
        evaluator = Evaluator(runner=PipelineRunner(allowed_root=FIXTURES))

        # crash_pipeline raises, so all examples get pipeline error
        result = evaluator.evaluate(crash_pipeline, bm, primitives_factory=_make_primitives)
        # Both should fail since the pipeline itself crashes
        assert result.num_failures == 2
        assert all(not r.success for r in result.per_example_results)


# ---------------------------------------------------------------------------
# Fresh context per example
# ---------------------------------------------------------------------------


class TestFreshContext:
    def test_no_metric_bleed_between_examples(self):
        """Each example gets a fresh PrimitivesContext — metrics don't accumulate."""
        data = [
            {"id": "a", "input": "q1", "expected": "anything"},
            {"id": "b", "input": "q2", "expected": "anything"},
            {"id": "c", "input": "q3", "expected": "anything"},
        ]
        bm = _benchmark_from_list(data, "includes")

        contexts_seen: list[PrimitivesContext] = []
        original_factory = _make_primitives

        def tracking_factory():
            ctx = original_factory()
            contexts_seen.append(ctx)
            return ctx

        evaluator = Evaluator(runner=PipelineRunner(allowed_root=FIXTURES))
        evaluator.evaluate(TOY_PIPELINE, bm, primitives_factory=tracking_factory)

        # Each example got its own context
        assert len(contexts_seen) == 3
        # All contexts are distinct objects
        assert len(set(id(c) for c in contexts_seen)) == 3
        # Each context's collector should have exactly 2 snapshots (1 LLM + 1 Retriever)
        for ctx in contexts_seen:
            assert len(ctx.collector.snapshots) == 2


# ---------------------------------------------------------------------------
# Metric aggregation
# ---------------------------------------------------------------------------


class TestMetricAggregation:
    def test_aggregated_metrics_sum_across_examples(self):
        """Aggregated metrics should sum token counts across all examples."""
        data = [
            {"id": "a", "input": "q1", "expected": "anything"},
            {"id": "b", "input": "q2", "expected": "anything"},
        ]
        bm = _benchmark_from_list(data, "includes")
        evaluator = Evaluator(runner=PipelineRunner(allowed_root=FIXTURES))
        result = evaluator.evaluate(TOY_PIPELINE, bm, primitives_factory=_make_primitives)

        assert result.metrics is not None
        # toy_pipeline does 1 LLM call (10 in, 20 out) + 1 retriever call (5 in, 0 out) per example
        # 2 examples × (10+5) tokens_in = 30
        assert result.metrics.tokens_in == 30
        # 2 examples × (20+0) tokens_out = 40
        assert result.metrics.tokens_out == 40

    def test_per_example_metrics_present(self):
        data = [{"id": "a", "input": "q", "expected": "x"}]
        bm = _benchmark_from_list(data, "exact_match")
        evaluator = Evaluator(runner=PipelineRunner(allowed_root=FIXTURES))
        result = evaluator.evaluate(TOY_PIPELINE, bm, primitives_factory=_make_primitives)

        ex = result.per_example_results[0]
        assert ex.metrics is not None
        assert ex.duration_ms > 0


# ---------------------------------------------------------------------------
# Boundary contract imports
# ---------------------------------------------------------------------------


class TestBoundaryContracts:
    def test_evaluation_types_importable(self):
        from autoagent.evaluation import Evaluator, EvaluationResult, ExampleResult
        assert Evaluator is not None
        assert EvaluationResult is not None
        assert ExampleResult is not None

    def test_benchmark_types_importable(self):
        from autoagent.benchmark import Benchmark, BenchmarkExample
        assert Benchmark is not None
        assert BenchmarkExample is not None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _benchmark_from_list(data: list[dict], scorer_name: str) -> Benchmark:
    """Create a Benchmark from a list of dicts without going through a file."""
    examples = [
        BenchmarkExample(
            input=d["input"],
            expected=d["expected"],
            id=d.get("id", f"example_{i}"),
        )
        for i, d in enumerate(data)
    ]
    from autoagent.benchmark import BUILT_IN_SCORERS
    return Benchmark(
        examples=examples,
        scorer=BUILT_IN_SCORERS[scorer_name],
        source_path="test_inline",
    )
