---
estimated_steps: 6
estimated_files: 4
---

# T01: Add budget ceiling, crash recovery, and --budget CLI wiring

**Slice:** S06 — Budget, Recovery & Fire-and-Forget
**Milestone:** M001

## Description

Modify `OptimizationLoop.run()` to support budget-based auto-pause and resume-from-state, then wire `--budget` through the CLI. The three capabilities share the same code path — budget checking and resume logic both live in the `run()` method's preamble and iteration loop. This is one coherent unit of work.

## Steps

1. **Add `budget_usd` param to `OptimizationLoop.__init__()`** — optional float, stored as instance attribute.

2. **Add resume-from-state logic at top of `run()`** — after reading state, if `current_iteration > 0`:
   - Query archive for best kept entry (`decision="keep"`, `sort_by="primary_score"`, `ascending=False`, `limit=1`)
   - If found: set `best_score` from its `primary_score`, read its pipeline source from `{iteration_id}-pipeline.py`, set as `current_best_source`, restore pipeline.py on disk
   - If no kept entries: `best_score` stays None, `current_best_source` from starter pipeline on disk
   - Handle phase transition: if phase is "paused" or "running" (stale lock), transition to "running"
   - Start iteration counter from `state.current_iteration` (existing code already does this)

3. **Add budget check before each iteration** — at top of while loop, before proposing:
   - If `budget_usd is not None` and `total_cost >= budget_usd`: set phase="paused", break
   - Estimate next iteration cost from average of prior iterations (if `iteration > 0`: `avg = total_cost / iterations_run`). If `total_cost + avg > budget_usd`: set phase="paused", break
   - If no prior iterations, skip estimation (can't estimate without data)

4. **Handle "paused" phase state transitions** — ensure "paused" → "running" is valid on resume. The phase="completed" terminal state should also allow re-entry if budget is increased (treat same as "paused").

5. **Wire `--budget` in CLI** — add `--budget` arg to `run_parser` in `build_parser()`. In `cmd_run()`, read from args, persist to config via `write_config(replace(config, budget_usd=budget))`, pass to `OptimizationLoop`. Print "Paused (budget)" vs "Optimization complete" based on final phase.

6. **Write tests** — add to `tests/test_loop.py`:
   - `test_budget_pause`: 3 proposals at $0.01 each, budget=$0.02 → pauses after 2, phase="paused"
   - `test_budget_estimation_pause`: budget set just above 2 iterations cost but below 3 → pauses after 2
   - `test_resume_from_state`: run 2 iterations, create new loop with same SM/archive, run 2 more → final iteration=4
   - `test_resume_reconstructs_best_score`: after resume, keep/discard decisions reflect archive history (not fresh start)
   - `test_resume_restores_pipeline_from_archive`: write stale source to pipeline.py, resume → pipeline restored from archive's best kept entry
   - `test_resume_from_paused_phase`: set phase="paused" in state, run with higher budget → continues
   - `test_resume_all_discards`: resume when all archive entries are discards → best_score stays None, first good eval is kept
   - Add to `tests/test_cli.py`: `test_run_budget_arg` — parse `--budget 5.00`, verify it reaches the loop

## Must-Haves

- [ ] Budget check runs before each iteration, not after (prevents overspending)
- [ ] Pre-iteration cost estimation using average of prior iterations
- [ ] Phase="paused" on budget stop (distinct from "completed")
- [ ] Resume reconstructs best_score from archive's best kept entry
- [ ] Resume restores pipeline.py from archive if disk source is stale
- [ ] `--budget` CLI arg wired through to OptimizationLoop
- [ ] All existing tests pass (zero regressions)
- [ ] ≥7 new tests covering budget, resume, and edge cases

## Verification

- `pytest tests/test_loop.py -v` — all old + new tests pass
- `pytest tests/test_cli.py -v` — budget arg test passes
- `pytest tests/ -v` — full suite green

## Observability Impact

- Signals added: `ProjectState.phase="paused"` — new terminal phase for budget-triggered stops
- How a future agent inspects this: `autoagent status` shows phase="paused" + total_cost_usd vs budget
- Failure state exposed: budget pause is a clean operational signal, not a failure — distinguishable via phase field

## Inputs

- `src/autoagent/loop.py` — current `OptimizationLoop.run()` with no budget/resume logic
- `src/autoagent/cli.py` — `cmd_run()` and `build_parser()` with no `--budget` arg
- `src/autoagent/archive.py` — `Archive.query()` for reconstructing best entry on resume
- `src/autoagent/state.py` — `ProjectConfig.budget_usd` already exists (never read), `ProjectState` has phase/iteration/cost fields
- `tests/test_loop.py` — `SequentialMockMetaAgent` pattern and helper functions for test setup

## Expected Output

- `src/autoagent/loop.py` — `OptimizationLoop` accepts `budget_usd`, checks budget before iterations, resumes from persisted state, supports "paused" phase
- `src/autoagent/cli.py` — `--budget` arg parsed, persisted to config, passed to loop
- `tests/test_loop.py` — ≥7 new tests proving budget pause, resume, and edge cases
- `tests/test_cli.py` — budget arg parsing test
