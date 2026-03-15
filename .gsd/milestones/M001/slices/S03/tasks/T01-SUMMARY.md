---
id: T01
parent: S03
milestone: M001
provides:
  - Benchmark loader with JSON parsing and scorer resolution (built-in + custom file)
  - Evaluator with per-example timeout, fresh context isolation, and metric aggregation
  - EvaluationResult boundary contract type for S04/S05
key_files:
  - src/autoagent/benchmark.py
  - src/autoagent/evaluation.py
  - tests/test_benchmark.py
  - tests/test_evaluation.py
  - tests/fixtures/toy_benchmark.json
  - tests/fixtures/toy_scorer.py
key_decisions:
  - ThreadPoolExecutor with shutdown(wait=False, cancel_futures=True) for timeout — avoids blocking on timed-out threads
  - Scorer resolution: built-in name lookup first, then filesystem path check, then error
  - compile()+exec() for custom scorer loading — matches pipeline loader pattern from S01
patterns_established:
  - ScorerFn callable protocol: (output, expected) -> ScoringResult
  - Per-example isolation via primitives_factory callable
  - EvaluationResult as the standard evaluation output type for downstream consumption
observability_surfaces:
  - EvaluationResult.per_example_results — score, success, error, duration_ms, metrics per example
  - Timeout examples have error="timeout", scoring failures have error="scoring_error: {detail}"
  - Pipeline failures propagate error.message from PipelineResult.error
duration: 15m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Build benchmark loader, evaluator, and scoring with per-example timeout

**Built `benchmark.py` and `evaluation.py` — benchmark loading with scorer resolution, evaluator with per-example timeout via ThreadPoolExecutor, fresh context isolation, and metric aggregation into `EvaluationResult`.**

## What Happened

Built two modules:

1. **`benchmark.py`**: `BenchmarkExample` dataclass, `ScoringResult` dataclass, built-in scorer registry (`exact_match`, `includes`), `Benchmark` class with `from_file()` that loads a JSON array and resolves scoring functions (built-in name or path to custom `.py` file via compile+exec).

2. **`evaluation.py`**: `ExampleResult` and `EvaluationResult` frozen dataclasses, `Evaluator` class that runs each benchmark example through `PipelineRunner` with a fresh `PrimitivesContext` (via factory callable), enforces per-example timeout through `ThreadPoolExecutor`, catches scoring errors per-example, and aggregates metrics. Primary score = mean of per-example scores.

Initial timeout implementation used `with ThreadPoolExecutor` context manager which blocked on `__exit__` waiting for timed-out threads. Fixed by using explicit `shutdown(wait=False, cancel_futures=True)` in a `try/finally`.

## Verification

- `pytest tests/test_benchmark.py -v` — **19 passed** (scorers, JSON loading, custom file resolution, error paths)
- `pytest tests/test_evaluation.py -v` — **10 passed** (happy path, mixed results, timeout, scoring errors, pipeline failures, fresh context, metric aggregation, boundary contracts)
- `python -c "from autoagent.evaluation import Evaluator, EvaluationResult, ExampleResult; from autoagent.benchmark import Benchmark, BenchmarkExample; print('boundary contracts importable')"` — **passed**
- `pytest tests/ -v` — **105 passed**, zero regressions

**Slice-level verification:** All checks pass. This is the only task in S03.

## Diagnostics

- Iterate `EvaluationResult.per_example_results` to find failing/slow/timeout examples
- Check `.error` field: `"timeout"` for timed-out, `"scoring_error: {detail}"` for scorer failures, pipeline error message for pipeline crashes
- `EvaluationResult.metrics` for aggregate cost/latency across all examples
- `ExampleResult.metrics` for per-example cost/latency breakdown

## Deviations

- Added `tests/fixtures/slow_pipeline.py` and `tests/fixtures/passthrough_pipeline.py` as test fixtures (not in original plan but needed for timeout and scoring error tests)

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/benchmark.py` — Benchmark loader, BenchmarkExample, ScoringResult, built-in scorer registry, custom scorer file loading
- `src/autoagent/evaluation.py` — Evaluator, ExampleResult, EvaluationResult with per-example timeout and metric aggregation
- `tests/test_benchmark.py` — 19 tests for benchmark loading, scorers, and error handling
- `tests/test_evaluation.py` — 10 tests for evaluator happy path, timeout, errors, context isolation, metrics
- `tests/fixtures/toy_benchmark.json` — 5-example benchmark dataset for toy_pipeline
- `tests/fixtures/toy_scorer.py` — Custom case-insensitive scorer for file-based resolution testing
- `tests/fixtures/slow_pipeline.py` — Sleeps 10s, used for timeout testing
- `tests/fixtures/passthrough_pipeline.py` — Returns input unchanged, used for scoring error testing
