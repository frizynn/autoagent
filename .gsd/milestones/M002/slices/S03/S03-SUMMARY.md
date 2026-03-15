---
id: S03
parent: M002
milestone: M002
provides:
  - analyze_strategy() graduated stagnation detector with sliding-window archive analysis
  - classify_mutation() heuristic distinguishing structural vs parametric diffs
  - mutation_type field on ArchiveEntry (optional, backward-compatible)
  - strategy_signals parameter threading through _build_prompt() and propose()
  - ## Strategy Guidance prompt section with graduated exploration/exploitation signals
  - Loop wiring — detector called before propose(), mutation_type set after evaluation
requires:
  - slice: S01
    provides: Archive summaries with score trend data (consumed by loop when summarizer active)
  - slice: S02
    provides: Component vocabulary in meta-agent prompt (structural options for exploration)
affects:
  - S04
key_files:
  - src/autoagent/strategy.py
  - src/autoagent/archive.py
  - src/autoagent/meta_agent.py
  - src/autoagent/loop.py
  - tests/test_strategy.py
  - tests/test_meta_agent.py
  - tests/test_loop_strategy.py
key_decisions:
  - Graduated signals via prompt text, not binary mode switching (D031)
  - Strategy selection via prompt signals, not explicit phases (D032)
  - Failed proposals default to mutation_type="parametric" — no real mutation occurred
  - Strategy detector failures produce empty signals (graceful degradation, logged as warning)
  - Removed return/yield from structural patterns — changing a return value is parametric
patterns_established:
  - Strategy functions are pure (no I/O, no LLM calls) — testable with synthetic ArchiveEntry data
  - Graduated signals use plain text with embedded diagnostic numbers (plateau length, variance, structural ratio)
  - MockLLM.last_prompt captures prompt for test assertions without monkey-patching
observability_surfaces:
  - analyze_strategy() and classify_mutation() are pure functions — callable in REPL with synthetic data
  - Logger autoagent.loop at INFO — strategy signal summary per iteration
  - Logger autoagent.loop at DEBUG — mutation_type classification result
  - Strategy detector failure logged as WARNING with exc_info
drill_down_paths:
  - .gsd/milestones/M002/slices/S03/tasks/T01-SUMMARY.md
  - .gsd/milestones/M002/slices/S03/tasks/T02-SUMMARY.md
duration: ~45m
verification_result: passed
completed_at: 2026-03-14
---

# S03: Strategy Selection & Parameter Optimization

**Stagnation detector analyzes sliding-window archive statistics and injects graduated strategy signals into the meta-agent prompt, autonomously balancing structural exploration vs parameter tuning with mutation type tracking on every archive entry.**

## What Happened

Built a pure-function strategy module (`strategy.py`) with two core functions:

`classify_mutation(diff)` — regex-based heuristic that detects structural changes (new function/class defs, primitive calls, control flow, imports) vs parametric changes (string/number tweaks). Used both for real-time classification in the loop and as fallback when `mutation_type` is not set on historical entries.

`analyze_strategy(entries, window=10, plateau_threshold=5)` — sliding-window analysis of recent archive entries computing plateau length, score variance, and structural diversity ratio. Returns graduated signals: empty when improving, parameter tuning suggestion when topology is strong, escalating structural/parametric guidance during plateau based on mutation diversity, and "fundamentally different approach" for extended mixed-type plateaus. All signals embed diagnostic numbers.

Added `mutation_type: str | None = None` to `ArchiveEntry` with backward-compatible deserialization — all 215 existing tests pass unchanged.

Wired everything through the optimization loop: `analyze_strategy()` is called with `archive.recent(10)` before each `propose()`, signals flow as `strategy_signals` parameter through `_build_prompt()` → `propose()`, and after evaluation `classify_mutation()` tags the archive entry. `_build_prompt()` renders a `## Strategy Guidance` section when signals are non-empty. Strategy detector failures degrade gracefully to empty signals.

## Verification

