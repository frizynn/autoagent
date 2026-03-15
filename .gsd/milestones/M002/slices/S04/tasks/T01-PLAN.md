---
estimated_steps: 5
estimated_files: 4
---

# T01: Implement benchmark description and cold-start generation

**Slice:** S04 — Cold-Start Pipeline Generation
**Milestone:** M002

## Description

Add `Benchmark.describe()` to produce a compact benchmark description for the LLM (sample examples, scorer name, I/O format), and `MetaAgent.generate_initial()` to generate an initial pipeline from scratch using the component vocabulary and benchmark context. Both follow existing patterns — `describe()` is a pure method on Benchmark, `generate_initial()` mirrors `propose()` with a different prompt.

## Steps

1. Add `Benchmark.describe(max_examples: int = 3) -> str` — samples up to `max_examples` from `self.examples`, formats each as input/expected pair, includes total example count and scoring function name. Keep output under ~500 tokens (~2K chars).
2. Add `MetaAgent.generate_initial(benchmark_description: str) -> ProposalResult` — builds a cold-start-specific prompt with: system instructions for from-scratch generation, goal, component vocabulary (via `build_component_vocabulary()`), benchmark description, explicit `run(input_data, primitives=None)` signature requirement, one concrete example showing correct structure. Calls LLM, uses `_extract_source()` → `_validate_source()`, tracks cost via collector snapshot pattern from `propose()`.
3. Add unit tests in `tests/test_benchmark.py`: `describe()` includes example samples, scorer name, total count; `describe()` with fewer examples than max_examples; `describe()` output is a non-empty string under 2K chars.
4. Add unit tests in `tests/test_meta_agent.py`: `generate_initial()` success with mock LLM returning valid pipeline; `generate_initial()` failure when LLM returns invalid code; `generate_initial()` prompt includes vocabulary and benchmark description; `generate_initial()` cost tracking.
5. Run `pytest tests/test_benchmark.py tests/test_meta_agent.py -v` to verify.

## Observability Impact

- `Benchmark.describe()` output is a plain string — future agents can call it to inspect what the LLM sees about the benchmark
- `generate_initial()` uses same `ProposalResult` error surface as `propose()` — `success`, `error`, `cost_usd` fields are the diagnostic interface
- Cost from cold-start generation appears in MetricsCollector snapshots — distinguishable by timing (first snapshot before any loop iterations)
- Prompt content is inspectable by calling `_build_cold_start_prompt()` pattern or reading the prompt in test assertions

## Must-Haves

- [ ] `Benchmark.describe()` returns compact text with sampled examples and scorer name
- [ ] `MetaAgent.generate_initial()` returns `ProposalResult` using same extract/validate pipeline as `propose()`
- [ ] Generated prompt includes component vocabulary, benchmark description, and primitive usage rules
- [ ] Cost tracked via collector snapshot pattern (same as `propose()`)

## Verification

- `pytest tests/test_benchmark.py -v` — new describe tests pass
- `pytest tests/test_meta_agent.py -v` — new generate_initial tests pass, all existing tests still pass

## Inputs

- `src/autoagent/benchmark.py` — Benchmark class with examples, scorer, scoring_function_name
- `src/autoagent/meta_agent.py` — MetaAgent with propose(), _extract_source(), _validate_source(), build_component_vocabulary()
- S02 summary — vocabulary is ~875 tokens, injected between Goal and Benchmark sections

## Expected Output

- `src/autoagent/benchmark.py` — `describe()` method added to Benchmark class
- `src/autoagent/meta_agent.py` — `generate_initial()` method added to MetaAgent class
- `tests/test_benchmark.py` — 3+ new tests for describe()
- `tests/test_meta_agent.py` — 4+ new tests for generate_initial()
