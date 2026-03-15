# S03: Evaluation & Benchmark

**Goal:** A pipeline can be evaluated against a benchmark dataset with a scoring function, producing a multi-metric `EvaluationResult` with per-example timeout enforcement.
**Demo:** A toy pipeline runs against a JSON benchmark, scores each example (with one timeout), and returns `EvaluationResult` with primary_score + aggregated MetricsSnapshot + timing.

## Must-Haves

- `Benchmark` loads examples from JSON, resolves scoring functions (built-in registry + custom file)
- Built-in scorers: `exact_match`, `includes`
- `Evaluator` runs pipeline per-example via `PipelineRunner`, aggregates scores and metrics
- Per-example timeout via `concurrent.futures.ThreadPoolExecutor` — timeout → score 0.0, marked as failure (R022)
- `EvaluationResult` captures: primary_score, per_example_results, aggregated MetricsSnapshot, benchmark_id, duration_ms
- Fresh `PrimitivesContext` per example (no metric bleed between examples)
- Scoring function errors caught per-example — error → score 0.0, not crash
- `EvaluationResult` type is the boundary contract for S04/S05

## Proof Level

- This slice proves: contract — `Evaluator.evaluate()` returns structured `EvaluationResult` exercised by tests with mock providers
- Real runtime required: no (mock LLM/Retriever)
- Human/UAT required: no

## Verification

- `pytest tests/test_benchmark.py tests/test_evaluation.py -v` — all pass
- Tests cover: benchmark loading, built-in scorers, custom scorer resolution, evaluator happy path, per-example timeout, scoring error handling, metric aggregation, fresh context per example
- Boundary contract import: `from autoagent.evaluation import Evaluator, EvaluationResult` and `from autoagent.benchmark import Benchmark, BenchmarkExample`

## Observability / Diagnostics

- Runtime signals: `EvaluationResult.per_example_results` — per-example score, success, error, duration for diagnosing which examples fail
- Inspection surfaces: `EvaluationResult.primary_score`, `.metrics`, `.duration_ms` — top-level aggregates
- Failure visibility: per-example errors include type and message; timed-out examples have `error="timeout"` distinct from pipeline failures

## Integration Closure

- Upstream surfaces consumed: `PipelineRunner.run()`, `PrimitivesContext`, `MetricsSnapshot`, `PipelineResult` from S01
- New wiring introduced in this slice: none — standalone modules, no CLI hookup yet
- What remains before the milestone is truly usable end-to-end: S04 (archive), S05 (loop wiring), S06 (budget/recovery)

## Tasks

- [x] **T01: Build benchmark loader, evaluator, and scoring with per-example timeout** `est:45m`
  - Why: This is the entire slice — `benchmark.py` and `evaluation.py` are tightly coupled (evaluator needs benchmark to function) and small enough for one task
  - Files: `src/autoagent/benchmark.py`, `src/autoagent/evaluation.py`, `tests/test_benchmark.py`, `tests/test_evaluation.py`, `tests/fixtures/toy_benchmark.json`, `tests/fixtures/toy_scorer.py`
  - Do: Build `Benchmark` (JSON loading, `BenchmarkExample` dataclass, scorer registry + custom file resolution), `EvaluationResult` and `ExampleResult` types, `Evaluator` (per-example pipeline execution with fresh PrimitivesContext, ThreadPoolExecutor timeout, score aggregation). Built-in scorers: `exact_match`, `includes`. Scoring errors → score 0.0. Timeout → score 0.0 with error="timeout".
  - Verify: `pytest tests/test_benchmark.py tests/test_evaluation.py -v` — all pass; import check for boundary types
  - Done when: `Evaluator.evaluate(pipeline_path, benchmark)` returns `EvaluationResult` with correct primary_score, metrics aggregation, and per-example breakdown — verified by tests including timeout and error cases

## Files Likely Touched

- `src/autoagent/benchmark.py`
- `src/autoagent/evaluation.py`
- `tests/test_benchmark.py`
- `tests/test_evaluation.py`
- `tests/fixtures/toy_benchmark.json`
- `tests/fixtures/toy_scorer.py`
