# S02: Structural Search & Component Vocabulary

**Goal:** The meta-agent prompt includes a component vocabulary and structural mutation guidance, enabling topology-changing mutations — not just parameter tweaks.
**Demo:** `_build_prompt()` output includes a vocabulary section listing available primitives and architectural patterns (RAG, CAG, debate, reflexion, ensemble, reranking) with skeleton examples. System instructions encourage structural changes. Tests prove vocabulary injection and content.

## Must-Haves

- Component vocabulary listing `primitives.llm.complete()` and `primitives.retriever.retrieve()` with signatures
- Architectural pattern descriptions (RAG, CAG, debate, reflexion, ensemble, reranking) with compact skeletons using primitives interface
- Anti-pattern guidance (no `import openai`, no hardcoded providers, must use `primitives` parameter)
- Vocabulary injected as a section in `_build_prompt()` — always included (static content)
- System instructions updated to mention structural mutation as an option
- Vocabulary fits within ~2K tokens
- All existing meta-agent tests still pass

## Verification

- `pytest tests/test_meta_agent.py -v` — all existing + new tests pass
- New tests verify:
  - Vocabulary section present in prompt output
  - Vocabulary contains all 6 pattern names and both primitive signatures
  - Anti-patterns mentioned (hardcoded imports, missing primitives)
  - System instructions reference structural changes
  - Vocabulary builder produces output under 2K tokens (~8K chars)

## Observability / Diagnostics

- **Inspection surface:** `build_component_vocabulary()` is a pure function — call it directly in a REPL or test to inspect the full vocabulary text without running the meta-agent loop.
- **Prompt inspection:** `_build_prompt()` output is a plain string. Print it to verify vocabulary placement, system instruction wording, and section ordering.
- **Failure visibility:** If a pattern skeleton uses raw imports instead of `primitives.*`, `test_vocabulary_contains_anti_patterns` fails with a clear assertion showing the offending content.
- **Budget signal:** `test_vocabulary_token_budget` fails if vocabulary exceeds 8K chars, catching prompt bloat before it reaches production.
- **Redaction:** No secrets or API keys in vocabulary content — skeletons use `primitives` parameter exclusively.

## Verification (diagnostic / failure-path)

- `test_vocabulary_contains_anti_patterns` — verifies anti-pattern warnings are present, catches accidental removal of safety guidance
- `test_vocabulary_token_budget` — budget guard prevents vocabulary bloat from silently inflating prompt cost

## Integration Closure

- Upstream surfaces consumed: `MetaAgent._build_prompt()`, `primitives.py` protocol definitions
- New wiring introduced: vocabulary section added to `_build_prompt()` output, system instructions updated
- What remains before milestone is truly usable end-to-end: S03 (strategy signals), S04 (cold-start generation)

## Tasks

- [x] **T01: Build component vocabulary and inject into meta-agent prompt** `est:45m`
  - Why: This is the entire slice — build the vocabulary, update `_build_prompt()` and system instructions, test it
  - Files: `src/autoagent/meta_agent.py`, `tests/test_meta_agent.py`
  - Do: (1) Add a `build_component_vocabulary()` function that returns structured text listing primitives with signatures, 6 architectural patterns with 5-10 line skeletons each, and anti-patterns. Keep it compact (~2K tokens). (2) Add vocabulary section to `_build_prompt()` between Goal and Current Pipeline — always included. (3) Update system instructions to mention structural topology changes as an option. (4) Add tests for vocabulary content, injection, and token budget.
  - Verify: `pytest tests/test_meta_agent.py -v` — all 27+ existing tests pass, new tests pass
  - Done when: prompt output contains vocabulary section with all 6 patterns, both primitives, anti-patterns, and structural guidance in system instructions; vocabulary under ~8K chars

## Files Likely Touched

- `src/autoagent/meta_agent.py`
- `tests/test_meta_agent.py`
