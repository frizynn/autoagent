---
id: T02
parent: S05
milestone: M001
provides:
  - OptimizationLoop class with run() method (propose→evaluate→keep/discard cycle)
  - cmd_run wired to loop with --max-iterations CLI arg
key_files:
  - src/autoagent/loop.py
  - src/autoagent/cli.py
  - tests/test_loop.py
key_decisions:
  - PipelineRunner allowed_root must be passed through Evaluator for tests running in tmp_path
  - First successful evaluation always kept (best_score starts None, any score >= None → keep)
  - MetaAgent failures produce zero-score EvaluationResult stubs for archive consistency
patterns_established:
  - SequentialMockMetaAgent pattern for deterministic loop testing
observability_surfaces:
  - ProjectState.phase transitions (initialized→running→completed)
  - current_iteration increments per iteration
  - total_cost_usd accumulates meta-agent + evaluation costs
  - MetaAgent failures recorded as discard entries with "proposal_error:" prefix in rationale
duration: 15m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T02: Build OptimizationLoop, wire cmd_run, and prove ≥3 autonomous iterations

**Built OptimizationLoop orchestrator: ties MetaAgent, Evaluator, Archive, and StateManager into autonomous propose→evaluate→keep/discard cycle. Wired cmd_run with --max-iterations. 10 integration tests prove ≥3 iterations with correct state persistence, keep/discard logic, and failure handling.**

## What Happened

Created `OptimizationLoop` in `loop.py` that:
1. Acquires lock, transitions phase to "running", persists state
2. Reads current pipeline source from disk
3. For each iteration: calls MetaAgent.propose(), handles failures as discards, writes proposed source to disk, evaluates via Evaluator, compares primary_score to best, keeps or discards, archives the entry, restores previous best on disk if discard, persists state atomically
4. Transitions to "completed", releases lock in finally block

Wired `cmd_run` in cli.py to read config, load benchmark, instantiate all components (MockLLM for now), and run the loop. Added `--max-iterations` arg to the `run` subcommand.

Wrote 10 integration tests covering: ≥3 iterations complete, keep/discard decisions based on score, state persistence, meta-agent failure handling, first-iteration-always-kept, cost accumulation, pipeline-on-disk-reflects-best, phase transitions, archive entry completeness, lock release on exception.

Fixed a subtle issue: PipelineRunner's `allowed_root` defaults to cwd, but tests use `tmp_path`. Created `_make_evaluator(tmp_path)` helper to pass correct allowed_root through. Updated existing `test_cli.py::TestRun` to reflect that `cmd_run` now requires a configured benchmark rather than being a stub.

## Verification

- `pytest tests/test_loop.py -v` — 10/10 passed
- `pytest tests/test_meta_agent.py -v` — 25/25 passed
- `pytest tests/ -v` — 173/173 passed, zero regressions
- `autoagent run --help` — shows --max-iterations option

### Slice-level verification status (T02 is final task):
- ✅ `pytest tests/test_meta_agent.py -v` — passes (25 tests)
- ✅ `pytest tests/test_loop.py -v` — passes (10 tests)
- ✅ `pytest tests/ -v` — full suite passes (173 tests)
- ✅ MetaAgent compile/validation failures produce discard entries with error rationale

## Diagnostics

- `ProjectState.phase` — check via `autoagent status` or `sm.read_state().phase`
- `ProjectState.current_iteration` — increments each iteration
- `ProjectState.total_cost_usd` — accumulates meta-agent + evaluation costs
- Failed proposals: archive entry rationale starts with `"proposal_error:"` followed by the MetaAgent error string
- Lock released in finally block — inspect `sm.lock_path.exists()` to verify

## Deviations

- Updated `tests/test_cli.py::TestRun::test_run_after_init` → `test_run_no_benchmark_configured` since cmd_run is no longer a stub and correctly requires a benchmark. Added `test_run_max_iterations_help` test.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/loop.py` — OptimizationLoop class with run() method
- `src/autoagent/cli.py` — cmd_run wired to loop, --max-iterations added, imports updated
- `tests/test_loop.py` — 10 integration tests for the optimization loop
- `tests/test_cli.py` — Updated TestRun to reflect cmd_run no longer being a stub
