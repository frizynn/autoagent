---
id: T02
parent: S03
milestone: M003
provides:
  - Leakage gate wired into OptimizationLoop (after TLA+, before evaluation)
  - ArchiveEntry.leakage_check field for post-run inspection
  - 5 integration tests proving gate behavior
key_files:
  - src/autoagent/archive.py
  - src/autoagent/loop.py
  - tests/test_loop_leakage.py
key_decisions:
  - Leakage gate follows exact same discard pattern as TLA+ gate (failed eval stub, archive, restore pipeline, continue)
  - leakage_check dict stores blocked/exact_matches/fuzzy_warnings/cost_usd — minimal but sufficient for inspection
patterns_established:
  - MockLeakageChecker test pattern mirrors MockTLAVerifier pattern from test_loop_verification.py
observability_surfaces:
  - leakage_check dict in archive JSON entries (blocked, exact_matches, fuzzy_warnings, cost_usd)
  - INFO log on blocked iterations with rationale
  - WARNING log per fuzzy warning when not blocked
duration: 15m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T02: Wire leakage gate into loop and archive

**Wired LeakageChecker into OptimizationLoop with archive persistence and 5 integration tests.**

## What Happened

Extended `ArchiveEntry` with optional `leakage_check: dict | None` field and updated `from_dict()` and `Archive.add()` to handle it. Added `leakage_checker` parameter to `OptimizationLoop.__init__()`. Inserted leakage gate after TLA+ verification gate and before evaluation — follows the identical discard pattern (zero-score eval stub, archive entry, restore pipeline, continue). Fuzzy warnings are logged at WARNING level per-warning. The `leakage_check` dict is passed to `archive.add()` for both blocked and normal evaluation paths.

## Verification

- `python3 -m pytest tests/test_loop_leakage.py -v` — 5/5 passed (blocked discard, warning proceeds, no checker skipped, cost tracking, JSON persistence)
- `python3 -m pytest tests/test_leakage.py -v` — 21/21 passed (T01 unit tests)
- `python3 -m pytest tests/ -v` — 357/357 passed, zero regressions
- Slice verification: all three check commands pass

## Diagnostics

- Read archive JSON entries for `leakage_check` field to inspect blocked/warning state
- Grep logs for "leakage" to find gate decisions (INFO for blocks, WARNING for fuzzy warnings)
- `leakage_check` is `None` when no checker configured — backward-compatible

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/archive.py` — Added `leakage_check` field to `ArchiveEntry`, `from_dict()`, and `Archive.add()`
- `src/autoagent/loop.py` — Added `LeakageChecker` import, `leakage_checker` parameter, leakage gate after TLA+ gate
- `tests/test_loop_leakage.py` — 5 integration tests for leakage gate behavior in the loop
