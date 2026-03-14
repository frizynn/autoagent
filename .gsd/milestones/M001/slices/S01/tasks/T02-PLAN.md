---
estimated_steps: 5
estimated_files: 4
---

# T02: Implement PipelineRunner and prove end-to-end execution

**Slice:** S01 — Pipeline Execution Engine
**Milestone:** M001

## Description

Build PipelineRunner — the component that dynamically loads a user's pipeline.py from disk, executes its `run()` function with pre-configured instrumented primitives, and returns a PipelineResult with aggregated metrics. This closes the S01 demo: a toy RAG pipeline runs through the runner and produces real metrics. Includes path validation (single-file constraint), fresh module loading (no caching), and structured error handling for all failure modes.

## Steps

1. Create `src/autoagent/pipeline.py` with `PipelineRunner` class. Constructor takes an optional `allowed_root` path (defaults to cwd). `run(pipeline_path, input_data, primitives_context)` method: resolve path, validate it's under allowed_root and is a .py file (reject symlinks pointing outside root), load module via `importlib.util.spec_from_file_location` + `spec.loader.exec_module` with a fresh module object (never add to `sys.modules`), verify module has callable `run` attribute, call `module.run(input_data, primitives_context)`, wrap entire execution in `time.perf_counter` for total duration, return PipelineResult. Every call creates a new spec+module — no caching.
2. Implement error handling: missing file → PipelineResult(success=False, error=ErrorInfo), no `run()` function → structured error, exception during execution → capture in ErrorInfo with traceback string, timeout (optional, for future S03 use — not enforced in S01 but the parameter exists). All errors produce a valid PipelineResult, never raise.
3. Create `tests/fixtures/toy_pipeline.py` — a mock RAG pipeline: calls `primitives.llm.complete("Summarize: {context}")` and `primitives.retriever.retrieve("test query")`, combines results, returns a dict with "answer" key. This is the proof artifact for the S01 demo.
4. Create `tests/fixtures/bad_pipeline.py` (missing run function), `tests/fixtures/crash_pipeline.py` (run() raises ValueError). These exercise error paths.
5. Write `tests/test_pipeline_runner.py`: test successful execution of toy_pipeline.py with mock primitives returns PipelineResult with success=True, metrics with latency>0 and tokens>0 and cost>0; test missing file returns structured error; test missing run() returns structured error; test exception in pipeline returns structured error with traceback; test path outside allowed_root is rejected; test fresh module loading (write a temp pipeline, run it, modify the file, run again — second run sees the new code).

## Must-Haves

- [ ] PipelineRunner.run() loads and executes a pipeline.py file, returns PipelineResult
- [ ] Fresh module load every invocation — no stale code from previous runs
- [ ] Single-file path validation: rejects paths outside allowed_root
- [ ] Missing file, missing run(), and runtime exceptions all produce PipelineResult(success=False) with ErrorInfo
- [ ] toy_pipeline.py runs with mock primitives and produces aggregated metrics (latency, tokens, cost all > 0)
- [ ] All tests pass

## Observability Impact

- Signals added: PipelineResult.error contains ErrorInfo(type, message, traceback) for any failure — structured, grepable
- How a future agent inspects this: check `result.success`, read `result.error.message` and `result.error.traceback`; check `result.metrics` for performance data
- Failure state exposed: exception type + message + full traceback preserved in result object; duration_ms captured even on failure

## Verification

- `pytest tests/test_pipeline_runner.py -v` — all tests pass
- `pytest tests/ -v` — full suite (T01 + T02 tests) still green
- The toy_pipeline.py fixture produces a PipelineResult where `metrics.tokens_in > 0`, `metrics.tokens_out > 0`, `metrics.cost_usd > 0`, `metrics.latency_ms > 0`

## Inputs

- `src/autoagent/types.py` — MetricsSnapshot, PipelineResult, ErrorInfo from T01
- `src/autoagent/primitives.py` — MockLLM, MockRetriever, PrimitivesContext, MetricsCollector from T01
- `tests/test_primitives.py` — T01 tests (must still pass)

## Expected Output

- `src/autoagent/pipeline.py` — PipelineRunner class with run(), path validation, error handling
- `tests/test_pipeline_runner.py` — comprehensive test suite
- `tests/fixtures/toy_pipeline.py` — toy RAG pipeline (S01 demo artifact)
- `tests/fixtures/bad_pipeline.py` — missing run() fixture
- `tests/fixtures/crash_pipeline.py` — exception fixture
