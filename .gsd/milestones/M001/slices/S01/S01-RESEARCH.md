# S01: Pipeline Execution Engine — Research

**Date:** 2026-03-14

## Summary

S01 is greenfield — no functional code exists beyond the package skeleton. The slice must deliver three things: (1) instrumented primitives (LLM, Retriever, Tool, Agent) that auto-capture latency, tokens, and cost; (2) a PipelineRunner that dynamically loads and executes a user's `pipeline.py`; and (3) the types that downstream slices consume (MetricsSnapshot, PipelineResult).

The execution model is straightforward: `importlib.util.spec_from_file_location` + `exec_module` loads arbitrary Python from a file path — stdlib, no dependencies. The pipeline.py contract is a `run(input_data, primitives)` function that receives pre-configured primitive instances and returns a result. Primitives wrap real provider SDKs (OpenAI, Anthropic) with timing/token/cost instrumentation. Both SDKs expose token usage on response objects, though field names differ (OpenAI: `prompt_tokens`/`completion_tokens`; Anthropic: `input_tokens`/`output_tokens`), so normalization is needed.

The primary design tension is abstraction depth (D010: thin wrappers). Primitives should add measurement, not behavior — they're not a framework (R030 anti-feature). The LLM primitive wraps a `complete()` call, captures timing and tokens, and returns the raw provider response. Cost calculation needs a pricing config since neither SDK returns cost directly.

## Recommendation

Build primitives as thin `Protocol`-based abstractions with concrete implementations per provider. Use `time.perf_counter()` for latency (monotonic, high-resolution). Use `dataclasses` for MetricsSnapshot and PipelineResult — no Pydantic dependency needed for this slice. Pipeline loading via `importlib.util` with a clear contract: the loaded module must expose a `run()` callable.

For S01 proof scope, implement one real provider (OpenAI) and one mock provider. The mock is critical — it enables testing without API calls and is what the S01 UAT will use. Provider-agnostic means the primitive interface is stable; adding Anthropic/others is additive, not architectural.

Cost tracking should use a simple dictionary of per-model costs (USD per 1K tokens input/output). Ship with known model prices; let users override via config. This is adequate for M001 — a dynamic pricing API can come later if needed.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Dynamic module loading | `importlib.util` (stdlib) | Battle-tested, handles path resolution, avoids `exec()` security smell |
| High-resolution timing | `time.perf_counter()` (stdlib) | Monotonic clock, nanosecond resolution on most platforms |
| Data classes for types | `dataclasses` (stdlib) | Zero dependencies, good enough for serialization to JSON via `asdict()` |
| Type protocols | `typing.Protocol` (stdlib 3.8+) | Structural subtyping — providers implement the protocol without inheriting |

## Existing Code and Patterns

- `src/autoagent/__init__.py` — Empty package, version only. Our new modules go alongside it.
- `pyproject.toml` — Python 3.11+, hatchling build, zero runtime deps. We should keep runtime deps minimal (no pydantic, no framework). OpenAI/Anthropic SDKs are user-installed, not our dependency — primitives import them lazily.
- `tests/test_smoke.py` — Simple import test. Follow the `tests/` flat structure. Use pytest with the existing config.

## Constraints

- **Python 3.11+ required** — pyproject.toml enforces this. Can use `dataclasses`, `Protocol`, `TypeAlias`, `Self`, match statements.
- **Zero runtime dependencies** — pyproject.toml has none. Provider SDKs (openai, anthropic) must be optional imports, not hard deps. Primitives should fail clearly if the provider SDK isn't installed.
- **Single-file mutation constraint (R002)** — PipelineRunner loads exactly one file. The runner must refuse to load anything outside the expected path.
- **Provider-agnostic (R018)** — The primitive interface (Protocol) is the contract. Concrete implementations are per-provider. Pipeline.py uses the protocol, not the implementation.
- **Thin wrappers (D010)** — Primitives add instrumentation. They don't add retry logic, caching, prompt templating, or any "framework" behavior.
- **Metrics must flow to downstream slices** — S03 (Evaluation) and S04 (Archive) consume MetricsSnapshot and PipelineResult. These types are the boundary contract.

## Common Pitfalls

- **Module caching in importlib** — `importlib.util` doesn't cache like regular imports, but if we add the module to `sys.modules`, reloading the same path returns stale code. Must create a fresh module each time (new spec, new module object). The optimization loop mutates pipeline.py between runs, so stale modules = wrong results.
- **Cost calculation drift** — Hardcoded pricing goes stale as providers update. Design the cost config to be overridable from the start. For M001, ship known prices but don't pretend they're permanent.
- **Provider SDK version churn** — OpenAI's SDK had a major v0→v1 breaking change. Import lazily, handle both `openai.ChatCompletion` (old) and `openai.OpenAI().chat.completions` (new) patterns — or just target v1+ and document minimum version. Leaning toward v1+ only since the old API is deprecated.
- **Pipeline.py exception handling** — User code in pipeline.py can throw anything. The runner must catch all exceptions, capture them in a structured result (not swallow), and let the caller decide what to do. An unhandled exception in pipeline.py should never crash the runner.
- **Async vs sync** — Provider SDKs support both. Pipeline.py might want async. For M001, keep it sync — async execution adds complexity that isn't needed yet. The `run()` contract is sync; async can be a future enhancement.

## Open Risks

- **Provider SDK not installed at runtime** — If a pipeline.py references `LLM(provider="openai")` but `openai` isn't installed, the error must be clear and actionable ("pip install openai"). Lazy imports with good error messages mitigate this.
- **Pipeline.py contract enforcement** — How strict? Must it have a `run()` function? Can it have side effects at import time? Module-level code executes during `exec_module`. For safety, the contract should be: module is loaded, then `run()` is called. Side effects at module level are the user's problem but we should document the expectation.
- **Metrics accumulation across multiple primitive calls** — A pipeline.py might call LLM 5 times. MetricsSnapshot should be the aggregate (total latency, total tokens, total cost), but individual call metrics should also be accessible for the meta-agent's analysis. Need a collector/accumulator pattern.
- **Thread safety** — Not a concern for M001's sync execution model, but the metrics accumulator design should not preclude future concurrent execution.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Python pipeline execution | none relevant | none found |
| OpenAI Python SDK | none relevant | none found |
| Anthropic Python SDK | none relevant | none found |

No external skills are relevant — this is core Python with provider SDK integration. The work is straightforward enough that skills would add overhead without value.

## Sources

- OpenAI response includes `usage.prompt_tokens` and `usage.completion_tokens` (source: [openai-python API docs](https://github.com/openai/openai-python/blob/main/api.md))
- Anthropic response includes `usage.input_tokens` and `usage.output_tokens` (source: [anthropic-sdk-python docs](https://github.com/anthropics/anthropic-sdk-python))
- `importlib.util.spec_from_file_location` is the stdlib approach for dynamic module loading — verified working with Python 3.11
- `time.perf_counter()` provides monotonic high-resolution timing — appropriate for latency measurement
- `dataclasses.asdict()` provides zero-dep serialization to dict/JSON — sufficient for MetricsSnapshot and PipelineResult
