---
estimated_steps: 5
estimated_files: 3
---

# T01: Implement types, primitive protocols, and concrete providers

**Slice:** S01 — Pipeline Execution Engine
**Milestone:** M001

## Description

Build the foundational type contracts (MetricsSnapshot, PipelineResult) and primitive system (Protocol-based interfaces + concrete implementations). This is the boundary contract that S03, S04, and S05 depend on. Includes MockLLM/MockRetriever for testing, OpenAILLM with lazy import, MetricsCollector for aggregating metrics across multiple calls, and a per-model cost configuration.

## Steps

1. Create `src/autoagent/types.py` with `MetricsSnapshot` (latency_ms, tokens_in, tokens_out, cost_usd, custom_metrics dict, model, provider, timestamp) and `PipelineResult` (output, metrics: MetricsSnapshot, success, error, duration_ms) as frozen/regular dataclasses. Include `asdict()` helper for JSON serialization. PipelineResult.error should be an optional `ErrorInfo` dataclass (type, message, traceback).
2. Create `src/autoagent/primitives.py` with Protocol classes: `LLMProtocol` (complete method), `RetrieverProtocol` (retrieve method). Add `MetricsCollector` class that primitive implementations register calls with — stores per-call snapshots in a list, provides `.aggregate()` returning a single MetricsSnapshot with summed values. Include a `PrimitivesContext` namespace that holds configured primitive instances + the shared collector.
3. Implement `MockLLM` and `MockRetriever` in primitives.py — configurable response content, simulated token counts, simulated latency (optional sleep or just reported). Each call auto-registers a MetricsSnapshot with the collector. Implement `OpenAILLM` with lazy `import openai` inside `complete()` — if missing, raise `ImportError` with message "pip install openai". Normalize OpenAI's `prompt_tokens`/`completion_tokens` to `tokens_in`/`tokens_out`. Use `time.perf_counter()` for latency.
4. Add `COST_PER_1K_TOKENS` dict in primitives.py with known model prices (gpt-4o, gpt-4o-mini, gpt-3.5-turbo, claude-3.5-sonnet, etc.). Cost = (tokens_in * input_price + tokens_out * output_price) / 1000. Allow override via a `cost_config` parameter.
5. Write `tests/test_primitives.py`: test MetricsSnapshot creation and serialization, test MockLLM returns expected response and captures metrics, test MockRetriever returns docs and captures metrics, test MetricsCollector aggregates 5+ calls correctly (sums tokens, sums cost, sums latency), test OpenAILLM raises clear error when openai not installed, test PrimitivesContext provides access to primitives and shared collector.

## Must-Haves

- [ ] MetricsSnapshot and PipelineResult are importable from `autoagent.types`
- [ ] LLMProtocol and RetrieverProtocol define the structural contracts
- [ ] MockLLM.complete() returns configurable response and registers MetricsSnapshot
- [ ] MockRetriever.retrieve() returns configurable docs and registers MetricsSnapshot
- [ ] MetricsCollector.aggregate() sums metrics across all registered calls
- [ ] OpenAILLM raises clear ImportError when openai package is missing
- [ ] Cost calculation uses per-model config, not hardcoded per-call
- [ ] All tests pass

## Verification

- `pytest tests/test_primitives.py -v` — all tests pass
- `python -c "from autoagent.types import MetricsSnapshot, PipelineResult; print('OK')"` — imports work

## Observability Impact

- **MetricsCollector.snapshots** — list of per-call MetricsSnapshot objects; a future agent can inspect individual call metrics after any pipeline run
- **MetricsCollector.aggregate()** — returns a single MetricsSnapshot with summed values; the primary summary surface for pipeline cost/latency/tokens
- **PipelineResult.error** — structured ErrorInfo (type, message, traceback) when success=False; enables programmatic failure inspection without parsing stderr
- **Cost calculation** — per-model pricing in COST_PER_1K_TOKENS dict; visible and overridable, not buried in implementation
- **Failure signals:** OpenAILLM raises ImportError with actionable message when SDK missing; MockLLM/MockRetriever always register snapshots even on zero-latency calls

## Inputs

- `src/autoagent/__init__.py` — existing package entry point
- `pyproject.toml` — Python 3.11+, zero runtime deps, pytest configured
- S01 research findings on provider SDK token field names and importlib patterns

## Expected Output

- `src/autoagent/types.py` — MetricsSnapshot, PipelineResult, ErrorInfo dataclasses
- `src/autoagent/primitives.py` — Protocols, MetricsCollector, MockLLM, MockRetriever, OpenAILLM, PrimitivesContext, cost config
- `tests/test_primitives.py` — comprehensive test suite for all of the above
