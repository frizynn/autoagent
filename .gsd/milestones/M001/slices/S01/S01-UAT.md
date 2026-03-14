# S01: Pipeline Execution Engine — UAT

**Milestone:** M001
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: S01 produces no UI or runtime service — it's a library layer. All verification is through imports, pytest, and inline script execution.

## Preconditions

- Python 3.11+ available (project venv at `.venv/`)
- Package installed in editable mode (`pip install -e ".[dev]"`)
- Working directory is the project root

## Smoke Test

```bash
.venv/bin/python -c "from autoagent.types import MetricsSnapshot, PipelineResult; from autoagent.primitives import LLM, Retriever; from autoagent.pipeline import PipelineRunner; print('all S01 modules importable')"
```
Expected: prints "all S01 modules importable" with exit code 0.

## Test Cases

### 1. Toy RAG pipeline produces structured metrics

1. Run: `.venv/bin/python -m pytest tests/test_pipeline_runner.py::TestSuccessfulExecution -v`
2. **Expected:** All 3 tests pass — success=True, metrics have tokens_in=15/tokens_out=20/cost>0/latency>0, duration_ms>0

### 2. Error paths never crash the runner

1. Run: `.venv/bin/python -m pytest tests/test_pipeline_runner.py::TestErrorPaths -v`
2. **Expected:** All 5 tests pass — missing file, missing run(), exception, path-outside-root, non-.py all return PipelineResult(success=False) with structured ErrorInfo

### 3. Fresh module loading (mutation detection)

1. Run: `.venv/bin/python -m pytest tests/test_pipeline_runner.py::TestFreshModuleLoading -v`
2. **Expected:** Test passes — modifying pipeline.py between two .run() calls produces different output, proving no stale cache

### 4. MetricsCollector aggregates multi-call pipelines

1. Run: `.venv/bin/python -m pytest tests/test_primitives.py::TestMetricsCollector -v`
2. **Expected:** All 4 tests pass — empty aggregate returns zeros, multi-call sums correctly, mixed providers aggregate, reset clears

### 5. Boundary contracts importable by downstream slices

1. Run:
   ```bash
   .venv/bin/python -c "from autoagent.types import MetricsSnapshot, PipelineResult; from autoagent.primitives import LLM, Retriever; print('boundary contracts importable')"
   ```
2. **Expected:** Prints message, exit code 0

### 6. Failure state is structured and inspectable

1. Run:
   ```bash
   .venv/bin/python -c "
   from autoagent.types import PipelineResult, ErrorInfo
   r = PipelineResult(output=None, metrics=None, success=False, error=ErrorInfo(type='ValueError', message='test', traceback='...'), duration_ms=0.0)
   assert not r.success
   assert r.error.type == 'ValueError'
   assert r.error.message == 'test'
   print('failure state structured')
   "
   ```
2. **Expected:** Prints "failure state structured", exit code 0

### 7. Full test suite passes

1. Run: `.venv/bin/python -m pytest tests/ -v`
2. **Expected:** 41/41 tests pass, no warnings

## Edge Cases

### OpenAI SDK missing produces actionable error

1. Ensure `openai` is not installed in the venv
2. Run:
   ```bash
   .venv/bin/python -c "
   from autoagent.primitives import OpenAILLM, MetricsCollector
   llm = OpenAILLM(model='gpt-4o', collector=MetricsCollector())
   try:
       llm.complete('test')
       assert False, 'should have raised'
   except ImportError as e:
       assert 'pip install openai' in str(e)
       print('actionable import error')
   "
   ```
3. **Expected:** Prints "actionable import error" — the error message tells the user exactly what to install

### Pipeline path traversal rejected

1. Run:
   ```bash
   .venv/bin/python -c "
   from autoagent.pipeline import PipelineRunner
   runner = PipelineRunner(allowed_root='/tmp/safe')
   result = runner.run('/etc/passwd', {})
   assert not result.success
   assert 'outside allowed root' in result.error.message or 'must have .py extension' in result.error.message
   print('path traversal blocked')
   "
   ```
2. **Expected:** Prints "path traversal blocked" — runner refuses to load files outside allowed_root

### MockRetriever returns copies (mutation safety)

1. Run: `.venv/bin/python -m pytest tests/test_primitives.py::TestMockRetriever::test_returns_copy_not_reference -v`
2. **Expected:** Test passes — mutating returned docs doesn't affect subsequent retrieve() calls

## Failure Signals

- Any test in `tests/test_primitives.py` or `tests/test_pipeline_runner.py` fails
- Import of `autoagent.types`, `autoagent.primitives`, or `autoagent.pipeline` raises ModuleNotFoundError
- PipelineRunner.run() raises an exception instead of returning PipelineResult(success=False)
- MetricsSnapshot has zero latency/tokens/cost after a mock provider call
- OpenAI missing produces a generic error instead of mentioning "pip install openai"

## Requirements Proved By This UAT

- R002 (Single-File Mutation Constraint) — test cases 2 (path validation) and edge case (path traversal) prove the runner enforces file location constraints
- R003 (Instrumented Primitives) — test cases 1 and 4 prove auto-metric capture without user instrumentation
- R018 (Provider-Agnostic Primitives) — test cases 4 and 5 prove protocol-based contracts work with multiple providers

## Not Proven By This UAT

- R003 full scope — only MockLLM/MockRetriever and OpenAILLM tested; Anthropic, local models, real retrieval backends not exercised
- R018 full scope — only mock and OpenAI providers; no real multi-provider pipeline tested
- Runtime performance under load — no stress testing of MetricsCollector with hundreds of calls
- End-to-end optimization loop — that's S05's territory

## Notes for Tester

- The venv must have the package installed in editable mode. If imports fail, run `.venv/bin/pip install -e ".[dev]"` first.
- OpenAI edge case test requires that `openai` is NOT installed. If it is installed, the test will behave differently (it will try to make a real API call). Skip that edge case if openai is present.
- All tests use mock providers — no API keys or network access needed.
