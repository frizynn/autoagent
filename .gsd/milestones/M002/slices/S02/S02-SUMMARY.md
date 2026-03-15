---
id: S02
parent: M002
milestone: M002
provides:
  - build_component_vocabulary() function returning structured vocabulary text (~875 tokens)
  - Vocabulary section injected into _build_prompt() output (between Goal and Benchmark)
  - Structural mutation guidance in system instructions (rule 5)
  - 6 architectural pattern skeletons (RAG, CAG, Debate, Reflexion, Ensemble, Reranking) using primitives interface
  - Anti-pattern guidance (no raw provider imports, must use primitives parameter)
requires:
  - slice: S01
    provides: not consumed — S02 is independent
affects:
  - S03 (consumes vocabulary for strategy balance between structural/parameter mutations)
  - S04 (consumes vocabulary and pattern examples for cold-start pipeline generation)
key_files:
  - src/autoagent/meta_agent.py
  - tests/test_meta_agent.py
key_decisions:
  - D035: Vocabulary built from _PATTERNS list of dicts — adding new patterns is one dict append
patterns_established:
  - Static prompt artifacts built from data structures for easy extension
observability_surfaces:
  - build_component_vocabulary() is a pure standalone function — callable in REPL to inspect output
  - _build_prompt() output is a plain string — print to verify vocabulary placement and section ordering
drill_down_paths:
  - .gsd/milestones/M002/slices/S02/tasks/T01-SUMMARY.md
duration: 15m
verification_result: passed
completed_at: 2026-03-14
---

# S02: Structural Search & Component Vocabulary

**Component vocabulary with 6 architectural patterns, primitive signatures, anti-pattern guidance, and structural mutation system instructions injected into meta-agent prompt.**

## What Happened

Built `build_component_vocabulary()` in `meta_agent.py` using a `_PATTERNS` list of dicts — each pattern (RAG, CAG, Debate, Reflexion, Ensemble, Reranking) has a name, 1-2 line description, and a 5-10 line skeleton using `primitives.llm.complete()` / `primitives.retriever.retrieve()`. The function also documents both primitive signatures and lists anti-patterns (no raw provider imports, no hardcoded keys, must use primitives parameter).

Vocabulary injected as `## Component Vocabulary` section in `_build_prompt()` between Goal and Benchmark — always present since it's static content (3501 chars, ~875 tokens, well under 8K char budget).

System instructions updated with rule 5: "Consider changing the pipeline's architecture — not just tuning parameters — when the current approach has fundamental limitations."

7 new tests added covering vocabulary content, injection, budget, system instruction guidance, and skeleton safety (no raw imports).

## Verification

- `pytest tests/test_meta_agent.py -v` — 34/34 passed (27 existing + 7 new)
- Vocabulary output: 3501 chars, under 8K budget
- All 6 patterns present in vocabulary, both primitive signatures present
- Anti-patterns (hardcoded imports, missing primitives) present
- System instructions reference structural/architecture changes
- Skeletons verified to use primitives interface exclusively

## Requirements Advanced

- R011 (Structural Search) — meta-agent prompt now includes component vocabulary and structural mutation guidance enabling topology-changing mutations

## Requirements Validated

- none — R011 requires end-to-end proof of topology-changing mutations visible in archive diffs (will be validated when S03/S04 exercise the full stack)

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

Added a 7th test (`test_vocabulary_skeletons_use_primitives`) beyond the 6 specified in the plan — verifies skeletons don't contain raw provider imports like `import openai`.

## Known Limitations

- Vocabulary is static — doesn't discover primitives dynamically from the codebase. Adding a new primitive type requires updating `build_component_vocabulary()`.
- Pattern skeletons are illustrative, not validated — they show correct primitive usage but aren't tested as runnable pipelines.

## Follow-ups

- S03 will consume the vocabulary to balance structural vs parameter mutations
- S04 will use vocabulary and pattern examples for cold-start pipeline generation

## Files Created/Modified

- `src/autoagent/meta_agent.py` — Added `_PATTERNS` data structure, `build_component_vocabulary()` function, vocabulary section injection in `_build_prompt()`, structural mutation guidance in system instructions
- `tests/test_meta_agent.py` — Added 7 new tests in `TestComponentVocabulary` class

## Forward Intelligence

### What the next slice should know
- `build_component_vocabulary()` returns a plain string — S03/S04 can call it directly or rely on its presence in `_build_prompt()` output
- The vocabulary is injected between Goal and Benchmark sections — if S03 adds strategy signals to the prompt, place them after vocabulary or in system instructions

### What's fragile
- Vocabulary char count (3501) is tested with an 8K ceiling — adding patterns or expanding skeletons could approach the budget
- Pattern names are asserted by test — renaming a pattern breaks `test_vocabulary_contains_all_patterns`

### Authoritative diagnostics
- `build_component_vocabulary()` — pure function, call it to see exact vocabulary text
- `test_vocabulary_token_budget` — fails with exact char count if vocabulary exceeds budget

### What assumptions changed
- none — slice executed as planned
