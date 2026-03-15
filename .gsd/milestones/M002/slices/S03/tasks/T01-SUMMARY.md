---
id: T01
parent: S03
milestone: M002
provides:
  - classify_mutation() heuristic for structural vs parametric diff classification
  - analyze_strategy() graduated stagnation detector with configurable window/threshold
  - mutation_type field on ArchiveEntry with backward-compatible deserialization
key_files:
  - src/autoagent/strategy.py
  - src/autoagent/archive.py
  - tests/test_strategy.py
key_decisions:
  - Removed return/yield from structural control-flow patterns — too noisy (changing a return value is parametric, not structural). New returns accompany new if/def blocks anyway.
patterns_established:
  - Strategy functions are pure (no I/O, no LLM calls) — testable with synthetic ArchiveEntry data
  - Graduated signals use plain text with embedded diagnostic numbers (plateau length, variance, structural ratio)
observability_surfaces:
  - analyze_strategy() and classify_mutation() are pure functions — callable in REPL with synthetic data
  - Signal text includes plateau length, score variance, and structural ratio for diagnostic inspection
duration: 20m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Build stagnation detector and mutation type infrastructure

**Added `mutation_type` field to `ArchiveEntry`, `classify_mutation()` diff heuristic, and `analyze_strategy()` graduated stagnation detector — all independently testable with synthetic data.**

## What Happened

Added `mutation_type: str | None = None` to the frozen `ArchiveEntry` dataclass with backward-compatible `from_dict()` using `.get()`. All 215 existing tests pass unchanged.

Created `src/autoagent/strategy.py` with two pure functions:

- `classify_mutation(diff)` — uses regex patterns to detect structural changes (new function/class defs, `primitives.*` calls, control flow keywords, imports) vs parametric changes (string/number tweaks, variable renames). Empty diffs return "parametric".

- `analyze_strategy(entries, window=10, plateau_threshold=5)` — takes newest-first entries, computes plateau length (consecutive recent iterations below window best), score variance, and structural diversity ratio. Returns graduated signals: empty when improving, parameter tuning suggestion when improving with high structural ratio, escalating structural/parametric guidance during plateau based on mutation diversity, and "fundamentally different approach" for extended mixed-type plateaus.

Wrote 26 tests covering both functions: structural/parametric diff classification, plateau detection at various severities, mutation type influence on recommendations, diff-based fallback when mutation_type is None, edge cases (single entry, oversized window, identical scores), signal content validation (diagnostic numbers, length bounds).

## Verification

- `pytest tests/test_strategy.py -v` — 26/26 passed
- `pytest tests/ -v` — 241 passed (215 original + 26 new), zero regressions

Slice-level checks (T01 is intermediate — partial passes expected):
- ✅ `pytest tests/test_strategy.py -v` — all pass
- ✅ `pytest tests/test_meta_agent.py -v` — 34 pass, no regressions (new strategy tests in T02)
- ⏳ `pytest tests/test_loop_strategy.py -v` — not yet created (T02)
- ✅ `pytest tests/ -v` — full suite green
- ✅ Diagnostic: `analyze_strategy()` output includes plateau length and diversity ratio in signal text

## Diagnostics

Call `analyze_strategy()` or `classify_mutation()` directly in REPL with synthetic `ArchiveEntry` data to inspect behavior. Signal text embeds diagnostic numbers — plateau length, score variance, structural ratio — making signal quality inspectable without additional tooling.

## Deviations

Removed `return` and `yield` from structural control-flow regex patterns. The plan included them, but they cause false positives — changing a return *value* (e.g., `return "hello"` → `return "goodbye"`) is parametric, not structural. New return statements typically accompany new `if`/`def` blocks which are caught by other patterns.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/strategy.py` — new module with `classify_mutation()` and `analyze_strategy()` pure functions
- `src/autoagent/archive.py` — added `mutation_type: str | None = None` field to `ArchiveEntry`, updated `from_dict()`
- `tests/test_strategy.py` — 26 tests covering mutation classification and stagnation detection
