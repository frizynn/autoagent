---
id: S06
parent: M001
milestone: M001
provides:
  - Budget ceiling with auto-pause (phase="paused") and pre-iteration cost estimation
  - Crash recovery — resume from last committed iteration with archive state reconstruction
  - Pipeline.py restoration from archive on resume (prevents stale crash artifacts)
  - --budget CLI arg wired through config to OptimizationLoop
requires:
  - slice: S05
    provides: OptimizationLoop, MetaAgent, loop state protocol with state persistence
  - slice: S04
    provides: Archive with query() for reading history
  - slice: S02
    provides: StateManager, ProjectConfig, CLI scaffold
affects: []
key_files:
  - src/autoagent/loop.py
  - src/autoagent/cli.py
  - tests/test_loop.py
  - tests/test_cli.py
key_decisions:
  - Budget estimation uses global average cost (total_cost / total_iterations) rather than session-only — more accurate for resumed runs (D026)
  - Resume restores pipeline.py from archive's best kept entry, not from disk — prevents stale crash artifacts (D027)
patterns_established:
  - Budget check runs before each iteration (not after) to prevent overspending
  - Pre-iteration cost estimation skips when iterations_run==0 (can't estimate without data)
  - "paused" and "completed" phases both allow re-entry via transition to "running"
observability_surfaces:
  - ProjectState.phase="paused" — budget-triggered stop, distinct from "completed" and "running"
  - total_cost_usd and current_iteration show exactly where the loop stopped
  - autoagent status displays phase, cost, iteration — no new surfaces needed
drill_down_paths:
  - .gsd/milestones/M001/slices/S06/tasks/T01-SUMMARY.md
duration: 20m
verification_result: passed
completed_at: 2026-03-14
---

# S06: Budget, Recovery & Fire-and-Forget

**Hard budget ceiling with auto-pause, crash recovery with archive-based state reconstruction, and `--budget` CLI wiring — completing the fire-and-forget operational model.**

## What Happened

Single task slice. Added `budget_usd` parameter to `OptimizationLoop.__init__()`. The `run()` method now checks budget before each iteration — both a hard ceiling (`total_cost >= budget_usd`) and a pre-iteration estimate using global average cost per iteration. Budget exhaustion sets phase="paused" and returns cleanly.

Resume-from-state logic reconstructs `best_score` and `current_best_source` from the archive's best kept entry when `current_iteration > 0`. If disk has stale/proposed pipeline.py after a mid-iteration crash, it's restored from the archive's best kept pipeline source file. Both "paused" and "completed" phases allow re-entry to "running".

`--budget` CLI arg wired through `build_parser()` and `cmd_run()`, persisted to config. Output message distinguishes "Paused (budget)" from "Optimization complete".

## Verification

- `pytest tests/ -v` — 181 tests pass, zero regressions
- 8 new tests: budget pause, budget estimation pause, resume from state (iteration continuity), resume reconstructs best_score (correct keep/discard), resume restores pipeline from archive (crash recovery), resume from paused phase, all-discards resume edge case, CLI budget arg parsing
- Diagnostic: test_budget_pause verifies state.json has phase="paused", total_cost_usd > 0, current_iteration > 0

## Requirements Advanced

- R017 (Hard Budget Ceiling) — budget check before each iteration with pre-iteration estimation, phase="paused" on exhaustion
- R005 (Crash-Recoverable Disk State) — full crash recovery: kill/restart/resume from last committed iteration with archive reconstruction
- R019 (Fire-and-Forget Operation) — budget + recovery together enable unattended overnight runs

## Requirements Validated

- R005 — Crash recovery fully proven: atomic writes (S02), PID-based lock (S02), resume from archive (S06), pipeline restoration (S06)
- R017 — Hard budget ceiling with auto-pause proven by budget pause and estimation tests
- R019 — Fire-and-forget proven by combination of autonomous loop (S05), budget ceiling (S06), and crash recovery (S06)

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

None.

## Known Limitations

- Budget estimation is simple (global average) — could underestimate if later iterations are more expensive than earlier ones
- No notification mechanism on budget pause — user must check status manually

## Follow-ups

None — S06 is the terminal slice for M001.

## Files Created/Modified

- `src/autoagent/loop.py` — budget_usd param, resume-from-state logic, budget checks, phase="paused"
- `src/autoagent/cli.py` — --budget arg, config persistence, paused/complete output distinction
- `tests/test_loop.py` — 7 new tests for budget, resume, crash recovery
- `tests/test_cli.py` — 1 new test for --budget arg parsing

## Forward Intelligence

### What the next slice should know
- M001 is complete — all 6 slices delivered. Next work is M002 (Search Intelligence) or milestone-level UAT.
- The full loop works: init → run → propose → evaluate → keep/discard → archive → budget check → repeat/pause.

### What's fragile
- Budget estimation accuracy depends on cost consistency across iterations — wildly varying costs could cause premature pause or overshoot
- Resume logic assumes archive files are intact — corrupted archive entries will cause reconstruction failure (by design, per D021)

### Authoritative diagnostics
- `state.json` phase field — "paused" vs "completed" vs "running" is the single source of truth for loop status
- Archive iteration count vs state.current_iteration — mismatch indicates crash during write

### What assumptions changed
- None — implementation matched the plan exactly
