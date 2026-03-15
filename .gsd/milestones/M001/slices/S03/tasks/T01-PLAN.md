---
estimated_steps: 5
estimated_files: 6
---

# T01: Build benchmark loader, evaluator, and scoring with per-example timeout

**Slice:** S03 — Evaluation & Benchmark
**Milestone:** M001

## Description

Build the two core modules for S03: `benchmark.py` (dataset loading + scoring function resolution) and `evaluation.py` (per-example pipeline execution with timeout enforcement and metric aggregation). These are tightly coupled — the evaluator's only purpose is running a pipeline against a benchmark — so building and testing them together is natural.

The key design points: `Benchmark` loads a JSON array of `{input, expected}` objects and resolves a scoring function (built-in name or path to custom `.py` file). `Evaluator` runs the pipeline once per example with a fresh `PrimitivesContext` (preventing metric bleed), enforces per-example timeout via `ThreadPoolExecutor`, catches scoring errors gracefully, and aggregates everything into an `EvaluationResult` that S04/S05 will consume.

## Steps

1. Create `src/autoagent/benchmark.py`: `BenchmarkExample` dataclass (input, expected, id), `ScoringResult` dataclass (score, error), built-in scorer registry (`exact_match`, `includes`), `Benchmark` class with `from_file(path, scoring_function)` that loads JSON examples and resolves scorer
2. Create `src/autoagent/evaluation.py`: `ExampleResult` dataclass (example_id, score, success, error, duration_ms, metrics), `EvaluationResult` dataclass (primary_score, per_example_results, metrics, benchmark_id, duration_ms, num_examples, num_failures), `Evaluator` class with `evaluate(pipeline_path, benchmark, timeout_per_example, primitives_factory)` that runs each example through `PipelineRunner` with fresh `PrimitivesContext`, applies scorer, handles timeout via `ThreadPoolExecutor`
3. Create test fixtures: `tests/fixtures/toy_benchmark.json` (5 examples with input/expected pairs matching toy_pipeline's mock behavior) and `tests/fixtures/toy_scorer.py` (custom scorer for testing file-based resolution)
4. Create `tests/test_benchmark.py`: test JSON loading, built-in scorers, custom scorer file resolution, missing file errors, invalid JSON handling, unknown scorer name
5. Create `tests/test_evaluation.py`: test happy path (all examples pass), mixed results, per-example timeout enforcement (use a slow pipeline fixture), scoring error handling, fresh context per example verification, metric aggregation correctness, boundary contract import check

## Must-Haves

- [ ] `Benchmark.from_file()` loads JSON and resolves scoring functions (built-in + custom file)
- [ ] Built-in scorers: `exact_match` (str equality), `includes` (substring match)
- [ ] `Evaluator.evaluate()` returns `EvaluationResult` with primary_score = mean of per-example scores
- [ ] Per-example timeout via `ThreadPoolExecutor` — `TimeoutError` → score 0.0, error="timeout" (R022)
- [ ] Fresh `PrimitivesContext` per example — no metric bleed
- [ ] Scoring function errors caught per-example — error recorded, score 0.0, evaluation continues
- [ ] `EvaluationResult` is the boundary contract type for S04/S05

## Verification

- `pytest tests/test_benchmark.py -v` — all tests pass
- `pytest tests/test_evaluation.py -v` — all tests pass
- `python -c "from autoagent.evaluation import Evaluator, EvaluationResult, ExampleResult; from autoagent.benchmark import Benchmark, BenchmarkExample; print('boundary contracts importable')"` — succeeds
- `pytest tests/ -v` — full suite passes (no regressions)

## Observability Impact

- Signals added: `EvaluationResult.per_example_results` list — each entry has score, success, error, duration_ms, and per-example metrics snapshot
- How a future agent inspects this: iterate `per_example_results` to find failing/slow/timeout examples; check `.metrics` for aggregate cost/latency
- Failure state exposed: timed-out examples have `error="timeout"`; scorer failures have `error="scoring_error: {detail}"`; pipeline failures have `error` from `PipelineResult.error`

## Inputs

- `src/autoagent/pipeline.py` — `PipelineRunner.run()` returns `PipelineResult`, never raises
- `src/autoagent/primitives.py` — `PrimitivesContext`, `MetricsCollector`, `MockLLM`, `MockRetriever` for test fixtures
- `src/autoagent/types.py` — `MetricsSnapshot`, `PipelineResult`, `ErrorInfo`
- `tests/fixtures/toy_pipeline.py` — reference for pipeline.py structure
- S01 forward intelligence: compile()+exec() module loading, frozen MetricsSnapshot, PipelineRunner never raises

## Expected Output

- `src/autoagent/benchmark.py` — `BenchmarkExample`, `Benchmark`, built-in scorer registry, custom scorer file loading
- `src/autoagent/evaluation.py` — `ExampleResult`, `EvaluationResult`, `Evaluator` with per-example timeout
- `tests/test_benchmark.py` — unit tests for benchmark loading and scoring
- `tests/test_evaluation.py` — unit + integration tests for evaluator with timeout and error handling
- `tests/fixtures/toy_benchmark.json` — test benchmark dataset
- `tests/fixtures/toy_scorer.py` — custom scoring function fixture
