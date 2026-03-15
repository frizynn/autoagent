# S06: Budget, Recovery & Fire-and-Forget — UAT

**Milestone:** M001
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: Budget and recovery are state machine behaviors — deterministic mocks fully exercise all transitions without requiring real LLM calls or dollar spend

## Preconditions

- Repository cloned with `.venv` active
- `pip install -e .` completed (autoagent importable)
- All 181 tests passing: `.venv/bin/python -m pytest tests/ -v`

## Smoke Test

Run `pytest tests/test_loop.py::TestBudgetAndRecovery -v` — all 7 budget/recovery tests pass in < 2 seconds.

## Test Cases

### 1. Budget pause stops loop before overspending

1. Create an OptimizationLoop with `budget_usd=0.05` and a mock meta-agent that generates valid pipeline mutations
2. Configure mock evaluation to report cost_usd=0.02 per iteration
3. Run the loop with `max_iterations=10`
4. **Expected:** Loop stops after 2-3 iterations. State phase is "paused". `total_cost_usd > 0`. `current_iteration > 0`. Loop did NOT run all 10 iterations.

### 2. Budget estimation prevents starting an iteration that would exceed remaining budget

1. Create an OptimizationLoop with `budget_usd=0.05`
2. Run 2 iterations at cost_usd=0.02 each (total: 0.04, remaining: 0.01)
3. Average cost per iteration is 0.02, which exceeds remaining 0.01
4. **Expected:** Loop pauses before starting iteration 3, even though total_cost (0.04) < budget (0.05). Phase is "paused".

### 3. Resume from state continues iteration numbering

1. Run loop for 2 iterations, then stop
2. Create a new OptimizationLoop with the same state directory and archive
3. Run again with `max_iterations=2`
4. **Expected:** New run starts from iteration 3 (not 1). Final state shows `current_iteration=4`. Archive contains 4 total entries.

### 4. Resume reconstructs best_score for correct keep/discard decisions

1. Run loop for 2 iterations where iteration 1 scores 0.8 (kept) and iteration 2 scores 0.6 (discarded)
2. Create a new loop instance with the same state/archive
3. Run iteration 3 with score 0.7
4. **Expected:** Iteration 3 is discarded (0.7 < 0.8 best from archive). The resumed loop correctly reconstructed best_score=0.8 from archive history.

### 5. Resume restores pipeline.py from archive after mid-iteration crash

1. Run loop for 2 iterations, with iteration 1 kept (score 0.8)
2. Simulate mid-iteration crash: write garbage/proposed source to pipeline.py on disk
3. Create a new loop instance, run it
4. **Expected:** On resume, pipeline.py is restored to the best kept version from the archive (iteration 1's source), not the stale/garbage on disk.

### 6. Resume from "paused" phase with increased budget

1. Run loop with `budget_usd=0.03`, let it pause after 1 iteration (cost 0.02)
2. Increase budget to 0.10
3. Create new loop instance with updated budget, run it
4. **Expected:** Loop transitions from "paused" to "running" and continues executing more iterations.

### 7. `--budget` CLI argument wiring

1. Parse CLI args: `autoagent run --budget 5.00`
2. **Expected:** Budget value `5.0` is captured and would be passed to OptimizationLoop as `budget_usd=5.0`

## Edge Cases

### All-discards resume

1. Run loop for 3 iterations where all produce scores lower than nothing (all discarded — best_score stays None or first iteration kept, rest discarded depending on logic)
2. Resume with new loop instance
3. **Expected:** Resume works correctly. If no kept entries exist, best_score is reconstructed as None and any new successful evaluation is kept.

### Zero budget

1. Create loop with `budget_usd=0.0`
2. Run the loop
3. **Expected:** Loop immediately pauses without running any iterations. Phase is "paused".

## Failure Signals

- Any test in `tests/test_loop.py` or `tests/test_cli.py` failing
- State phase stuck at "running" after budget should have triggered pause
- Resume starting iterations from 1 instead of continuing from last committed
- Pipeline.py containing stale/proposed source after resume instead of best kept version
- Keep/discard decisions after resume not matching archive history (wrong best_score reconstruction)

## Requirements Proved By This UAT

- R005 — Crash-recoverable disk state: kill at any point, restart, continue from last committed iteration (tests 3, 4, 5, 6)
- R017 — Hard budget ceiling with auto-pause: dollar ceiling prevents overspending (tests 1, 2)
- R019 — Fire-and-forget operation: budget + recovery together enable unattended runs (tests 1-6 combined)

## Not Proven By This UAT

- Real dollar tracking with live LLM providers — all costs are mocked
- Overnight multi-hour stability — would require extended live run
- Notification on budget pause — no notification mechanism exists (known limitation)
- Sandbox isolation (R021) — deferred to M003

## Notes for Tester

All test cases map directly to `tests/test_loop.py::TestBudgetAndRecovery` and `tests/test_cli.py`. Running the pytest suite exercises every scenario above with deterministic mocks. For manual UAT of fire-and-forget, run `autoagent init` in a temp directory, configure a real LLM provider, and run `autoagent run --budget 0.10` — it should pause within a few iterations.
