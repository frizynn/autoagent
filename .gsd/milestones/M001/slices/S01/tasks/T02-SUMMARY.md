---
id: T02
parent: S01
milestone: M001
provides:
  - PipelineRunner class (autoagent.pipeline) — dynamic pipeline loading and execution
  - toy_pipeline.py fixture — S01 demo artifact proving end-to-end metrics flow
  - bad_pipeline.py, crash_pipeline.py — error-path fixtures
key_files:
  - src/autoagent/pipeline.py
  - tests/test_pipeline_runner.py
  - tests/fixtures/toy_pipeline.py
  - tests/fixtures/bad_pipeline.py
  - tests/fixtures/crash_pipeline.py
key_decisions:
  - "compile() + exec() instead of importlib.util.spec_from_file_location — importlib's SourceFileLoader uses bytecode cache (.pyc) which defeats fresh-load semantics when the same file path is loaded twice in one process"
patterns_established:
  - "PipelineRunner never raises — all failures produce PipelineResult(success=False) with structured ErrorInfo"
  - "Path validation resolves symlinks before checking allowed_root containment"
  - "Internal _PathError exception carries ErrorInfo for clean control flow in validation/load stages"
observability_surfaces:
  - "PipelineResult.error — ErrorInfo(type, message, traceback) for any failure mode"
  - "PipelineResult.duration_ms — wall-clock time captured even on failure"
  - "PipelineResult.metrics — aggregated MetricsSnapshot from collector after successful execution"
duration: 20min
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T02: Implement PipelineRunner and prove end-to-end execution

**Built PipelineRunner with dynamic module loading, path validation, structured error handling, and proved end-to-end metrics flow through toy RAG pipeline.**

## What Happened

Implemented `PipelineRunner` in `src/autoagent/pipeline.py`. The runner takes an `allowed_root` path, validates pipeline paths against it (rejecting non-.py files and paths outside root after symlink resolution), loads the module fresh every invocation, verifies a callable `run` attribute exists, and executes it with the provided `PrimitivesContext`. All failure modes (missing file, missing run(), runtime exception, bad path) produce a valid `PipelineResult(success=False)` with structured `ErrorInfo` — the runner never raises.

Key discovery: `importlib.util.spec_from_file_location` uses Python's bytecode cache (`.pyc`), which means loading the same file path twice in one process returns stale code even with a unique module name. Switched to `compile()` + `exec()` which reads source directly and guarantees fresh loads. The fresh-load test caught this immediately.

Created three fixtures: `toy_pipeline.py` (mock RAG that calls both LLM and Retriever), `bad_pipeline.py` (no run function), `crash_pipeline.py` (raises ValueError).

## Verification

- `pytest tests/test_pipeline_runner.py -v` — 9/9 passed (success path, missing file, missing run, exception, path-outside-root, non-.py rejection, fresh module loading)
- `pytest tests/ -v` — 43/43 passed (T01 + T02 full suite)
- Slice verification (all 4 checks pass):
  - `pytest tests/test_primitives.py -v` ✅
  - `pytest tests/test_pipeline_runner.py -v` ✅
  - `python -c "from autoagent.types import MetricsSnapshot, PipelineResult; from autoagent.primitives import LLM, Retriever; print('boundary contracts importable')"` ✅
  - `python -c "from autoagent.types import PipelineResult, ErrorInfo; r = PipelineResult(...); assert not r.success; assert r.error.type == 'ValueError'; print('failure state structured')"` ✅
- toy_pipeline.py produces PipelineResult with `metrics.tokens_in=15, tokens_out=20, cost_usd>0, latency_ms>0` ✅

## Diagnostics

- `result.success` — boolean, check first
- `result.error.type` / `.message` / `.traceback` — structured failure info when `success=False`
- `result.metrics` — aggregated MetricsSnapshot when `success=True`
- `result.duration_ms` — wall-clock duration, always populated (even on failure)

## Deviations

Switched from `importlib.util.spec_from_file_location` to `compile()` + `exec()` for module loading. The plan specified importlib but its bytecode cache prevents true fresh loads. The `compile()` approach is simpler and actually works. Added `crash_pipeline.py` as an additional fixture beyond `bad_pipeline.py`.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/pipeline.py` — PipelineRunner class with run(), path validation, error handling
- `tests/test_pipeline_runner.py` — 9 tests covering success, errors, path validation, fresh loading
- `tests/fixtures/toy_pipeline.py` — toy RAG pipeline (S01 demo artifact)
- `tests/fixtures/bad_pipeline.py` — missing run() fixture
- `tests/fixtures/crash_pipeline.py` — raises ValueError fixture
