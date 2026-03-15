# S04: Cold-Start Pipeline Generation — Research

**Date:** 2026-03-14

## Summary

Cold-start needs three things: (1) detect that no real pipeline exists, (2) generate an initial pipeline from goal + benchmark + component vocabulary via the meta-agent's LLM, and (3) wire that into `cmd_run` so it happens transparently before the optimization loop starts. The codebase is well-positioned — `MetaAgent._validate_source()` already handles validation, `build_component_vocabulary()` provides the pattern menu, and the loop's existing `propose()` flow shows the extraction/validation pattern to follow.

The main design question is **where cold-start generation lives**. The boundary map says "MetaAgent (or new method)" for generation and "CLI integration" for detection. The cleanest approach: add `MetaAgent.generate_initial(benchmark_description: str) -> ProposalResult` that builds a cold-start-specific prompt (goal + vocabulary + benchmark examples + primitive usage rules), calls the LLM, extracts/validates source via the same `_extract_source` / `_validate_source` path. Detection happens in `cmd_run()` — check if pipeline.py content matches `STARTER_PIPELINE` (or a simpler heuristic: pipeline contains `return {"echo": input_data}`). On detection, generate initial pipeline, write it, then enter the loop normally.

A secondary need is **benchmark description generation** — the meta-agent currently receives `benchmark_description=""` from the loop (the parameter exists on `_build_prompt` and `propose` but is never populated). Cold-start especially needs this: the LLM must understand what the benchmark expects to generate a relevant pipeline. A `Benchmark.describe()` method (or standalone function) that samples a few examples and reports the scorer name would serve both cold-start and improve normal iterations.

## Recommendation

**Layer 1: Benchmark description.** Add a method or function that produces a compact description from a `Benchmark` — sample 2-3 examples (input/expected), note total example count, scoring function name. Keep it under 500 tokens. This benefits both cold-start and normal loop iterations (the plumbing exists but is unused).

**Layer 2: Cold-start generation on MetaAgent.** Add `generate_initial(benchmark_description: str) -> ProposalResult`. This builds a prompt with:
- System instructions: "Generate a complete pipeline.py from scratch"
- Goal section
- Component vocabulary (via `build_component_vocabulary()`)
- Benchmark description with example samples
- Explicit primitive usage rules (the `run(input_data, primitives=None)` signature, `primitives.llm.complete()` usage)
- One concrete example showing correct structure

Uses the same `_extract_source()` → `_validate_source()` pipeline as `propose()`. Returns `ProposalResult` — same cost tracking, same error handling.

