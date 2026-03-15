# S02: Structural Search & Component Vocabulary — UAT

**Milestone:** M002
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: S02 produces static prompt content (vocabulary text) and prompt integration — no runtime behavior, no server, no live loop. All verification is through function output inspection and test assertions.

## Preconditions

- Python 3.11+ with project installed in dev mode (`.venv/bin/python -m pip install -e ".[dev]"`)
- All M001 tests passing (baseline)

## Smoke Test

Run `pytest tests/test_meta_agent.py::TestComponentVocabulary -v` — all 7 tests pass.

## Test Cases

### 1. Vocabulary contains all architectural patterns

1. Run: `from autoagent.meta_agent import build_component_vocabulary; v = build_component_vocabulary()`
2. Check `v` contains all 6 pattern names: "RAG", "CAG", "Debate", "Reflexion", "Ensemble", "Reranking"
3. **Expected:** All 6 pattern names appear in the vocabulary text, each with a description and a skeleton code block.

### 2. Vocabulary contains primitive signatures

1. Run: `from autoagent.meta_agent import build_component_vocabulary; v = build_component_vocabulary()`
2. Check `v` contains `primitives.llm.complete(` and `primitives.retriever.retrieve(`
3. **Expected:** Both primitive signatures are documented in the vocabulary.

### 3. Anti-pattern guidance present

1. Run: `from autoagent.meta_agent import build_component_vocabulary; v = build_component_vocabulary()`
2. Check `v` contains warnings about raw imports (e.g., `import openai`) and hardcoded providers
3. **Expected:** Anti-pattern section warns against bypassing the primitives interface.

### 4. Vocabulary injected into prompt output

1. Create a `MetaAgent` instance with a mock LLM
2. Call `_build_prompt(goal="test", current_source="...", kept_entries=[], discarded_entries=[])`
3. Check the returned prompt string contains `## Component Vocabulary`
4. **Expected:** Vocabulary section appears in the prompt, between Goal and Benchmark sections.

### 5. System instructions include structural mutation guidance

1. Create a `MetaAgent` instance and call `_build_prompt(...)` with any valid args
2. Inspect the system instructions section of the output
3. **Expected:** Instructions mention considering architecture changes, not just parameter tuning. The word "architecture" or "structural" appears in the guidance.

### 6. Vocabulary fits token budget

1. Run: `v = build_component_vocabulary(); len(v)`
2. **Expected:** Length is under 8000 characters (~2K tokens).

### 7. No existing tests broken

1. Run: `.venv/bin/python -m pytest tests/test_meta_agent.py -v`
2. **Expected:** All 34 tests pass (27 existing + 7 new). Zero failures, zero errors.

## Edge Cases

### Empty patterns list

1. If `_PATTERNS` were accidentally emptied, `build_component_vocabulary()` would still return the primitives and anti-patterns sections
2. **Expected:** `test_vocabulary_contains_all_patterns` would fail, catching this immediately.

### Vocabulary bloat

1. If a developer adds many patterns or expands skeletons significantly
2. **Expected:** `test_vocabulary_token_budget` fails with the exact character count, preventing silent prompt cost inflation.

### Skeleton using raw imports

1. If a pattern skeleton contains `import openai` or `from anthropic import ...`
2. **Expected:** `test_vocabulary_skeletons_use_primitives` fails, catching the anti-pattern in the vocabulary's own examples.

## Failure Signals

- Any test in `TestComponentVocabulary` failing
- `_build_prompt()` output missing `## Component Vocabulary` section
- Vocabulary char count exceeding 8000
- Pattern skeletons containing raw provider imports
- Existing `TestBuildPrompt` or `TestPropose` tests failing (regression)

## Requirements Proved By This UAT

- R011 (Structural Search) — partially proved: meta-agent prompt now includes component vocabulary and structural mutation guidance. Full proof requires end-to-end topology-changing mutations (S03/S04).

## Not Proven By This UAT

- Actual topology-changing mutations in the optimization loop (requires S03/S04 integration)
- Meta-agent producing structurally different pipelines based on vocabulary (runtime behavior)
- Archive diffs showing structural changes vs parameter tweaks (requires archive analysis)

## Notes for Tester

- All test cases map directly to pytest tests — run the test suite for automated verification
- `build_component_vocabulary()` is a pure function with no dependencies — safe to call in any REPL
- The vocabulary is static content, not dynamic — it doesn't change based on project state
