---
estimated_steps: 5
estimated_files: 3
---

# T02: Build OptimizationLoop, wire cmd_run, and prove ≥3 autonomous iterations

**Slice:** S05 — The Optimization Loop
**Milestone:** M001

## Description

Build the `OptimizationLoop` orchestrator that ties MetaAgent, Evaluator, Archive, and StateManager together into the propose→evaluate→keep/discard cycle. Wire `cmd_run` in cli.py to instantiate and start the loop. Write integration tests proving ≥3 iterations run autonomously with correct state persistence, archive entries, and keep/discard decisions.

This is the assembly task — every upstream module is stable. The loop itself is straightforward plumbing, but it must handle MetaAgent failures (compile error, missing run) gracefully as discard iterations, persist state atomically after each iteration, and transition phase correctly.

## Steps

1. Create `src/autoagent/loop.py` with:
   - `OptimizationLoop` class accepting StateManager, Archive, Evaluator, MetaAgent, Benchmark, PipelineRunner, primitives_factory callable, and max_iterations (default None = unlimited)
   - `run()` method implementing the cycle:
     a. Acquire lock, set phase="running", persist state
     b. Read current best pipeline source from disk (pipeline_path from config)
     c. For each iteration up to max_iterations:
        - Call MetaAgent.propose(current_source, archive_entries)
        - If proposal failed → Archive.add() as discard with error rationale, increment iteration, continue
        - Write proposed source to pipeline_path on disk
        - Call Evaluator.evaluate(pipeline_path, benchmark, primitives_factory=factory)
        - Compare primary_score to current best score
        - Decision: keep if score >= best_score (or first iteration), discard otherwise
        - Archive.add() with decision, rationale from meta-agent, parent_iteration_id
        - If keep: update best_iteration_id, retain proposed source as current best
        - If discard: restore previous best pipeline source to disk
        - Update state: current_iteration, best_iteration_id, total_cost_usd (meta-agent cost + evaluation cost), updated_at
        - Persist state
     d. Set phase="completed", release lock
   - Exception handling: release lock in finally block, don't corrupt state on unexpected errors
   - First iteration handling: use baseline_source param on Archive.add() for initial diff; any first evaluation that succeeds is kept

2. Wire `cmd_run` in `src/autoagent/cli.py`:
   - Read config from StateManager to get goal, benchmark config, pipeline_path
   - Load Benchmark from config.benchmark dict (dataset_path, scoring_function)
   - Instantiate MetaAgent with a MockLLM (for now — real LLM provider selection is an S06/later concern, but the plumbing should accept any LLM)
   - Parse optional `--max-iterations` CLI argument
   - Instantiate OptimizationLoop and call .run()
   - Print summary on completion (iterations run, best score, total cost)

3. Write integration tests in `tests/test_loop.py`:
   - Create a mock meta-agent that returns deterministic pipeline mutations (varying quality to trigger both keep and discard decisions)
   - Test: ≥3 iterations complete, archive has ≥3 entries, state.current_iteration matches
   - Test: keep/discard decisions are correct based on primary_score comparison
   - Test: state persistence — read state after loop, verify current_iteration, best_iteration_id, phase="completed"
   - Test: meta-agent failure (returns invalid source) → discard entry in archive with error rationale
   - Test: first iteration is always kept (baseline establishment)
   - Test: total_cost_usd accumulates meta-agent + evaluation costs

4. Wire `--max-iterations` into the argparse `run` subcommand

5. Verify full test suite passes with zero regressions

## Must-Haves

- [ ] OptimizationLoop.run() executes ≥3 iterations autonomously with mock providers
- [ ] Each iteration produces an archive entry with metrics, diff, rationale, and decision
- [ ] Keep/discard decision is based on primary_score comparison to current best
- [ ] State (current_iteration, best_iteration_id, total_cost_usd, phase) persisted after every iteration
- [ ] Phase transitions: initialized→running→completed
- [ ] MetaAgent failures (invalid source) produce discard archive entries, don't halt the loop
- [ ] cmd_run is wired to instantiate and start the loop (no longer a stub)
- [ ] Pipeline on disk reflects current best after each iteration (restored on discard)

## Verification

- `pytest tests/test_loop.py -v` — all tests pass including ≥3 iteration test
- `pytest tests/ -v` — full suite passes, zero regressions
- `autoagent run --help` shows --max-iterations option

## Observability Impact

- Signals added: ProjectState.phase transitions (running/completed), current_iteration increments per iteration, total_cost_usd accumulates
- How a future agent inspects this: `autoagent status` after a run shows iteration count, best score, total cost; archive entries on disk show per-iteration decisions
- Failure state exposed: MetaAgent compile/validation failures recorded as discard entries with error field in archive JSON; loop exceptions leave state at last successful iteration

## Inputs

- `src/autoagent/meta_agent.py` — MetaAgent.propose() from T01
- `src/autoagent/evaluation.py` — Evaluator.evaluate()
- `src/autoagent/archive.py` — Archive.add()/query()/best()
- `src/autoagent/state.py` — StateManager.read_state()/write_state()/acquire_lock()/release_lock()
- `src/autoagent/pipeline.py` — PipelineRunner.run()
- `src/autoagent/benchmark.py` — Benchmark.from_file()
- `src/autoagent/cli.py` — cmd_run stub to replace
- `tests/fixtures/toy_benchmark.json` — benchmark for integration tests

## Expected Output

- `src/autoagent/loop.py` — OptimizationLoop class with run() method
- `src/autoagent/cli.py` — cmd_run wired to loop, --max-iterations arg added
- `tests/test_loop.py` — Integration tests proving ≥3 iterations, state persistence, keep/discard logic
