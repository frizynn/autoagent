---
id: T01
parent: S02
milestone: M005
provides:
  - "--json flag on autoagent new"
  - "Bidirectional JSON protocol for interview I/O"
  - "Protocol test suite (17 tests)"
key_files:
  - src/autoagent/cli.py
  - tests/test_cli_json_interview.py
key_decisions:
  - "Phase state read from orchestrator.phase rather than threading phase through input_fn signature — avoids changing InterviewOrchestrator API"
  - "Confirmation summary accumulated in print_fn closure then emitted as single confirm event — cleaner than splitting the orchestrator's _run_confirmation method"
  - "_build_json_orchestrator uses closures over the orchestrator instance to track state without modifying InterviewOrchestrator internals"
patterns_established:
  - "JSON protocol: prompt → answer strict request-response on stdout/stdin"
  - "_json_emit helper for flushed JSON line output"
  - "_build_json_orchestrator factory pattern for wiring JSON I/O into existing orchestrator"
observability_surfaces:
  - "JSON protocol messages on stdout — machine-parseable interview telemetry"
  - "error events with message field on Python-side failures"
  - "Runnable directly: autoagent new --json 2>/dev/null piped to jq for protocol debugging"
duration: 1 task
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Python `--json` interview protocol

**Added `--json` flag to `autoagent new` with bidirectional JSON protocol driving the interview via stdin/stdout.**

## What Happened

Added `--json` flag to the `new` subparser. When active, `cmd_new` redirects `builtins.print` to stderr (same pattern as `cmd_run --jsonl`) and builds a JSON-protocol orchestrator via `_build_json_orchestrator()`.

The JSON orchestrator wires custom `input_fn`/`print_fn` closures into `InterviewOrchestrator` without modifying the orchestrator class:

- `json_print_fn` routes text to `status` events for headers/banners, accumulates confirmation summary lines, and tracks the last question text for prompt events
- `json_input_fn` emits `prompt` or `confirm` events to stdout, reads one JSON line from stdin, handles `abort` → `KeyboardInterrupt` and EOF gracefully
- On completion, `_cmd_new_inner` emits `complete` with full config dict and context string

Protocol messages: `prompt`, `confirm`, `status`, `complete`, `error`, `abort` — strict request-response, no interleaving.

Refactored `cmd_new` into `cmd_new` (JSON mode setup/teardown + builtins.print redirect) and `_cmd_new_inner` (shared logic) to keep the JSON/interactive branching clean.

## Verification

- `pytest tests/test_cli_json_interview.py -v` — **17 tests pass** (≥8 required)
- `pytest tests/ -q` — **496 passed**, no regressions (479 baseline + 17 new)
- Manual: `echo '...' | autoagent new --json 2>/dev/null` produces valid JSON lines — all 6 phases emit prompts, confirm event has summary, complete event has valid config

### Slice-level verification status (T01 of 3):
- ✅ `pytest tests/test_cli_json_interview.py -v` — protocol tests pass
- ✅ `pytest tests/ -q` — full suite passes (496 tests)
- ⬜ TypeScript structural check — not yet implemented (T02/T03 scope)

## Diagnostics

- Pipe `autoagent new --json 2>/dev/null` to inspect protocol messages
- Error events include `{"type":"error","message":"..."}` with descriptive text
- Non-zero exit code on abort or EOF
- stderr captures all human-readable output in JSON mode

## Deviations

- Added `_json_emit` as a module-level helper (not in plan but needed by both `cmd_new` wrapper and closures)
- Extracted `_cmd_new_inner` to cleanly separate JSON setup/teardown from core logic — plan didn't specify this refactor but it keeps the builtins.print restore in a finally block

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/cli.py` — Added `--json` flag to parser, `_json_emit` helper, refactored `cmd_new` into wrapper + `_cmd_new_inner`, added `_build_json_orchestrator` factory
- `tests/test_cli_json_interview.py` — New test file with 17 tests covering protocol round-trip, vague follow-up, abort, EOF, stderr redirect, message format validation, overwrite skip
