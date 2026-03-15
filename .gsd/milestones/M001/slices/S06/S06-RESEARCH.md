# S06: Budget, Recovery & Fire-and-Forget — Research

**Date:** 2026-03-14

## Summary

S06 adds three capabilities to the existing OptimizationLoop: (1) hard budget ceiling with auto-pause, (2) crash recovery via resume from disk state, and (3) `--budget` CLI integration. The codebase is well-prepared — `ProjectConfig.budget_usd` already exists, `ProjectState.total_cost_usd` accumulates correctly, `StateManager` has PID-based stale lock detection, and archive entries are crash-durable. The main work is modifying `OptimizationLoop.run()` to check budget before each iteration, resume from persisted state instead of starting from scratch, and adding a "paused" phase for budget-triggered stops.

The risk is moderate. Budget checking is straightforward (compare `total_cost` against ceiling before each iteration). Recovery is the trickiest part: the loop must reconstruct `best_score` from archive on restart, and handle the edge case where a crash happened mid-iteration (proposed source written to disk but not yet evaluated). Fire-and-forget is proven by the combination of budget + recovery working together.

## Recommendation

Modify `OptimizationLoop` in-place rather than introducing new classes. Three changes to `loop.py`:

1. **Budget check**: Accept `budget_usd: float | None` in constructor. Before each iteration, check `total_cost >= budget_usd` → set phase="paused", break. Also estimate whether next iteration would exceed budget (using average cost from prior iterations or a simple heuristic).
2. **Resume from state**: On `run()` entry, if `state.current_iteration > 0`, reconstruct `best_score` and `current_best_source` from archive (find the best kept entry). Start iteration counter from `state.current_iteration` instead of 0.
3. **"paused" phase**: Add alongside initialized/running/completed. Budget pause → "paused". Resume from paused is allowed (user increases budget, re-runs).

Wire `--budget` in CLI's `build_parser()` and `cmd_run()`. Pass to `OptimizationLoop`. Also write `budget_usd` into `ProjectConfig` on `cmd_run` if provided.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Atomic state writes | `_atomic_write_json()` in `state.py` | Already handles fsync + os.replace; crash-safe |
| Stale lock detection | `StateManager.acquire_lock()` with `_pid_alive()` | PID-based detection already handles kill -9 case |
| Cost tracking | `ProjectState.total_cost_usd` | Already accumulates meta-agent + evaluation costs per iteration |
| Archive reconstruction | `Archive.query(decision="keep", sort_by="primary_score")` | Can find best kept entry to reconstruct best_score on resume |

## Existing Code and Patterns

- `src/autoagent/loop.py` — `OptimizationLoop.run()` is the single method to modify. Currently starts from scratch, has no budget check, no resume logic. The `finally` block releases the lock.
- `src/autoagent/state.py` — `ProjectConfig.budget_usd: float | None = None` already exists but is never read. `ProjectState` has `phase`, `current_iteration`, `best_iteration_id`, `total_cost_usd` — all needed for resume. `StateManager.acquire_lock()` handles stale locks via PID check.
- `src/autoagent/cli.py` — `cmd_run` reads config, builds loop, calls `loop.run()`. Needs `--budget` arg and wiring to loop + config.
- `src/autoagent/archive.py` — `Archive.query()` and `Archive.get()` support reconstruction. `_next_iteration_id()` scans filenames — already crash-safe (derives ID from disk, not memory).
- `tests/test_loop.py` — `SequentialMockMetaAgent` pattern works well for testing budget and recovery scenarios.

## Constraints

- Zero runtime dependencies — all stdlib (no signal handlers from third-party libs)
- `kill -9` won't execute `finally` blocks — stale lock detection via PID is the only recovery mechanism
- `ProjectState` and `ProjectConfig` are frozen dataclasses — must use `dataclasses.replace()` for mutations
- Archive entries are immutable once written — crash mid-write leaves partial files (but `_atomic_write_json` prevents this via temp+rename)
- State is written after each complete iteration — a crash mid-iteration means the iteration is lost (acceptable; it will be re-proposed)

## Common Pitfalls

- **Reconstructing best_score from archive on resume** — Must handle the case where all entries are discards (no kept entries). `best_score` stays None, next successful eval is kept. Also must handle the case where `best_iteration_id` in state doesn't match any archive entry (corrupted state).
- **Budget check timing** — Check before starting the iteration, not after. Checking after means you've already spent the money. Checking before with average-cost estimation is more conservative.
- **Mid-iteration crash pipeline state** — If crash happens after writing proposed source but before evaluation, pipeline.py on disk has the proposed (unevaluated) source. On resume, need to restore the best pipeline from archive before continuing.
- **Phase transitions on resume** — A process resuming from "paused" or "running" (stale) state should transition back to "running". Don't skip the phase check.
- **Lock acquisition on resume** — `acquire_lock()` already handles stale locks, but the resumed process must re-acquire the lock before modifying state.

## Open Risks

- **Cost estimation accuracy** — Pre-iteration budget check can underestimate if the next iteration is unusually expensive (e.g., very long LLM response). Acceptable for M001 — the check prevents gross overspend, not exact-penny precision.
- **Concurrent runs** — Two processes racing to acquire the lock after a crash. PID-based locking is non-atomic (TOCTOU between reading lock file and writing new one). Acceptable for single-user M001 use case.

## Requirements Targeted

- **R005 (Crash-Recoverable Disk State)** — primary owner. Kill at any point, restart, continue from last committed iteration. Proven by kill/restart test.
- **R017 (Hard Budget Ceiling with Auto-Pause)** — primary owner. Dollar ceiling that auto-pauses the loop before overspending. Proven by budget-triggered pause test.
- **R019 (Fire-and-Forget Operation)** — primary owner. Launch with goal and budget, check results later. Proven by combination of budget + recovery + unattended operation.
- **R001 (Autonomous Optimization Loop)** — supporting. Budget/recovery make the loop production-viable.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Python stdlib | n/a | No skill needed — pure stdlib work |

## Sources

- S05 summary forward intelligence (inlined context above) — key signals about lock behavior, state persistence, cost tracking
- Existing codebase exploration — `loop.py`, `state.py`, `cli.py`, `archive.py`
