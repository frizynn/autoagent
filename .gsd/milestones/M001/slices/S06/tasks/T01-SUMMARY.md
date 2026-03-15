---
id: T01
parent: S06
milestone: M001
provides:
  - Budget ceiling with auto-pause (phase="paused")
  - Crash recovery / resume-from-state with archive reconstruction
  - --budget CLI arg wired through to OptimizationLoop
key_files:
  - src/autoagent/loop.py
  - src/autoagent/cli.py
  - tests/test_loop.py
  - tests/test_cli.py
key_decisions:
  - Budget estimation uses global average cost (total_cost / total_iterations) rather than session-only average — more accurate for resumed runs
  - Resume restores pipeline.py from archive's best kept entry, not from disk — prevents stale crash artifacts from corrupting state
  - "paused" and "completed" phases both allow re-entry via transition to "running" — completed loops can be resumed if budget increases
patterns_established:
  - Budget check runs before each iteration (not after) to prevent overspending
  - Pre-iteration cost estimation skips when iterations_run==0 (can't estimate without data)
observability_surfaces:
  - ProjectState.phase="paused" — new phase for budget-triggered stops, distinct from "completed"
  - total_cost_usd and current_iteration show exactly where the loop stopped
duration: 20m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Add budget ceiling, crash recovery, and --budget CLI wiring

**Added budget-based auto-pause, crash recovery with archive state reconstruction, and `--budget` CLI arg to OptimizationLoop.**

## What Happened

Modified `OptimizationLoop.__init__()` to accept `budget_usd` parameter. Added resume-from-state logic at the top of `run()` that reconstructs `best_score` and `current_best_source` from the archive's best kept entry when `current_iteration > 0`. Added budget check before each iteration — both hard ceiling (`total_cost >= budget_usd`) and estimation (`total_cost + avg > budget_usd`). Budget exhaustion sets phase="paused" and returns immediately.

Wired `--budget` through `build_parser()` and `cmd_run()`. Budget is persisted to config and passed to the loop. Output message distinguishes "Paused (budget)" from "Optimization complete".

Wrote 8 new tests covering: budget pause, budget estimation pause, resume from state (iteration continuity), resume reconstructs best_score (correct keep/discard decisions), resume restores pipeline from archive (stale crash recovery), resume from paused phase (budget increase), all-discards resume edge case, and CLI budget arg parsing.

## Verification

- `pytest tests/test_loop.py -v` — 17 tests pass (10 existing + 7 new)
- `pytest tests/test_cli.py -v` — 12 tests pass (11 existing + 1 new)
- `pytest tests/ -v` — 181 tests pass, zero regressions
- Diagnostic check: test_budget_pause verifies state.json has phase="paused", total_cost_usd > 0, current_iteration > 0 after budget stop

## Diagnostics

- `autoagent status` shows phase="paused" + cost/iteration after budget stop
- `StateManager.read_state()` returns phase, total_cost_usd, current_iteration for programmatic inspection
- Budget pause is a clean operational signal — distinguishable from "completed" and "running" via the phase field

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/loop.py` — Added `budget_usd` param, resume-from-state logic, budget checks before iterations, phase="paused" support
- `src/autoagent/cli.py` — Added `--budget` arg, config persistence, paused/complete output distinction
- `tests/test_loop.py` — 7 new tests for budget pause, estimation, resume, crash recovery, edge cases
- `tests/test_cli.py` — 1 new test for `--budget` arg parsing
