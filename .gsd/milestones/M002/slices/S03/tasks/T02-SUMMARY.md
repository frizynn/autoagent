---
id: T02
parent: S03
milestone: M002
provides:
  - strategy_signals parameter on _build_prompt() and propose() with ## Strategy Guidance section
  - Loop wiring: analyze_strategy() called before propose(), classify_mutation() called after evaluation
  - Archive.add() accepts mutation_type parameter and forwards to ArchiveEntry
key_files:
  - src/autoagent/meta_agent.py
  - src/autoagent/loop.py
  - src/autoagent/archive.py
  - tests/test_meta_agent.py
  - tests/test_loop_strategy.py
key_decisions:
  - Failed proposals get mutation_type="parametric" — no real mutation occurred, consistent default
  - Mutation classification in loop computes diff from parent pipeline file on disk rather than using proposal source directly — matches how Archive.add() computes its own diff
  - Strategy detector failure is caught and produces empty signals (graceful degradation, logged as warning)
patterns_established:
  - MockLLM.last_prompt captures the prompt sent to LLM — enables test assertions on prompt content without monkey-patching
observability_surfaces:
  - Logger autoagent.loop at INFO — logs strategy signal text when non-empty
  - Logger autoagent.loop at DEBUG — logs mutation_type classification result
  - Strategy detector failure logged as WARNING with exc_info
duration: ~25m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T02: Wire strategy signals into prompt and optimization loop

**Threaded strategy signals from stagnation detector through meta-agent prompt and optimization loop — `_build_prompt()` renders `## Strategy Guidance` section, loop calls `analyze_strategy()` before proposing and tags archive entries with `mutation_type` after evaluation.**

## What Happened

Added `strategy_signals: str = ""` parameter to both `_build_prompt()` and `propose()` in `meta_agent.py`. When non-empty, a `## Strategy Guidance` section is appended after the history/archive sections in the prompt. `propose()` forwards the parameter to `_build_prompt()`.

In `loop.py`, imported `analyze_strategy` and `classify_mutation` from `strategy.py`. Before each `propose()` call, the loop fetches `archive.recent(10)` and calls `analyze_strategy()`, passing the result as `strategy_signals`. The call is wrapped in try/except for graceful degradation. After evaluation, the loop computes the mutation diff from the parent pipeline file and classifies it via `classify_mutation()`, passing `mutation_type` to `archive.add()`.

Updated `Archive.add()` to accept `mutation_type` and forward it to the `ArchiveEntry` constructor.

Added `last_prompt` tracking to `MockLLM` to enable test assertions on prompt content.

Updated existing mock `propose()` signatures in `test_loop.py` and `test_loop_summarizer.py` to accept the new `strategy_signals` parameter.

## Verification

- `pytest tests/test_meta_agent.py -v` — 42 tests pass including 4 new strategy signal tests
- `pytest tests/test_loop_strategy.py -v` — 5 integration tests pass (detector called, signals forwarded, mutation_type set, summary compatibility, graceful failure)
- `pytest tests/test_strategy.py -v` — 21 tests pass (T01 contract tests)
- `pytest tests/ -v` — 250 tests pass, 0 failures, no regressions

## Diagnostics

- `_build_prompt()` output is a plain string — print it to see `## Strategy Guidance` section when signals are present
- Logger `autoagent.loop` at INFO shows strategy signal text each iteration
- Logger `autoagent.loop` at DEBUG shows mutation_type classification
- If strategy detector raises, loop logs WARNING with traceback and proceeds with empty signals

## Deviations

- Added `MockLLM.last_prompt` field to `src/autoagent/primitives.py` — not in task plan but needed to test that `propose()` correctly forwards strategy signals through to the LLM prompt
- Updated mock `propose()` signatures in `test_loop.py` and `test_loop_summarizer.py` to accept `strategy_signals` — necessary for existing tests to work with the new parameter

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/meta_agent.py` — Added `strategy_signals` parameter to `_build_prompt()` and `propose()`, `## Strategy Guidance` section rendering
- `src/autoagent/loop.py` — Imported strategy functions, wired `analyze_strategy()` before `propose()`, `classify_mutation()` after evaluation, `mutation_type` on `archive.add()` calls
- `src/autoagent/archive.py` — `Archive.add()` accepts `mutation_type` parameter, forwards to `ArchiveEntry` constructor
- `src/autoagent/primitives.py` — Added `last_prompt` tracking to `MockLLM`
- `tests/test_meta_agent.py` — 4 new tests in `TestStrategySignals` class
- `tests/test_loop_strategy.py` — New file with 5 integration tests for loop wiring
- `tests/test_loop.py` — Updated mock `propose()` signature to accept `strategy_signals`
- `tests/test_loop_summarizer.py` — Updated mock `propose()` signature to accept `strategy_signals`
