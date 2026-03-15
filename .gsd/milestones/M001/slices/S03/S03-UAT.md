# S03: Evaluation & Benchmark — UAT

**Milestone:** M001
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: All verification is via pytest with mock providers — no live LLM calls or runtime services needed. The boundary contracts are import-checked and type-verified.

## Preconditions

- Python venv active: `.venv/bin/python` available
- Package installed in dev mode: `pip install -e .` has been run
- S01 modules exist: `src/autoagent/primitives.py`, `src/autoagent/pipeline.py`, `src/autoagent/types.py`
- Test fixtures present: `tests/fixtures/toy_benchmark.json`, `tests/fixtures/toy_scorer.py`, `tests/fixtures/slow_pipeline.py`, `tests/fixtures/passthrough_pipeline.py`

## Smoke Test

```bash
.venv/bin/python -c "from autoagent.evaluation import Evaluator, EvaluationResult; from autoagent.benchmark import Benchmark, BenchmarkExample; print('OK')"
```
Expected: prints `OK` with exit code 0.

## Test Cases

### 1. Benchmark loads from JSON with built-in scorer

1. Run `.venv/bin/python -m pytest tests/test_benchmark.py::TestBenchmarkFromFile::test_loads_toy_benchmark -v`
2. **Expected:** Test passes. Benchmark has 5 examples, each with `input`, `expected`, and an `id`.

### 2. Custom scorer resolves from file path

1. Run `.venv/bin/python -m pytest tests/test_benchmark.py::TestBenchmarkFromFile::test_custom_scorer_file -v`
2. **Expected:** Test passes. Scorer loaded from `tests/fixtures/toy_scorer.py` via compile()+exec(), produces `ScoringResult` with score and explanation.

### 3. Evaluator returns correct primary_score for all-pass benchmark

1. Run `.venv/bin/python -m pytest tests/test_evaluation.py::TestEvaluatorHappyPath::test_all_examples_pass -v`
2. **Expected:** Test passes. `EvaluationResult.primary_score == 1.0`, all `per_example_results` have `success=True`.

### 4. Evaluator handles mixed pass/fail results

1. Run `.venv/bin/python -m pytest tests/test_evaluation.py::TestEvaluatorHappyPath::test_mixed_results -v`
2. **Expected:** Test passes. `primary_score` is the mean of per-example scores (some 1.0, some 0.0).

### 5. Per-example timeout enforcement

1. Run `.venv/bin/python -m pytest tests/test_evaluation.py::TestTimeout::test_timeout_produces_score_zero -v`
2. **Expected:** Test passes. Timed-out example has `score=0.0`, `success=False`, `error="timeout"`. Wall-clock time is close to timeout value, not pipeline execution time (10s).

### 6. Scoring error caught per-example

1. Run `.venv/bin/python -m pytest tests/test_evaluation.py::TestScoringErrors::test_scorer_exception_caught -v`
2. **Expected:** Test passes. Example with bad scorer has `score=0.0`, `error` starts with `"scoring_error:"`. Other examples unaffected.

### 7. Fresh PrimitivesContext per example

1. Run `.venv/bin/python -m pytest tests/test_evaluation.py::TestFreshContext::test_no_metric_bleed_between_examples -v`
2. **Expected:** Test passes. Each example's metrics reflect only that example's execution, not accumulated from previous examples.

### 8. Metric aggregation across examples

1. Run `.venv/bin/python -m pytest tests/test_evaluation.py::TestMetricAggregation::test_aggregated_metrics_sum_across_examples -v`
2. **Expected:** Test passes. `EvaluationResult.metrics` aggregates latency, tokens, and cost across all examples.

### 9. Full test suite — no regressions

1. Run `.venv/bin/python -m pytest tests/ -v`
2. **Expected:** 105+ tests pass, zero failures.

## Edge Cases

### Unknown scorer name raises clear error

1. Run `.venv/bin/python -m pytest tests/test_benchmark.py::TestBenchmarkErrors::test_unknown_scorer_name -v`
2. **Expected:** Test passes. `ValueError` raised with descriptive message about unknown scorer.

### Pipeline failure recorded without crashing evaluation

1. Run `.venv/bin/python -m pytest tests/test_evaluation.py::TestScoringErrors::test_pipeline_failure_recorded -v`
2. **Expected:** Test passes. Failed pipeline example has `success=False`, error message from pipeline, score 0.0. Other examples still evaluated.

### Missing benchmark file raises FileNotFoundError

1. Run `.venv/bin/python -m pytest tests/test_benchmark.py::TestBenchmarkErrors::test_missing_file -v`
2. **Expected:** Test passes. Clear error when benchmark JSON doesn't exist.

## Failure Signals

- Any test failure in `tests/test_benchmark.py` or `tests/test_evaluation.py`
- Import errors on `from autoagent.evaluation import Evaluator, EvaluationResult`
- Import errors on `from autoagent.benchmark import Benchmark, BenchmarkExample`
- Timeout test taking >5s (should complete in ~1-2s with the configured timeout)
- Regressions in S01/S02 tests (total count drops below 76)

## Requirements Proved By This UAT

- R008 (Benchmark-Driven Evaluation) — benchmark loading and evaluation against dataset with scoring function demonstrated
- R022 (Fixed Evaluation Time Budget) — per-example timeout enforcement with score=0.0 on timeout
- R003 (Instrumented Primitives, supporting) — metrics from instrumented primitives captured and aggregated in evaluation results

## Not Proven By This UAT

- R009 (Data Leakage Guardrail) — no leakage checking implemented yet (M003/S04)
- R010 (Multi-Metric Pareto Evaluation) — metrics captured but Pareto enforcement deferred to M003/S05
- Integration with the optimization loop (S05) — evaluation works standalone but not yet wired into propose→evaluate→keep/discard
- Real LLM provider evaluation — all tests use mock providers

## Notes for Tester

- The timeout test uses `slow_pipeline.py` which sleeps for 10s. The test configures a ~1s timeout. If the test takes significantly longer than 2s, the `shutdown(wait=False)` pattern may not be working correctly.
- All scorers return `ScoringResult(score=float, explanation=str)` — check explanation strings for meaningful content.
- `toy_benchmark.json` has 5 examples designed for the toy_pipeline from S01 fixtures. If S01 fixtures change, these may need updating.
