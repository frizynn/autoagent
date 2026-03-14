---
id: S01
parent: M001
milestone: M001
provides:
  - MetricsSnapshot, PipelineResult, ErrorInfo dataclasses (autoagent.types) — boundary contracts for S03/S04/S05
  - LLMProtocol, RetrieverProtocol structural contracts (autoagent.primitives)
  - MockLLM, MockRetriever concrete providers with auto-metric capture
  - OpenAILLM with lazy import and token normalization
  - MetricsCollector for per-call and aggregate metrics accumulation
  - PrimitivesContext namespace for pipeline injection
  - COST_PER_1K_TOKENS per-model pricing config with override support
  - PipelineRunner — dynamic pipeline loading and execution with structured error handling
requires: []
affects:
  - S03 (consumes PipelineRunner, MetricsSnapshot, PipelineResult)
  - S04 (consumes PipelineResult, MetricsSnapshot)
  - S05 (consumes PipelineRunner, PrimitivesContext)
key_files:
  - src/autoagent/types.py
  - src/autoagent/primitives.py
  - src/autoagent/pipeline.py
  - tests/test_primitives.py
  - tests/test_pipeline_runner.py
  - tests/fixtures/toy_pipeline.py
key_decisions:
  - "Frozen dataclass for MetricsSnapshot — immutability after capture (D011)"
  - "compile()+exec() for module loading instead of importlib — defeats bytecode cache for fresh loads (D014)"
  - "Cost calculation as standalone function with override config (D012)"
  - "Protocol aliases (LLM, Retriever) for clean imports (D013)"
patterns_established:
  - Primitives accept optional MetricsCollector in __init__; each call records a snapshot
  - PipelineRunner never raises — all failures produce PipelineResult(success=False) with structured ErrorInfo
  - Path validation resolves symlinks before checking allowed_root containment
observability_surfaces:
  - MetricsCollector.snapshots — per-call list, inspectable after any run
  - MetricsCollector.aggregate() — summed totals across all calls
  - PipelineResult.error — structured ErrorInfo(type, message, traceback) when success=False
  - PipelineResult.duration_ms — wall-clock time, always populated
drill_down_paths:
  - .gsd/milestones/M001/slices/S01/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S01/tasks/T02-SUMMARY.md
duration: ~35min
verification_result: passed
completed_at: 2026-03-14
---

# S01: Pipeline Execution Engine

**Instrumented primitives auto-capture metrics; PipelineRunner dynamically loads and executes pipeline.py, returning structured results with aggregated latency/tokens/cost.**

## What Happened

T01 built the foundational type system and primitive layer. `types.py` defines three dataclasses: frozen `MetricsSnapshot` (latency, tokens in/out, cost, model, provider, timestamp, custom_metrics), `ErrorInfo` (type, message, traceback), and mutable `PipelineResult` (output, metrics, success, error, duration_ms). `primitives.py` provides runtime-checkable `LLMProtocol` and `RetrieverProtocol`, `MetricsCollector` accumulating per-call snapshots with `.aggregate()`, `MockLLM`/`MockRetriever` for testing, `OpenAILLM` with lazy import, and `COST_PER_1K_TOKENS` pricing config with `calculate_cost()`.

T02 built `PipelineRunner` with dynamic module loading. Key discovery: importlib's bytecode cache defeats fresh-load semantics when the same path is loaded twice, so the implementation uses `compile()+exec()` instead. The runner validates paths (rejects non-.py, symlinks outside root), loads fresh source every call, verifies a callable `run` exists, and wraps execution in structured error handling. Three fixtures prove the paths: `toy_pipeline.py` (mock RAG with LLM + Retriever calls), `bad_pipeline.py` (missing run), `crash_pipeline.py` (raises exception).

## Verification

