# S03: Evaluation & Benchmark — Research

**Date:** 2026-03-14

## Summary

S03 builds two modules: `benchmark.py` (loading datasets + scoring functions) and `evaluation.py` (running a pipeline against a benchmark, capturing multi-metric results with timeout enforcement). The existing codebase provides clean seams — `PipelineRunner` returns `PipelineResult` with `MetricsSnapshot`, and `ProjectConfig` already has `benchmark.dataset_path` and `benchmark.scoring_function` fields waiting to be consumed.

The core design is: a `Benchmark` loads a list of `BenchmarkExample` dicts (input + expected output) from a JSON file and resolves a `ScoringFunction` (callable that takes output + expected → float). The `Evaluator` runs the pipeline once per example with a per-example timeout (R022), collects per-example scores, aggregates into `EvaluationResult` with primary_score + full MetricsSnapshot + timing. No external dependencies needed — `concurrent.futures` handles timeout enforcement, everything else is stdlib.

The main design tension is where scoring functions live. Options: (a) user provides a Python file with a `score()` function, (b) built-in named scorers (exact_match, f1, etc.), (c) both. Going with (c) — built-in scorers for common cases, user can point to a custom `.py` file for domain-specific scoring. This matches the config's `scoring_function` field which can be either a name or a path.

## Recommendation

Build two modules with clear responsibilities:

- **`benchmark.py`**: `BenchmarkExample` dataclass, `Benchmark` class that loads from JSON, resolves scoring functions (built-in registry + custom file loading). Built-in scorers: `exact_match`, `includes` (substring), `llm_judge` (placeholder for later).
- **`evaluation.py`**: `EvaluationResult` dataclass, `Evaluator` class that takes a benchmark + pipeline path, runs each example through `PipelineRunner` with per-example timeout via `concurrent.futures.ThreadPoolExecutor`, aggregates scores and metrics.

Timeout enforcement (R022) uses `concurrent.futures.ThreadPoolExecutor.submit()` with `future.result(timeout=N)`. ThreadPool rather than ProcessPool because pipeline.py uses in-process primitives with shared `MetricsCollector` — a subprocess boundary would lose metrics. The timeout won't kill the thread (Python limitation), but it will abandon the result and mark the example as failed. For truly stuck pipelines, S06's process-level kill handles the escape hatch.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Timeout enforcement | `concurrent.futures.ThreadPoolExecutor` | stdlib, cleaner than signal-based approaches, works cross-platform |
| JSON dataset loading | `json` stdlib | Zero deps, benchmark files are JSON per D003 |
| Scoring functions | Custom but simple — no framework needed | These are 5-line functions; pulling in sklearn or similar would violate zero-deps |

## Existing Code and Patterns

- `src/autoagent/pipeline.py` — `PipelineRunner.run()` returns `PipelineResult`, never raises. S03 wraps this per-example. The `timeout` kwarg is already reserved (`timeout: float | None = None` with comment "reserved for S03").
- `src/autoagent/types.py` — `MetricsSnapshot` (frozen, `.asdict()`), `PipelineResult` (mutable, has `.metrics`, `.success`, `.error`, `.duration_ms`). S03's `EvaluationResult` will compose these.
- `src/autoagent/primitives.py` — `PrimitivesContext`, `MetricsCollector`, `MockLLM`, `MockRetriever`. S03 tests will use mocks to avoid real LLM calls.
- `src/autoagent/state.py` — `ProjectConfig.benchmark` dict has `dataset_path` and `scoring_function` fields. S03's `Benchmark.from_config()` will consume this.
- `tests/fixtures/toy_pipeline.py` — working pipeline fixture. S03 needs its own benchmark fixture (JSON dataset + toy scoring function).

## Constraints

- **Zero runtime dependencies** — all scoring, loading, timeout must be stdlib-only
- **MetricsCollector is in-process** — timeout enforcement can't use subprocess isolation (metrics would be lost). ThreadPool + `future.result(timeout)` is the mechanism.
- **Thread-based timeout doesn't kill the thread** — a truly hung pipeline will leak a thread. Acceptable for M001; S06 process-level kill is the real escape hatch.
- **PipelineRunner never raises** — S03 doesn't need try/except around runner calls; check `PipelineResult.success` instead
- **Frozen MetricsSnapshot** — can't mutate after creation; aggregate via `MetricsCollector.aggregate()` pattern

## Common Pitfalls

- **Thread timeout doesn't terminate execution** — `future.result(timeout=N)` raises `TimeoutError` but the thread keeps running. Must document this limitation and not pretend we have hard termination. For M001 this is acceptable.
- **Scoring function errors crashing evaluation** — A bad scoring function shouldn't take down the entire benchmark run. Wrap each `score()` call, treat errors as score=0.0 with error recorded.
- **Pipeline metrics not reset between examples** — `MetricsCollector` accumulates across calls. Must create a fresh `PrimitivesContext` per example or reset the collector, otherwise metrics from example N bleed into example N+1. Per-example fresh context is cleaner.
- **Large benchmark datasets** — No streaming/batching in M001. If someone loads a 10K example benchmark, it all sits in memory. Fine for M001; note as known limitation.
- **Scoring function resolution ambiguity** — "exact_match" could be a built-in name or a file path. Resolve order: check built-in registry first, then treat as file path. Document the convention.

## Open Risks

- **Thread-based timeout is soft** — If a pipeline makes a blocking API call with no internal timeout, the thread will hang until the API responds. The `TimeoutError` fires but the thread leaks. Real mitigation is in S06 (process-level watchdog). For M001, document and accept.
- **Scoring function loading uses same compile()+exec() pattern as pipeline loading** — custom scoring functions are arbitrary Python. Same security posture as pipeline.py itself (addressed by R021/sandbox in M003).

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Python stdlib (concurrent.futures, json, dataclasses) | N/A | No skill needed — stdlib only |

No external libraries or frameworks involved. No skills to discover.

## Sources

- S01 summary and source code (boundary contracts, PipelineRunner API, MetricsSnapshot)
- S02 state.py (ProjectConfig.benchmark structure)
- Python docs: concurrent.futures.ThreadPoolExecutor timeout semantics
- Boundary map in M001-ROADMAP.md (S03 produces/consumes contracts)
