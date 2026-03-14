---
id: T01
parent: S01
milestone: M001
provides:
  - MetricsSnapshot, PipelineResult, ErrorInfo dataclasses (autoagent.types)
  - LLMProtocol, RetrieverProtocol structural contracts (autoagent.primitives)
  - MockLLM, MockRetriever concrete providers with auto-metric capture
  - OpenAILLM with lazy import and token normalization
  - MetricsCollector for per-call and aggregate metrics
  - PrimitivesContext namespace for pipeline injection
  - COST_PER_1K_TOKENS per-model pricing config
key_files:
  - src/autoagent/types.py
  - src/autoagent/primitives.py
  - tests/test_primitives.py
key_decisions:
  - Frozen dataclass for MetricsSnapshot (immutability after capture), regular dataclass for PipelineResult (runner populates incrementally)
  - Cost config as module-level dict with function accepting override — simple, overridable, no class ceremony
  - LLM/Retriever as public aliases for LLMProtocol/RetrieverProtocol to match slice plan import expectations
  - MockRetriever.retrieve() returns a copy to prevent mutation of internal state
patterns_established:
  - Primitives accept optional MetricsCollector in __init__; each call records a snapshot
  - calculate_cost() is a standalone function usable by any provider, not a method on the collector
  - OpenAI client lazily created on first complete() call, cached afterward
observability_surfaces:
  - MetricsCollector.snapshots — per-call list, inspectable after any run
  - MetricsCollector.aggregate() — summed totals across all calls
  - PipelineResult.error — structured ErrorInfo with type/message/traceback
duration: ~15min
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Implement types, primitive protocols, and concrete providers

**Built foundational type contracts (MetricsSnapshot, PipelineResult, ErrorInfo) and primitive system (Protocols, MockLLM, MockRetriever, OpenAILLM, MetricsCollector, cost config, PrimitivesContext).**

## What Happened

Created `types.py` with three dataclasses: frozen `MetricsSnapshot` (latency, tokens in/out, cost, model, provider, timestamp, custom_metrics), `ErrorInfo` (type, message, traceback), and mutable `PipelineResult` (output, metrics, success, error, duration_ms). Both top-level types have `.asdict()` for JSON serialization.

Created `primitives.py` with: runtime-checkable `LLMProtocol` and `RetrieverProtocol` defining structural contracts; `MetricsCollector` accumulating per-call snapshots with `.aggregate()` summing values; `MockLLM` and `MockRetriever` returning configurable responses and auto-registering metrics; `OpenAILLM` with lazy `import openai` inside `_get_client()`, normalizing `prompt_tokens`/`completion_tokens` to `tokens_in`/`tokens_out`; `COST_PER_1K_TOKENS` dict with 7 known models; `calculate_cost()` function accepting optional override config; `PrimitivesContext` namespace holding llm, retriever, and shared collector.

Wrote 32 tests covering all types, serialization, cost calculation, mock providers, collector aggregation (including 5+ calls and mixed providers), OpenAI import error handling, mocked OpenAI completion flow, and PrimitivesContext wiring.

## Verification

- `pytest tests/test_primitives.py -v` — **32/32 passed**
- `python -c "from autoagent.types import MetricsSnapshot, PipelineResult; ..."` — **imports OK**
- `python -c "from autoagent.primitives import LLM, Retriever; ..."` — **boundary contracts importable**
- Failure-state structured check — **PipelineResult with ErrorInfo inspectable**
- Slice checks `test_pipeline_runner.py` — **not yet applicable** (T02)

## Diagnostics

- `MetricsCollector.snapshots` — inspect per-call metrics after any pipeline run
- `MetricsCollector.aggregate()` — get summed totals
- `PipelineResult.error` — structured ErrorInfo when `success=False`
- OpenAILLM raises `ImportError("...pip install openai")` when SDK missing — grep-friendly

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/types.py` — MetricsSnapshot, PipelineResult, ErrorInfo dataclasses
- `src/autoagent/primitives.py` — Protocols, MetricsCollector, MockLLM, MockRetriever, OpenAILLM, cost config, PrimitivesContext
- `tests/test_primitives.py` — 32 tests covering all of the above
- `.gsd/milestones/M001/slices/S01/S01-PLAN.md` — added failure-path verification check
- `.gsd/milestones/M001/slices/S01/tasks/T01-PLAN.md` — added Observability Impact section