- `pytest tests/test_primitives.py -v` — **32/32 passed** (types, cost calc, mock providers, collector, OpenAI lazy import, PrimitivesContext)
- `pytest tests/test_pipeline_runner.py -v` — **9/9 passed** (success path, missing file, missing run, exception, path validation, fresh loading)
- `pytest tests/ -v` — **41/41 passed** (full suite)
- `python -c "from autoagent.types import MetricsSnapshot, PipelineResult; from autoagent.primitives import LLM, Retriever; print('boundary contracts importable')"` — ✅
- `python -c "from autoagent.types import PipelineResult, ErrorInfo; r = PipelineResult(...); assert not r.success; assert r.error.type == 'ValueError'"` — ✅
- toy_pipeline.py produces PipelineResult with tokens_in=15, tokens_out=20, cost_usd>0, latency_ms>0 — ✅

## Requirements Advanced

- R002 (Single-File Mutation Constraint) — PipelineRunner enforces path validation, rejects files outside allowed root
- R003 (Instrumented Primitives) — MockLLM, MockRetriever, OpenAILLM auto-capture latency/tokens/cost via MetricsCollector
- R018 (Provider-Agnostic Primitives) — Protocol-based contracts allow any provider; MockLLM and OpenAILLM prove the pattern

## Requirements Validated

- None — these requirements need downstream slices (S03 evaluation, S05 loop) to be fully validated

## New Requirements Surfaced

- None

## Requirements Invalidated or Re-scoped

- None

## Deviations

- **Module loading**: Plan specified importlib.util; switched to compile()+exec() after discovering bytecode cache prevents fresh loads. Simpler and correct.
- **Extra fixture**: Added crash_pipeline.py beyond what the plan specified for better error-path coverage.

## Known Limitations

- OpenAILLM is the only concrete LLM provider — Anthropic, local models deferred to when needed
- No Tool or Agent concrete implementations yet — protocols defined but no providers beyond LLM/Retriever
- Cost config is a static dict — no dynamic pricing API integration

## Follow-ups

- None — downstream slices (S03, S04, S05) consume these contracts as designed

## Files Created/Modified

- `src/autoagent/types.py` — MetricsSnapshot, PipelineResult, ErrorInfo dataclasses
- `src/autoagent/primitives.py` — Protocols, MetricsCollector, MockLLM, MockRetriever, OpenAILLM, cost config, PrimitivesContext
- `src/autoagent/pipeline.py` — PipelineRunner with dynamic loading, path validation, structured errors
- `tests/test_primitives.py` — 32 tests
- `tests/test_pipeline_runner.py` — 9 tests
- `tests/fixtures/toy_pipeline.py` — toy RAG pipeline fixture
- `tests/fixtures/bad_pipeline.py` — missing run() fixture
- `tests/fixtures/crash_pipeline.py` — raises ValueError fixture

## Forward Intelligence

### What the next slice should know
- Import types via `from autoagent.types import MetricsSnapshot, PipelineResult, ErrorInfo`
- Import primitives via `from autoagent.primitives import LLM, Retriever, MockLLM, MockRetriever, MetricsCollector, PrimitivesContext`
- `PipelineRunner(allowed_root=path)` then `.run(pipeline_path, input_data, primitives_context)` — returns PipelineResult, never raises
- toy_pipeline.py in tests/fixtures/ is a working reference for what pipeline.py looks like

### What's fragile
- `compile()+exec()` module loading creates a synthetic module namespace — pipeline code can't do relative imports or access `__file__` meaningfully
- Cost config is a plain dict — if model names don't match exactly (case, versioning), cost returns 0.0

### Authoritative diagnostics
- `PipelineResult.success` + `.error` — check these first on any execution failure
- `MetricsCollector.snapshots` — per-call breakdown if aggregate metrics look wrong
- OpenAI lazy import error message includes "pip install openai" — grep-friendly

### What assumptions changed
- importlib.util was expected to handle fresh loads — bytecode cache made it unsuitable, compile()+exec() is the actual pattern
