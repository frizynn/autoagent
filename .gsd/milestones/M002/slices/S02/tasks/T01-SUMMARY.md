---
id: T01
parent: S02
milestone: M002
provides:
  - build_component_vocabulary() function returning structured vocabulary text
  - Vocabulary section injected into _build_prompt() output
  - Structural mutation guidance in system instructions
key_files:
  - src/autoagent/meta_agent.py
  - tests/test_meta_agent.py
key_decisions:
  - Built vocabulary from a _PATTERNS list of dicts — adding new patterns is one dict append
  - Vocabulary is 3501 chars (~875 tokens), well under the 8K char budget
  - Placed vocabulary between Goal and Benchmark sections in prompt
patterns_established:
  - Static prompt artifacts built from data structures for easy extension
observability_surfaces:
  - build_component_vocabulary() is a pure standalone function — callable in REPL to inspect output
  - _build_prompt() output is a plain string — print it to verify vocabulary placement
duration: 15m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Build component vocabulary and inject into meta-agent prompt

**Added `build_component_vocabulary()` with 6 architectural patterns, primitive signatures, and anti-pattern guidance; injected into `_build_prompt()` with structural mutation system instructions.**

## What Happened

Built `build_component_vocabulary()` in `meta_agent.py` using a `_PATTERNS` list of dicts (name, description, skeleton). Each of the 6 patterns (RAG, CAG, Debate, Reflexion, Ensemble, Reranking) has a 1-2 line description and a 5-10 line skeleton using `primitives.llm.complete()` / `primitives.retriever.retrieve()`. The function also documents both primitive signatures and lists anti-patterns (no raw provider imports, no hardcoded keys, must use primitives parameter).

Updated `_build_prompt()` system instructions with rule 5: "Consider changing the pipeline's architecture — not just tuning parameters — when the current approach has fundamental limitations."

Injected vocabulary as `## Component Vocabulary` section between Goal and Benchmark — always present since it's static content.

Added 7 new tests covering vocabulary content, injection, budget, and system instruction structural guidance.

## Verification

- `pytest tests/test_meta_agent.py -v` — 34/34 passed (27 existing + 7 new)
- Vocabulary output: 3501 chars, well under 8K budget
- All 6 patterns present, both primitive signatures present, anti-patterns present
- System instructions mention "architecture" in structural mutation rule

### Slice-level verification status
- ✅ `pytest tests/test_meta_agent.py -v` — all existing + new tests pass
- ✅ Vocabulary section present in prompt output
- ✅ Vocabulary contains all 6 pattern names and both primitive signatures
- ✅ Anti-patterns mentioned (hardcoded imports, missing primitives)
- ✅ System instructions reference structural changes
- ✅ Vocabulary builder produces output under 2K tokens (~8K chars)

## Diagnostics

- Call `build_component_vocabulary()` directly to inspect the full vocabulary text — pure function, no state
- Print `_build_prompt()` output to see vocabulary placement in the full prompt
- If vocabulary grows beyond budget, `test_vocabulary_token_budget` will fail with exact char count

## Deviations

Added a 7th test (`test_vocabulary_skeletons_use_primitives`) beyond the 6 specified — verifies skeletons don't contain raw provider imports.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/meta_agent.py` — Added `_PATTERNS` data structure, `build_component_vocabulary()` function, vocabulary section injection in `_build_prompt()`, structural mutation guidance in system instructions
- `tests/test_meta_agent.py` — Added 7 new tests in `TestComponentVocabulary` class
- `.gsd/milestones/M002/slices/S02/S02-PLAN.md` — Added Observability / Diagnostics section (pre-flight fix)
- `.gsd/milestones/M002/slices/S02/tasks/T01-PLAN.md` — Added Observability Impact section (pre-flight fix)
