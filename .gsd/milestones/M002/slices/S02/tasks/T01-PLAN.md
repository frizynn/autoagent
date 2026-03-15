---
estimated_steps: 4
estimated_files: 2
---

# T01: Build component vocabulary and inject into meta-agent prompt

**Slice:** S02 — Structural Search & Component Vocabulary
**Milestone:** M002

## Description

Build a `build_component_vocabulary()` function in `meta_agent.py` that returns a structured text block listing available primitives and architectural patterns. Inject it into `_build_prompt()` as a new section. Update system instructions to encourage structural mutations. Add tests proving vocabulary content, injection, and budget.

The vocabulary is a static prompt artifact — reference-style, not tutorial prose. It describes what the meta-agent *can* build with, including pattern skeletons showing correct `primitives` usage. This is the core enabler for R011 (Structural Search).

## Steps

1. **Add `build_component_vocabulary()` function** to `meta_agent.py`. Returns a string containing:
   - Available primitives: `primitives.llm.complete(prompt, **kwargs) -> str` and `primitives.retriever.retrieve(query, **kwargs) -> list[str]` with brief usage notes
   - 6 architectural patterns (RAG, CAG, debate, reflexion, ensemble, reranking) — each with a 1-2 line description and a 5-10 line skeleton showing correct primitive usage in a `run(input_data, primitives=None)` function
   - Anti-patterns section: no `import openai`/`import anthropic`, must use `primitives` parameter, no hardcoded API keys
   - Target: ~1.5-2K tokens total (~6-8K chars). Build from a data structure (list of pattern dicts) so adding patterns later is trivial.

2. **Update `_build_prompt()` system instructions** to mention structural mutation: add a line like "Consider changing the pipeline's architecture — not just tuning parameters — when the current approach has fundamental limitations." Keep it suggestive per D005 (autonomous strategy decisions).

3. **Inject vocabulary section into `_build_prompt()`** between Goal and Current Pipeline (before benchmark). The vocabulary is always included (not conditional) since it's static. Add it as: `sections.append(f"## Component Vocabulary\n{build_component_vocabulary()}")`

4. **Add tests** to `tests/test_meta_agent.py`:
   - `test_vocabulary_section_in_prompt` — build prompt includes "## Component Vocabulary"
   - `test_vocabulary_contains_primitives` — vocabulary mentions `primitives.llm.complete` and `primitives.retriever.retrieve`
   - `test_vocabulary_contains_all_patterns` — vocabulary contains all 6 pattern names (RAG, CAG, debate, reflexion, ensemble, reranking)
   - `test_vocabulary_contains_anti_patterns` — vocabulary warns against hardcoded imports
   - `test_vocabulary_token_budget` — `build_component_vocabulary()` output is under 8000 chars (~2K tokens)
   - `test_system_instructions_mention_structural_changes` — prompt system instructions section mentions architecture/structural changes
   - Run all existing tests to confirm no regressions

## Must-Haves

- [ ] `build_component_vocabulary()` returns structured text with both primitives and all 6 patterns
- [ ] All pattern skeletons use `primitives.llm.complete()` / `primitives.retriever.retrieve()` — never raw provider imports
- [ ] Vocabulary section injected into `_build_prompt()` output, always present
- [ ] System instructions updated with structural mutation guidance
- [ ] Vocabulary fits under ~8K chars (~2K tokens)
- [ ] All existing 27 meta-agent tests still pass
- [ ] 6+ new tests covering vocabulary content, injection, and budget

## Observability Impact

- **New inspection surface:** `build_component_vocabulary()` — pure function, callable standalone to inspect full vocabulary text. No side effects, no state.
- **Prompt debuggability:** Vocabulary section appears in `_build_prompt()` output between Goal and Current Pipeline. Any agent debugging prompt quality can print the prompt and see the vocabulary inline.
- **Failure signals:** If vocabulary content drifts (missing patterns, broken skeletons, budget exceeded), the 6 new tests fail with descriptive assertions showing exactly what's missing or over-budget.
- **No new runtime state** — this is a static prompt artifact, not a stateful component. No failure modes beyond content correctness.

## Verification

- `pytest tests/test_meta_agent.py -v` — all tests pass (existing + new)
- Manual check: `build_component_vocabulary()` output is readable, compact, and correct

## Inputs

- `src/autoagent/meta_agent.py` — `_build_prompt()` is the extension point, follows sections-list pattern
- `src/autoagent/primitives.py` — `LLMProtocol.complete()` and `RetrieverProtocol.retrieve()` signatures
- `tests/test_meta_agent.py` — 27 existing tests, follows pytest patterns with MockLLM fixtures

## Expected Output

- `src/autoagent/meta_agent.py` — updated with `build_component_vocabulary()` function, enriched `_build_prompt()` with vocabulary section and updated system instructions
- `tests/test_meta_agent.py` — 6+ new tests verifying vocabulary content, injection, and budget
