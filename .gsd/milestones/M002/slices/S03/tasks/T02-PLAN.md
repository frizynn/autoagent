---
estimated_steps: 5
estimated_files: 4
---

# T02: Wire strategy signals into prompt and optimization loop

**Slice:** S03 — Strategy Selection & Parameter Optimization
**Milestone:** M002

## Description

Thread strategy signals from the stagnation detector through the meta-agent prompt and optimization loop. Add `strategy_signals` parameter to `_build_prompt()` and `propose()`, insert a `## Strategy Guidance` section in the prompt, call `analyze_strategy()` from the loop before proposing, and tag archive entries with `mutation_type` after evaluation.

## Steps

1. Add `strategy_signals: str = ""` parameter to `MetaAgent._build_prompt()`. When non-empty, append a `## Strategy Guidance\n{strategy_signals}` section after the history/archive summary section. Add same parameter to `MetaAgent.propose()` and forward it to `_build_prompt()`.

2. In `OptimizationLoop.run()`, after archive context gathering (after the summary block ~L255) and before `propose()` (~L272): import and call `analyze_strategy()` with `self.archive.recent(10)`. Pass the result as `strategy_signals=` to `meta_agent.propose()`. Log the strategy signal at INFO level via `autoagent.loop` logger when non-empty.

3. After the archive `add()` call in the loop (both keep and discard paths): classify the mutation diff via `classify_mutation(pipeline_diff)` and pass `mutation_type=` to `archive.add()`. Update `Archive.add()` to accept and forward `mutation_type` to `ArchiveEntry` constructor.

4. Write tests in `tests/test_meta_agent.py`:
   - `test_strategy_signals_in_prompt`: verify `## Strategy Guidance` section appears when `strategy_signals` is non-empty
   - `test_strategy_signals_empty_omitted`: verify section is absent when signals empty
   - `test_propose_forwards_strategy_signals`: verify `propose()` passes signals through to `_build_prompt()`

5. Write `tests/test_loop_strategy.py` integration tests:
   - `test_loop_calls_strategy_detector`: mock `analyze_strategy`, verify it's called with recent entries during loop iteration
   - `test_loop_passes_strategy_signals_to_propose`: verify strategy signals flow from detector → propose()
   - `test_loop_sets_mutation_type_on_archive_entry`: verify archive entries get `mutation_type` field set after evaluation
   - `test_loop_strategy_with_summary`: verify strategy detection works alongside archive summaries (not conflicting)
   - Run full test suite for regression check

## Must-Haves

- [ ] `_build_prompt()` accepts `strategy_signals` and renders `## Strategy Guidance` section
- [ ] `propose()` accepts and forwards `strategy_signals`
- [ ] Loop calls `analyze_strategy()` before `propose()` and passes result
- [ ] Loop calls `classify_mutation()` and sets `mutation_type` on archive entries
- [ ] `Archive.add()` accepts `mutation_type` parameter
- [ ] Strategy guidance section placed after history sections in prompt
- [ ] All new and existing tests pass

## Verification

- `pytest tests/test_meta_agent.py -v` — all pass including new strategy signal tests
- `pytest tests/test_loop_strategy.py -v` — all integration tests pass
- `pytest tests/ -v` — full suite green, no regressions

## Observability Impact

- Signals added/changed: Logger `autoagent.loop` at INFO — logs strategy signal text when non-empty; Logger `autoagent.loop` at DEBUG — logs mutation_type classification
- How a future agent inspects this: `_build_prompt()` output is a plain string — print to see Strategy Guidance section
- Failure state exposed: If strategy detector raises, loop should handle gracefully (empty signal string, log warning)

## Inputs

- `src/autoagent/strategy.py` — `analyze_strategy()` and `classify_mutation()` from T01
- `src/autoagent/archive.py` — `ArchiveEntry` with `mutation_type` field from T01
- `src/autoagent/meta_agent.py` — `_build_prompt()` (L224-299), `propose()` (L353-400)
- `src/autoagent/loop.py` — `OptimizationLoop.run()` (L210-290 archive context + propose block)
- T01-SUMMARY.md — any deviations or interface changes from T01

## Expected Output

- `src/autoagent/meta_agent.py` — `strategy_signals` parameter on `_build_prompt()` and `propose()`, `## Strategy Guidance` section
- `src/autoagent/loop.py` — strategy detector call before propose, mutation_type classification after evaluation
- `src/autoagent/archive.py` — `Archive.add()` accepts `mutation_type`
- `tests/test_meta_agent.py` — 3+ new strategy signal tests
- `tests/test_loop_strategy.py` — 4+ integration tests for loop wiring