**Layer 3: CLI wiring.** In `cmd_run()`, after loading benchmark and before creating the loop, detect cold-start condition. If pipeline.py is the starter template, call `meta_agent.generate_initial(benchmark_desc)`. On success, write to pipeline.py. On failure, retry once with a simpler prompt (or let the loop handle the starter pipeline — it'll score 0.0 and the meta-agent will improve from there). No need to abort on generation failure — the existing loop handles bad pipelines gracefully.

**Detection heuristic:** Compare pipeline content to `STARTER_PIPELINE` from `state.py`. Exact match is reliable — `init_project()` writes that exact template, and if the user has modified it, they don't want cold-start.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Source extraction from LLM response | `MetaAgent._extract_source()` | Longest fenced code block strategy (D022) — same for cold-start |
| Source validation | `MetaAgent._validate_source()` | compile + exec + run() check (D023) — cold-start pipelines must pass same gate |
| Cost tracking | `MetricsCollector` on `MetaAgent.llm` | Same incremental cost pattern as `propose()` |
| Component vocabulary | `build_component_vocabulary()` | Already returns formatted text with pattern skeletons and primitive signatures |
| Starter template | `state.STARTER_PIPELINE` | Single source of truth for cold-start detection |
| Atomic file writes | `pipeline_path.write_text()` | Loop already writes proposed source this way |

## Existing Code and Patterns

- `src/autoagent/meta_agent.py` — **Primary extension point.** `propose()` shows the pattern: snapshot collector → build prompt → call LLM → extract source → validate → return `ProposalResult`. `generate_initial()` follows the same structure with a different prompt. `_extract_source()` and `_validate_source()` are already `@staticmethod` — callable without an instance.
- `src/autoagent/meta_agent.py::build_component_vocabulary()` — **Consumed directly.** Returns ~875 tokens of pattern skeletons with correct primitive usage. Cold-start prompt includes this verbatim.
- `src/autoagent/state.py::STARTER_PIPELINE` — **Detection anchor.** The exact string written by `init_project()`. Cold-start triggers when pipeline.py matches this.
- `src/autoagent/cli.py::cmd_run()` — **Wiring point.** Pipeline path is `sm.pipeline_path`. After benchmark loading, before loop creation, detect cold-start and generate. Current code reads pipeline in the loop's `run()` — cold-start should happen before `loop.run()` so the loop sees a real initial pipeline.
- `src/autoagent/loop.py::OptimizationLoop.run()` — **No changes needed.** Line 149: `current_best_source = pipeline_path.read_text()`. If cold-start writes a real pipeline before loop starts, the loop works unchanged.
- `src/autoagent/benchmark.py::Benchmark` — **Needs description method.** Has `examples`, `scoring_function_name`, `source_path` but no way to generate a human-readable description. Cold-start needs this; regular iterations would also benefit.
- `tests/test_loop.py::SequentialMockMetaAgent` — **Test pattern.** Shows how to mock `propose()` with predetermined results. Cold-start tests should mock `generate_initial()` similarly.
- `src/autoagent/state.py::StateManager.is_initialized()` — **Checks pipeline.py exists.** Cold-start doesn't change initialization — it generates after init, before loop.

## Constraints

- **Zero runtime dependencies** — No tiktoken for token counting. Benchmark description length managed by character count heuristic (chars/4 ≈ tokens).
- **compile()+exec() module loading (D014)** — Cold-start pipelines run in synthetic namespace. No relative imports, no `__file__` assumptions. Pattern skeletons in vocabulary already satisfy this.
- **Single-file constraint (D001)** — Cold-start generates one complete `pipeline.py`. No multi-file generation.
- **First iteration always kept (D024)** — After cold-start writes pipeline.py, the loop's first evaluation will be kept regardless of score. This is correct behavior — establishes baseline.
- **Provider-agnostic (D004)** — Cold-start prompt must not assume specific LLM providers. Pattern skeletons use `primitives.llm.complete()` / `primitives.retriever.retrieve()`.
- **Existing propose() accepts benchmark_description="" but it's never populated** — The loop never passes benchmark description. This is a gap that cold-start exposes. Could fix in this slice (pass benchmark_description through loop) or leave for later. Cold-start generation needs it regardless.
- **MockLLM returns empty string by default** — Tests using MockLLM need configured responses for cold-start. `MockLLM` accepts a `responses` list or fixed `response` string.

## Common Pitfalls

- **Cold-start pipelines that don't use primitives** — The M002 research flags this explicitly. The generation prompt must include concrete examples of `primitives.llm.complete()` usage and anti-patterns (no `import openai`). The vocabulary already covers this, but the cold-start prompt should reinforce it with the explicit `run(input_data, primitives=None)` signature.
- **Generating a pipeline that ignores the benchmark format** — If the benchmark expects `{"answer": "..."}` and the generated pipeline returns `{"echo": "..."}`, every example scores 0.0. The benchmark description must include example I/O format so the LLM generates matching output keys.
- **Over-engineering detection** — Tempting to parse pipeline AST or hash it. Simple string comparison with `STARTER_PIPELINE` is sufficient and robust. If the user edits even one character, it's not a cold-start.
- **Retry loops on generation failure** — One retry is reasonable. Beyond that, let the loop handle it — the starter pipeline will score 0.0 and the meta-agent will improve from there. Don't block `autoagent run` on cold-start perfection.
- **Not logging the cold-start event** — This should be visible: "No custom pipeline found. Generating initial pipeline from goal and benchmark..." Users need to understand why the first iteration took longer.

## Open Risks

- **Cold-start quality variance** — The generated pipeline might score 0.0 on first evaluation. This is acceptable — D024 ensures it's kept as baseline, and the loop improves from there. But if the pipeline doesn't even use the right output keys, all 10+ iterations might waste budget before hitting the right format. Mitigation: include benchmark I/O examples in the prompt.
- **MockLLM in cmd_run()** — Currently `cmd_run()` creates a `MockLLM` (line 124-125: "MockLLM for now; real provider plugged in later"). Cold-start with MockLLM will produce garbage. This is a pre-existing issue, not a cold-start regression — but it means cold-start tests must mock at the MetaAgent level, not rely on the CLI's LLM setup.
- **Benchmark description leaking test data** — If the description includes too many examples, the pipeline could memorize them. Sampling 2-3 examples from a larger set is the right balance — shows format without enabling overfitting.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| No external technologies needed | — | Cold-start is pure prompt engineering + Python stdlib |

## Sources

- ADAS paper approach — cold-start equivalent is the "initial agent" seeded from domain description + available primitives (source: M002 research, prior knowledge)
- M002-RESEARCH.md — cold-start quality variance discussion, primitive usage requirements
- S02-SUMMARY.md — vocabulary is ~875 tokens, injected between Goal and Benchmark sections
- S03-SUMMARY.md — `propose()` accepts `strategy_signals=""`, cold-start should pass empty signals
