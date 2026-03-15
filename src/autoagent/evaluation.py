"""Evaluation engine — runs a pipeline against a benchmark with per-example timeout."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from autoagent.benchmark import Benchmark, BenchmarkExample, ScoringResult
from autoagent.pipeline import PipelineRunner
from autoagent.primitives import MetricsCollector, MockLLM, MockRetriever, PrimitivesContext
from autoagent.types import MetricsSnapshot, PipelineResult


@dataclass(frozen=True)
class ExampleResult:
    """Result of evaluating a single benchmark example."""

    example_id: str
    score: float
    success: bool
    error: str | None = None
    duration_ms: float = 0.0
    metrics: MetricsSnapshot | None = None


@dataclass(frozen=True)
class EvaluationResult:
    """Aggregate result of evaluating a pipeline against an entire benchmark.

    Boundary contract type consumed by S04 (CLI reporting) and S05 (comparison).

    Inspection surfaces:
    - ``primary_score``: mean of per-example scores (0.0–1.0)
    - ``per_example_results``: list of :class:`ExampleResult` for drill-down
    - ``metrics``: aggregated :class:`MetricsSnapshot` across all examples
    - ``duration_ms``: total wall-clock time for the evaluation run
    - ``num_failures``: count of examples with score < 1.0 or errors
    """

    primary_score: float
    per_example_results: list[ExampleResult]
    metrics: MetricsSnapshot | None
    benchmark_id: str
    duration_ms: float
    num_examples: int
    num_failures: int


# Default factory for PrimitivesContext — used when caller doesn't provide one
def _default_primitives_factory() -> PrimitivesContext:
    """Create a fresh PrimitivesContext with mock providers for testing."""
    collector = MetricsCollector()
    return PrimitivesContext(
        llm=MockLLM(collector=collector),
        retriever=MockRetriever(collector=collector),
        collector=collector,
    )


class Evaluator:
    """Runs a pipeline against a benchmark dataset with per-example timeout.

    Each example gets a fresh :class:`PrimitivesContext` to prevent metric bleed.
    Per-example timeout is enforced via :class:`ThreadPoolExecutor`. Scoring
    errors are caught per-example (score=0.0, error recorded) so the full
    evaluation always completes.
    """

    def __init__(
        self,
        runner: PipelineRunner | None = None,
    ) -> None:
        self.runner = runner or PipelineRunner()

    def evaluate(
        self,
        pipeline_path: str | Path,
        benchmark: Benchmark,
        timeout_per_example: float = 30.0,
        primitives_factory: Callable[[], PrimitivesContext] | None = None,
    ) -> EvaluationResult:
        """Evaluate *pipeline_path* against every example in *benchmark*.

        Parameters
        ----------
        pipeline_path:
            Path to the pipeline ``.py`` file.
        benchmark:
            Loaded :class:`Benchmark` with examples and scorer.
        timeout_per_example:
            Maximum seconds per example. Exceeded → score 0.0, error="timeout".
        primitives_factory:
            Callable returning a fresh :class:`PrimitivesContext` per example.
            Defaults to a mock-based context for testing.

        Returns
        -------
        EvaluationResult
            Aggregate evaluation with per-example breakdown.
        """
        factory = primitives_factory or _default_primitives_factory
        resolved_path = Path(pipeline_path).resolve()

        t0 = time.perf_counter()
        per_example_results: list[ExampleResult] = []
        all_metrics_snapshots: list[MetricsSnapshot] = []

        for example in benchmark.examples:
            result = self._run_single_example(
                resolved_path, example, benchmark.scorer, factory, timeout_per_example,
            )
            per_example_results.append(result)
            if result.metrics is not None:
                all_metrics_snapshots.append(result.metrics)

        duration_ms = (time.perf_counter() - t0) * 1000

        # Aggregate metrics across all examples
        aggregated_metrics = self._aggregate_metrics(all_metrics_snapshots)

        # Primary score = mean of per-example scores
        scores = [r.score for r in per_example_results]
        primary_score = sum(scores) / len(scores) if scores else 0.0

        num_failures = sum(1 for r in per_example_results if not r.success)

        return EvaluationResult(
            primary_score=primary_score,
            per_example_results=per_example_results,
            metrics=aggregated_metrics,
            benchmark_id=benchmark.source_path,
            duration_ms=duration_ms,
            num_examples=len(per_example_results),
            num_failures=num_failures,
        )

    def _run_single_example(
        self,
        pipeline_path: Path,
        example: BenchmarkExample,
        scorer: Callable[[Any, Any], ScoringResult],
        factory: Callable[[], PrimitivesContext],
        timeout: float,
    ) -> ExampleResult:
        """Run one example with timeout enforcement and error handling."""
        t0 = time.perf_counter()

        # Fresh context per example — prevents metric bleed
        ctx = factory()

        # Run pipeline with timeout via ThreadPoolExecutor
        try:
            pipeline_result = self._run_with_timeout(
                pipeline_path, example.input, ctx, timeout,
            )
        except FuturesTimeoutError:
            duration_ms = (time.perf_counter() - t0) * 1000
            return ExampleResult(
                example_id=example.id,
                score=0.0,
                success=False,
                error="timeout",
                duration_ms=duration_ms,
                metrics=ctx.collector.aggregate(),
            )

        # Pipeline failed
        if not pipeline_result.success:
            duration_ms = (time.perf_counter() - t0) * 1000
            error_msg = (
                pipeline_result.error.message
                if pipeline_result.error
                else "unknown pipeline error"
            )
            return ExampleResult(
                example_id=example.id,
                score=0.0,
                success=False,
                error=error_msg,
                duration_ms=duration_ms,
                metrics=pipeline_result.metrics or ctx.collector.aggregate(),
            )

        # Score the result
        try:
            scoring_result = scorer(pipeline_result.output, example.expected)
            score = scoring_result.score
            scoring_error = scoring_result.error
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            return ExampleResult(
                example_id=example.id,
                score=0.0,
                success=False,
                error=f"scoring_error: {exc}",
                duration_ms=duration_ms,
                metrics=pipeline_result.metrics or ctx.collector.aggregate(),
            )

        duration_ms = (time.perf_counter() - t0) * 1000
        success = score >= 1.0 and scoring_error is None

        error = scoring_error if scoring_error else None

        return ExampleResult(
            example_id=example.id,
            score=score,
            success=success,
            error=error,
            duration_ms=duration_ms,
            metrics=pipeline_result.metrics or ctx.collector.aggregate(),
        )

    def _run_with_timeout(
        self,
        pipeline_path: Path,
        input_data: Any,
        ctx: PrimitivesContext,
        timeout: float,
    ) -> PipelineResult:
        """Execute the pipeline in a thread with timeout enforcement.

        Uses ``cancel_futures=True`` on shutdown so the context manager
        doesn't block waiting for a timed-out thread to finish.
        """
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(
                self.runner.run, pipeline_path, input_data, ctx,
            )
            return future.result(timeout=timeout)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _aggregate_metrics(snapshots: list[MetricsSnapshot]) -> MetricsSnapshot | None:
        """Aggregate multiple MetricsSnapshot objects into one."""
        if not snapshots:
            return None
        return MetricsSnapshot(
            latency_ms=sum(s.latency_ms for s in snapshots),
            tokens_in=sum(s.tokens_in for s in snapshots),
            tokens_out=sum(s.tokens_out for s in snapshots),
            cost_usd=sum(s.cost_usd for s in snapshots),
            model=snapshots[-1].model,
            provider=snapshots[-1].provider,
        )
