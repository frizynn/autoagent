# S06: Budget, Recovery & Fire-and-Forget

**Goal:** `autoagent run --budget 5.00` respects a hard dollar ceiling with auto-pause; a killed process resumes from its last committed iteration on restart; fire-and-forget operation works end-to-end.
**Demo:** (1) Run with `--budget 0.05`, watch it pause before overspending. (2) Run 2 iterations, kill, restart, see it resume from iteration 2. (3) Both together prove fire-and-forget.

## Must-Haves

- Budget check before each iteration — loop pauses when `total_cost >= budget_usd`
- Pre-iteration cost estimation — skip if estimated next iteration would exceed budget
- "paused" phase in state for budget-triggered stops (distinct from "completed")
- Resume from persisted state — reconstruct `best_score` and `current_best_source` from archive on restart
- Restore best pipeline.py from archive if disk has stale/proposed source after mid-iteration crash
- `--budget` CLI arg wired to loop and persisted in config
- Phase transition on resume: paused/running (stale) → running

## Proof Level

- This slice proves: operational
- Real runtime required: no (deterministic mocks sufficient — budget/resume are state machine behaviors)
- Human/UAT required: no

## Verification

- `pytest tests/test_loop.py -v` — all existing tests pass (no regressions) plus new tests:
  - Budget pause: loop stops when cost exceeds budget, phase="paused"
  - Budget estimation: loop stops before starting an iteration that would likely exceed remaining budget
  - Resume from state: run 2 iterations, construct new loop with same state/archive, run 2 more, final state has 4 iterations
  - Resume reconstructs best_score: resumed loop makes correct keep/discard decisions based on archive history
  - Resume restores pipeline from archive: after simulated mid-iteration crash (stale proposed source on disk), resume restores the best kept pipeline
  - Resume from "paused" phase: increase budget, re-run, loop continues
  - All-discards resume: resume works when archive has no kept entries (best_score stays None)
- `pytest tests/test_cli.py -v` — `--budget` arg parses and wires to loop
- `pytest tests/ -v` — full suite green, zero regressions
- Diagnostic check: after budget pause, `state.json` on disk has `phase="paused"`, `total_cost_usd > 0`, and `current_iteration > 0` — verifiable via `StateManager.read_state()`

## Observability / Diagnostics

- Runtime signals: `ProjectState.phase="paused"` on budget stop; `current_iteration` and `total_cost_usd` show exactly where it stopped
- Inspection surfaces: `autoagent status` shows phase, cost, iteration — no new surfaces needed, existing ones cover it
- Failure visibility: budget pause is not a failure — it's a clean stop with phase="paused" distinguishable from "completed" and "running"

## Integration Closure

- Upstream surfaces consumed: `OptimizationLoop` (S05), `Archive.query()` (S04), `StateManager` (S02), `ProjectConfig.budget_usd` (S02), `ProjectState.total_cost_usd` (S05)
- New wiring introduced: `--budget` CLI → `ProjectConfig.budget_usd` → `OptimizationLoop` constructor → budget check in `run()`
- What remains before the milestone is truly usable end-to-end: nothing — S06 is the terminal slice

## Tasks

- [x] **T01: Add budget ceiling, crash recovery, and --budget CLI wiring** `est:45m`
  - Why: All three capabilities (budget, recovery, CLI) are tightly coupled — budget check and resume logic both modify the same `run()` method, and `--budget` is trivial CLI plumbing. Splitting would create artificial task boundaries.
  - Files: `src/autoagent/loop.py`, `src/autoagent/cli.py`, `tests/test_loop.py`, `tests/test_cli.py`
  - Do: (1) Add `budget_usd` param to `OptimizationLoop.__init__()`. (2) Add resume-from-state logic at top of `run()`: if `state.current_iteration > 0`, reconstruct `best_score` and `current_best_source` from archive (best kept entry's pipeline source file), restore pipeline.py on disk if stale. (3) Add budget check before each iteration: if `total_cost >= budget_usd`, set phase="paused" and break. Add cost estimation using average from prior iterations. (4) Allow "paused" → "running" phase transition on resume. (5) Wire `--budget` in `build_parser()` and `cmd_run()`, persist to config. (6) Write tests for budget pause, resume from state, resume from paused, all-discards edge case, pipeline restoration on resume.
  - Verify: `pytest tests/ -v` — all tests pass including ≥7 new tests
  - Done when: budget-triggered pause sets phase="paused", kill/restart resumes from last committed iteration with correct best_score, `--budget` wired end-to-end, full test suite green

## Files Likely Touched

- `src/autoagent/loop.py`
- `src/autoagent/cli.py`
- `tests/test_loop.py`
- `tests/test_cli.py`