- `pytest tests/test_strategy.py -v` — 26 tests (mutation classification + stagnation detection)
- `pytest tests/test_meta_agent.py -v` — 42 tests (4 new strategy signal tests + no regressions)
- `pytest tests/test_loop_strategy.py -v` — 5 integration tests (detector called, signals forwarded, mutation_type set, summary compat, graceful failure)
- `pytest tests/ -v` — 250 tests pass, 0 failures, zero regressions
- Diagnostic: `analyze_strategy()` callable in REPL with synthetic entries, signal text includes plateau length and diversity ratio

## Requirements Advanced

- R012 (Parameter Optimization) — parameter-only mutations are a distinct mode; strategy signals guide toward parameter tuning when topology is performing well
- R013 (Autonomous Search Strategy) — meta-agent reads archive statistics and autonomously decides mutation type based on graduated prompt signals
- R024 (Exploration/Exploitation Balance) — stagnation detection with graduated signals balances exploration (structural changes during plateau) and exploitation (parameter tuning when improving)

## Requirements Validated

- none — R012, R013, R024 require end-to-end integration proof in S04 before validation

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

- Removed `return` and `yield` from structural control-flow regex patterns (planned as structural indicators, but they cause false positives — changing a return value is parametric)
- Added `MockLLM.last_prompt` field to `primitives.py` — not in plan but needed to test prompt content assertions
- Updated mock `propose()` signatures in `test_loop.py` and `test_loop_summarizer.py` to accept new `strategy_signals` parameter

## Known Limitations

- Stagnation detection relies on `primary_score` in evaluation results — entries without it are skipped in score analysis
- The plateau threshold (5) and window size (10) are configurable but not yet tuned against real workloads
- Strategy signals are English-language text — they influence the LLM through natural language, not structured constraints

## Follow-ups

- none — S04 (Cold-Start) is the next slice and exercises the full M002 stack

## Files Created/Modified

- `src/autoagent/strategy.py` — new module with `classify_mutation()` and `analyze_strategy()` pure functions
- `src/autoagent/archive.py` — added `mutation_type` field to `ArchiveEntry`, updated `from_dict()` and `Archive.add()`
- `src/autoagent/meta_agent.py` — added `strategy_signals` parameter to `_build_prompt()` and `propose()`, `## Strategy Guidance` section
- `src/autoagent/loop.py` — wired strategy detector before `propose()`, mutation classification after evaluation
- `src/autoagent/primitives.py` — added `last_prompt` tracking to `MockLLM`
- `tests/test_strategy.py` — 26 tests for mutation classification and stagnation detection
- `tests/test_meta_agent.py` — 4 new tests for strategy signal prompt integration
- `tests/test_loop_strategy.py` — 5 integration tests for loop wiring
- `tests/test_loop.py` — updated mock signatures for `strategy_signals` parameter
- `tests/test_loop_summarizer.py` — updated mock signatures for `strategy_signals` parameter

## Forward Intelligence

### What the next slice should know
- `propose()` now accepts `strategy_signals: str = ""` — cold-start generation should pass empty signals (no history to analyze)
- `Archive.add()` accepts `mutation_type` — cold-start's initial pipeline should be tagged (likely "structural")
- The loop's `_build_prompt()` renders vocabulary, archive summaries, and strategy guidance in that order — cold-start prompt should follow the same section ordering

### What's fragile
- Plateau detection depends on entries being newest-first from `archive.recent()` — if sort order changes, plateau_len computes wrong
- `classify_mutation()` uses regex patterns on raw diff text — unusual code patterns could be misclassified, but the fallback is conservative (defaults to "parametric")

### Authoritative diagnostics
- `pytest tests/test_strategy.py -v` — 26 tests covering all stagnation/classification paths
- `analyze_strategy()` in REPL with synthetic `ArchiveEntry` data — the most direct way to inspect signal quality

### What assumptions changed
- Originally planned return/yield as structural indicators — removed because changing a return value is parametric, not structural
