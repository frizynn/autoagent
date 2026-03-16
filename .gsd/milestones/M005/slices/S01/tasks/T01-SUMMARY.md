---
id: T01
parent: S01
milestone: M005
provides:
  - JSONL output mode for `autoagent run --jsonl`
  - event_callback parameter on OptimizationLoop
  - structured event schema (loop_start, iteration_start, iteration_end, loop_end, error)
key_files:
  - src/autoagent/cli.py
  - src/autoagent/loop.py
  - tests/test_cli_jsonl.py
key_decisions:
  - event_callback is an optional callable on OptimizationLoop (not a protocol/class) — keeps it simple and zero-overhead when unused
  - builtins.print override for stderr redirection rather than changing every print() call site — non-invasive, auto-captures any new print() calls
  - error event emitted via try/except/finally in loop.run() — catches all exceptions without refactoring the method body
patterns_established:
  - JSONL event emission via callback pattern — future event types can be added by calling self._emit() at new points in the loop
observability_surfaces:
  - JSONL events on stdout — machine-parseable iteration telemetry via `autoagent run --jsonl 2>/dev/null | jq .`
  - error event with message and iteration number on exceptions
duration: 25min
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Add JSONL output mode to Python CLI

**Added `--jsonl` flag to `autoagent run` that emits structured JSON line events to stdout, with human output redirected to stderr.**

## What Happened

Added an `event_callback` parameter to `OptimizationLoop.__init__()` — an optional callable that receives event dicts. Inserted `self._emit()` calls at five points in the loop: before the while-loop (`loop_start`), top of each iteration (`iteration_start`), after archive.add (`iteration_end`), after loop exit (`loop_end`), and in exception handler (`error`).

Added `--jsonl` flag to `build_parser()` on the `run` subparser. When active, `cmd_run()` overrides `builtins.print` to route all human output to stderr, and creates a JSONL callback that writes `json.dumps(event) + "\n"` to stdout with flush.

`iteration_end` events include all required fields: iteration, score, decision, cost_usd, elapsed_ms, best_iteration_id, rationale, mutation_type.

## Verification

- `pytest tests/test_cli_jsonl.py -v` — 10/10 passed (parser flags, callback validity, event types emitted, stderr redirect, error event, field completeness, non-JSONL unchanged)
- `pytest tests/test_cli.py -v` — 24/24 passed (no regressions)
- `pytest tests/test_loop.py -v` — 17/17 passed (event_callback=None by default, zero overhead)
- `pytest tests/ -q` — 479/479 passed (full suite, no regressions)

### Slice-level verification status (intermediate task):
- ✅ `pytest tests/test_cli_jsonl.py -v` — all pass
- ✅ `pytest tests/ -q` — 479 tests pass (exceeds 469+ threshold)
- ⬜ Manual pi verification — requires T02 (extension not yet built)

## Diagnostics

Inspect JSONL output: `autoagent run --jsonl 2>/dev/null | jq .`
Error events include iteration number and exception message for post-mortem debugging.

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/loop.py` — Added `event_callback` parameter, `_emit()` helper, event emissions at loop_start/iteration_start/iteration_end/loop_end/error
- `src/autoagent/cli.py` — Added `--jsonl` flag, JSONL callback wiring, builtins.print stderr redirect
- `tests/test_cli_jsonl.py` — New test file with 10 tests covering parser, callback, events, stderr redirect, error handling, field schema
