---
id: S03
parent: M001
milestone: M001
provides:
  - Benchmark loader with JSON parsing and scorer resolution (built-in registry + custom file)
  - Evaluator with per-example pipeline execution, ThreadPoolExecutor timeout, and metric aggregation
  - EvaluationResult boundary contract type for S04/S05 consumption
requires:
  - slice: S01
    provides: PipelineRunner.run(), PrimitivesContext, MetricsSnapshot, PipelineResult
affects:
  - S04
  - S05
key_files:
  - src/autoagent/benchmark.py
  - src/autoagent/evaluation.py
  - tests/test_benchmark.py
  - tests/test_evaluation.py
  - tests/fixtures/toy_benchmark.json
  - tests/fixtures/toy_scorer.py
  - tests/fixtures/slow_pipeline.py
  - tests/fixtures/passthrough_pipeline.py
key_decisions:
  - "D018: ThreadPoolExecutor with shutdown(wait=False, cancel_futures=True) for per-example timeout"
  - "D019: compile()+exec() for custom scorer loading, matching pipeline loader pattern from S01"
patterns_established:
  - "ScorerFn callable protocol: (output, expected) -> ScoringResult"
  - "Per-example isolation via primitives_factory callable"
  - "EvaluationResult as the standard evaluation output type for downstream consumption"
observability_surfaces:
  - "EvaluationResult.per_example_results — score, success, error, duration_ms, metrics per example"
  - "Timeout examples: error='timeout'; scoring failures: error='scoring_error: {detail}'; pipeline failures: error message from PipelineResult"
drill_down_paths:
  - .gsd/milestones/M001/slices/S03/tasks/T01-SUMMARY.md
duration: 15m
verification_result: passed
completed_at: 2026-03-14
---

# S03: Evaluation & Benchmark

**Benchmark loader and evaluator with per-example timeout, fresh context isolation, and multi-metric aggregation into structured EvaluationResult.**

## What Happened

Built two modules in a single task:

**`benchmark.py`** — `BenchmarkExample` and `ScoringResult` dataclasses, built-in scorer registry (`exact_match`, `includes`), and `Benchmark` class with `from_file()` JSON loader. Scorer resolution checks built-in names first, then filesystem paths for custom `.py` files loaded via compile()+exec() (matching S01's pipeline loader pattern D014).

**`evaluation.py`** — `ExampleResult` and `EvaluationResult` frozen dataclasses, and `Evaluator` class. For each benchmark example: creates a fresh `PrimitivesContext` via factory callable (no metric bleed), runs the pipeline through `PipelineRunner`, applies the scoring function, and enforces per-example timeout via `ThreadPoolExecutor`. Scoring errors and pipeline failures are caught per-example (score 0.0, error recorded) — never crash the evaluation. Primary score = mean of per-example scores. Metrics aggregated across all examples.

The timeout implementation initially used `ThreadPoolExecutor` as a context manager, but its `__exit__` blocked waiting for timed-out threads. Fixed by using explicit `shutdown(wait=False, cancel_futures=True)` in a try/finally.

## Verification

- `pytest tests/test_benchmark.py tests/test_evaluation.py -v` — **29 passed** (19 benchmark + 10 evaluation)
- Boundary contract import check: `from autoagent.evaluation import Evaluator, EvaluationResult, ExampleResult` and `from autoagent.benchmark import Benchmark, BenchmarkExample` — passed
- Test coverage: scorers (exact_match, includes, stringification), JSON loading, auto-generated IDs, custom scorer file resolution, evaluator happy path, mixed results, per-example timeout, scoring error handling, pipeline failure recording, fresh context isolation, metric aggregation, boundary type imports
- Full suite: 105 tests passing, zero regressions

## Requirements Advanced

- R008 (Benchmark-Driven Evaluation) — benchmark loader and evaluator implemented; every iteration can now be scored against an explicit benchmark dataset + scoring function
- R003 (Instrumented Primitives) — metrics from instrumented primitives are aggregated per-example and across the full evaluation
- R022 (Fixed Evaluation Time Budget) — per-example timeout enforced via ThreadPoolExecutor; timeout → score 0.0 with error="timeout"

## Requirements Validated

None — R008 and R022 are advanced but full validation requires integration with the optimization loop (S05).

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

- Added `tests/fixtures/slow_pipeline.py` (sleeps 10s) and `tests/fixtures/passthrough_pipeline.py` (returns input unchanged) as test fixtures — not in original plan but needed for timeout and scoring error test coverage.

## Known Limitations

- Timeout is per-example, not per-evaluation. No aggregate wall-clock budget for the full benchmark run (deferred — S06 handles budget).
- ThreadPoolExecutor timeout threads may linger briefly after shutdown(wait=False) — Python limitation, not a practical issue for evaluation cadence.
- No data leakage checking yet (R009 deferred to M003/S04).

## Follow-ups

None — downstream work is S04 (archive) and S05 (loop), both already planned.

## Files Created/Modified

- `src/autoagent/benchmark.py` — Benchmark loader, BenchmarkExample, ScoringResult, built-in scorer registry, custom scorer file loading
- `src/autoagent/evaluation.py` — Evaluator, ExampleResult, EvaluationResult with per-example timeout and metric aggregation
- `tests/test_benchmark.py` — 19 tests for benchmark loading, scorers, error handling
- `tests/test_evaluation.py` — 10 tests for evaluator happy path, timeout, errors, context isolation, metrics
- `tests/fixtures/toy_benchmark.json` — 5-example benchmark dataset
- `tests/fixtures/toy_scorer.py` — Custom case-insensitive scorer
- `tests/fixtures/slow_pipeline.py` — Sleeps 10s, used for timeout testing
- `tests/fixtures/passthrough_pipeline.py` — Returns input unchanged, used for scoring error testing

## Forward Intelligence

### What the next slice should know
- `EvaluationResult` is the boundary type — it contains `primary_score`, `metrics` (aggregated MetricsSnapshot), `per_example_results`, `benchmark_id`, `duration_ms`, and `timestamp`
- `Evaluator` takes a `primitives_factory` callable that returns a fresh `PrimitivesContext` — S05's loop must supply this factory
- Import paths: `from autoagent.evaluation import Evaluator, EvaluationResult` and `from autoagent.benchmark import Benchmark`

### What's fragile
- ThreadPoolExecutor timeout threads can't be forcibly killed in Python — if a pipeline hangs on I/O, the thread lingers until the I/O completes. Not a problem with mock providers but could matter with real network calls in S05.

### Authoritative diagnostics
- `EvaluationResult.per_example_results` — iterate to find which examples failed/timed-out/errored, with per-example duration_ms and metrics
- `ExampleResult.error` field distinguishes timeout, scoring errors, and pipeline failures

### What assumptions changed
- None — S01's boundary contract worked exactly as documented in the boundary map.
