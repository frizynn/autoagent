---
estimated_steps: 5
estimated_files: 3
---

# T01: Add JSONL output mode to Python CLI

**Slice:** S01 — Live Dashboard with Streaming Subprocess
**Milestone:** M005

## Description

Add a `--jsonl` flag to `autoagent run` that switches output to structured JSON lines on stdout. This is the data contract that the pi extension (T02) consumes via spawn + line parsing. When `--jsonl` is active, human-readable output goes to stderr instead. The loop emits events at iteration boundaries: `loop_start`, `iteration_start`, `iteration_end`, `loop_end`, and `error`.

## Steps

1. Define the JSONL event schema as a set of TypedDicts or plain dicts with required keys: `{"event": str, "timestamp": str, ...}` with per-event fields. Events: `loop_start` (goal, budget_usd, phase), `iteration_start` (iteration), `iteration_end` (iteration, score, decision, cost_usd, elapsed_ms, best_iteration_id, rationale, mutation_type), `loop_end` (phase, total_iterations, total_cost_usd, best_iteration_id), `error` (message, iteration).
2. Add an `event_callback` parameter to `OptimizationLoop.__init__()` — an optional callable that receives event dicts. Insert callback calls at the right points in the loop: before the while-loop (loop_start), top of each iteration (iteration_start), after archive.add (iteration_end), after loop exit (loop_end), in exception handler (error). Keep it minimal — the callback is just `json.dumps(event) + "\n"` when JSONL is active, or `None` otherwise.
3. Add `--jsonl` flag to `build_parser()` on the `run` subparser. In `cmd_run()`, when `--jsonl` is set, redirect all `print()` calls to stderr and create the JSONL callback that writes to stdout with `sys.stdout.write(json.dumps(event) + "\n"); sys.stdout.flush()`.
4. Write `tests/test_cli_jsonl.py` testing: (a) `--jsonl` flag is accepted by parser, (b) JSONL callback produces valid JSON lines, (c) all event types are emitted during a mocked loop run, (d) human output goes to stderr not stdout when `--jsonl` active, (e) existing non-JSONL behavior unchanged.
5. Run full test suite to confirm no regressions.

## Must-Haves

- [ ] `autoagent run --jsonl` emits one JSON line per event to stdout
- [ ] Events include: loop_start, iteration_start, iteration_end, loop_end, error
- [ ] iteration_end events contain: iteration, score, decision, cost_usd, elapsed_ms, best_iteration_id, rationale, mutation_type
- [ ] Human-readable output redirected to stderr when --jsonl active
- [ ] Existing CLI behavior (without --jsonl) unchanged — test_cli.py passes
- [ ] Loop's event_callback is optional and defaults to None (zero overhead when unused)

## Verification

- `pytest tests/test_cli_jsonl.py -v` — all JSONL-specific tests pass
- `pytest tests/test_cli.py -v` — existing CLI tests pass unchanged
- `pytest tests/test_loop.py -v` — existing loop tests pass (event_callback=None by default)

## Observability Impact

- Signals added: Structured JSONL events on stdout — machine-parseable iteration telemetry
- How a future agent inspects this: `autoagent run --jsonl 2>/dev/null | jq .` to see raw events
- Failure state exposed: `error` event with message and iteration number on exceptions

## Inputs

- `src/autoagent/cli.py` — existing cmd_run implementation
- `src/autoagent/loop.py` — OptimizationLoop.run() method where events are emitted
- `tests/test_cli.py` — existing CLI test patterns to follow

## Expected Output

- `src/autoagent/cli.py` — modified with --jsonl flag, JSONL callback wiring, stderr redirection
- `src/autoagent/loop.py` — modified with event_callback parameter and callback calls at iteration boundaries
- `tests/test_cli_jsonl.py` — new test file with JSONL output verification
