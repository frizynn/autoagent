# S01: Pipeline Execution Engine

**Goal:** Instrumented primitives (LLM, Retriever, Tool, Agent) auto-capture metrics; PipelineRunner dynamically loads and executes a user's pipeline.py, returning structured results with aggregated metrics.
**Demo:** A toy RAG pipeline.py using mock primitives runs through PipelineRunner and reports latency, tokens, and cost to stdout.

## Must-Haves

- Protocol-based primitive interfaces (LLM, Retriever, Tool, Agent) that downstream slices code against
- Metrics auto-capture: latency (perf_counter), tokens (in/out), cost (USD) — no user instrumentation needed
- MetricsCollector accumulates across multiple primitive calls within a single pipeline run
- Mock provider for all primitives — enables testing without API keys
- OpenAI concrete LLM implementation with lazy import (fails clearly if sdk missing)
- PipelineRunner loads pipeline.py via importlib.util, executes `run(input_data, primitives)`, returns PipelineResult
- Fresh module load every time — no stale module caching across mutations
- Single-file constraint enforced: runner refuses paths outside expected location
- Pipeline exceptions captured in structured result, never crash the runner
- MetricsSnapshot and PipelineResult types usable by S03/S04/S05 via import
- Cost config: dictionary of per-model USD/1K-token prices, overridable

## Proof Level

- This slice proves: contract + integration (primitives capture real metrics, runner executes real Python)
- Real runtime required: yes (dynamic module loading, timing measurement)
- Human/UAT required: no

## Verification

- `pytest tests/test_primitives.py -v` — primitives capture metrics, mock provider returns expected values, metrics collector aggregates correctly
- `pytest tests/test_pipeline_runner.py -v` — runner loads a toy pipeline.py, returns PipelineResult with metrics; handles missing run(), exceptions, bad paths
- `python -c "from autoagent.types import MetricsSnapshot, PipelineResult; from autoagent.primitives import LLM, Retriever; print('boundary contracts importable')"` — proves S03/S04/S05 can import the types
- `python -c "from autoagent.types import PipelineResult, ErrorInfo; r = PipelineResult(output=None, metrics=None, success=False, error=ErrorInfo(type='ValueError', message='test', traceback='...'), duration_ms=0.0); assert not r.success; assert r.error.type == 'ValueError'; print('failure state structured')"` — proves error path produces inspectable structured failure

## Observability / Diagnostics

- Runtime signals: MetricsCollector exposes `.snapshots` list (per-call) and `.aggregate()` (totals) — inspectable after any run
- Inspection surfaces: PipelineResult includes `.metrics`, `.output`, `.error`, `.duration_ms` — all state visible in one object
- Failure visibility: pipeline.py exceptions captured as `PipelineResult.error` (type + message + traceback string) with `success=False`
- Redaction constraints: none (no secrets flow through primitives in S01)

## Integration Closure

- Upstream surfaces consumed: none (first slice)
- New wiring introduced in this slice: `src/autoagent/types.py`, `src/autoagent/primitives.py`, `src/autoagent/pipeline.py` — the boundary contracts for S03/S04/S05
- What remains before the milestone is truly usable end-to-end: S02 (CLI), S03 (evaluation), S04 (archive), S05 (loop), S06 (budget/recovery)

## Tasks

- [x] **T01: Implement types, primitive protocols, and concrete providers** `est:1.5h`
  - Why: Everything else depends on the type contracts and at least one working primitive implementation. This is the foundation S03/S04/S05 import from.
  - Files: `src/autoagent/types.py`, `src/autoagent/primitives.py`, `tests/test_primitives.py`
  - Do: Define MetricsSnapshot and PipelineResult dataclasses in types.py. Define Protocol classes (LLM, Retriever, Tool, Agent) in primitives.py with instrumentation wrappers. Implement MetricsCollector that accumulates per-call snapshots and produces aggregates. Build MockLLM and MockRetriever providers. Build OpenAILLM with lazy import and clear error on missing SDK. Add per-model cost config dict with known prices. Write comprehensive tests: metric capture accuracy, collector aggregation, mock provider behavior, lazy import error handling.
  - Verify: `pytest tests/test_primitives.py -v` — all pass
  - Done when: MockLLM and MockRetriever produce correct MetricsSnapshots; MetricsCollector aggregates 5+ calls accurately; OpenAILLM import fails gracefully without openai installed

- [x] **T02: Implement PipelineRunner and prove end-to-end execution** `est:1.5h`
  - Why: Closes the slice — proves a pipeline.py dynamically loads and runs through instrumented primitives, producing a PipelineResult with real aggregated metrics.
  - Files: `src/autoagent/pipeline.py`, `tests/test_pipeline_runner.py`, `tests/fixtures/toy_pipeline.py`, `tests/fixtures/bad_pipeline.py`
  - Do: Build PipelineRunner that loads a module from a file path via importlib.util (fresh spec + module each call, never added to sys.modules). Enforce single-file constraint (resolve path, reject symlinks or paths outside allowed root). Call module's `run(input_data, primitives)` with a primitives namespace containing pre-configured instances. Wrap execution in try/except, populate PipelineResult with output or error. Create toy_pipeline.py fixture (mock RAG: LLM call + retriever call, returns answer). Create bad_pipeline.py fixtures (missing run, raises exception). Test: successful run returns metrics, error cases return structured failures, stale module detection (modify file between loads), path validation.
  - Verify: `pytest tests/test_pipeline_runner.py -v` — all pass; toy pipeline produces PipelineResult with latency > 0, token counts > 0, cost > 0
  - Done when: PipelineRunner.run() executes toy_pipeline.py with mock primitives, returns PipelineResult with aggregated metrics; bad paths and exceptions produce structured errors, never crash

## Files Likely Touched

- `src/autoagent/types.py`
- `src/autoagent/primitives.py`
- `src/autoagent/pipeline.py`
- `tests/test_primitives.py`
- `tests/test_pipeline_runner.py`
- `tests/fixtures/toy_pipeline.py`
- `tests/fixtures/bad_pipeline.py`
