---
id: S02
parent: M005
milestone: M005
provides:
  - "Bidirectional JSON protocol for `autoagent new --json`"
  - "`/autoagent new` pi command wired to interview via subprocess"
  - "Protocol test suite (17 tests)"
requires:
  - slice: S01
    provides: "Extension scaffold with command routing, PYTHONUNBUFFERED=1 pattern"
affects:
  - S03
key_files:
  - src/autoagent/cli.py
  - tests/test_cli_json_interview.py
  - .pi/extensions/autoagent/interview-runner.ts
  - .pi/extensions/autoagent/index.ts
key_decisions:
  - "D071: Interview runner as standalone function, not SubprocessManager extension — bidirectional short-lived subprocess has different lifecycle than the unidirectional run singleton"
  - "D072: ctx.ui.input()/select() native dialogs, not custom overlay — interview is sequential input collection, not a persistent updating view"
  - "_build_json_orchestrator uses closures over the orchestrator instance to inject JSON I/O without modifying InterviewOrchestrator internals"
  - "Async line reader with bufferedLines/pendingWaiters pattern for strict request-response protocol handling"
patterns_established:
  - "JSON protocol: prompt/confirm/status/complete/error/abort message types with strict request-response on stdout/stdin"
  - "_json_emit helper for flushed JSON line output"
  - "_build_json_orchestrator factory pattern for wiring JSON I/O into existing orchestrator"
  - "nextLine() async reader: bufferedLines array + pendingWaiters array, readline feeds one, close resolves all waiters with null"
  - "writeLine(obj) helper: JSON.stringify + newline to subprocess stdin, guarded by !stdin.destroyed"
observability_surfaces:
  - "JSON protocol messages on stdout — machine-parseable interview telemetry"
  - "error events with message field on Python-side failures"
  - "Subprocess stderr captured (last 20 lines) included in error messages on unexpected exit"
  - "Runnable directly: autoagent new --json 2>/dev/null piped to jq for protocol debugging"
drill_down_paths:
  - .gsd/milestones/M005/slices/S02/tasks/T01-SUMMARY.md
  - .gsd/milestones/M005/slices/S02/tasks/T02-SUMMARY.md
duration: 2 tasks
verification_result: passed
completed_at: 2026-03-14
---

# S02: Interview Overlay with JSON Protocol

**Bidirectional JSON protocol for `autoagent new --json` with TypeScript subprocess driver rendering interview phases as native pi TUI dialogs.**

## What Happened

Added `--json` flag to `autoagent new` (T01). When active, `builtins.print` redirects to stderr (same pattern as `cmd_run --jsonl`), and a `_build_json_orchestrator()` factory wires JSON I/O closures into `InterviewOrchestrator` without modifying the orchestrator class. The protocol is strict request-response: Python emits one JSON line (`prompt`, `confirm`, `status`, `complete`, or `error`), waits for one JSON line back (`answer` or `abort`). Vague-input detection and follow-up probes work through the same protocol. `cmd_new` was refactored into `cmd_new` (JSON setup/teardown) and `_cmd_new_inner` (shared logic) to keep the builtins.print restore in a finally block.

Created `interview-runner.ts` (T02) exporting `runInterview(projectDir, ui)` that spawns `autoagent --project-dir <dir> new --json` with `PYTHONUNBUFFERED=1`. Uses readline on stdout for line-buffered JSON parsing. Protocol dispatch: `prompt` → `ui.input()`, `confirm` → `ui.select("Yes"/"No")`, `status` → `ui.notify()`, `complete` → success. User cancellation (Escape) sends `{"type":"abort"}` and kills the process. Subprocess crash detected via readline close with stderr tail captured for diagnostics.

Extended `index.ts` with `case "new"` routing to `runInterview()`.

## Verification

- `pytest tests/test_cli_json_interview.py -v` — **17 tests pass** covering protocol round-trip, all 6 phases, vague follow-up, abort, EOF, stderr redirect, message format validation, overwrite skip
- `pytest tests/ -q` — **496 passed**, no regressions
- TypeScript structural check: `interview-runner.ts` exports `runInterview`, `index.ts` has `case "new"` with import, spawn + readline + stdin write logic confirmed

## Requirements Advanced

- R006 — `/autoagent new` wired as pi extension subcommand, interview runs through native TUI dialogs

## Requirements Validated

- none (R006 was already validated; R007 interview capability was validated in M004)

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

- Added `_json_emit` as module-level helper and extracted `_cmd_new_inner` — not in plan but needed for clean JSON setup/teardown separation
- `--project-dir` placed as top-level arg before `new --json` in spawn args — matches actual argparse structure where it's a parser-level argument

## Known Limitations

- Interview overlay not visually verified in a running pi instance — UAT will confirm TUI dialog rendering
- No timeout on individual interview phases — a hung Python subprocess would block the interview indefinitely

## Follow-ups

- none

## Files Created/Modified

- `src/autoagent/cli.py` — Added `--json` flag, `_json_emit` helper, refactored `cmd_new` into wrapper + `_cmd_new_inner`, added `_build_json_orchestrator` factory
- `tests/test_cli_json_interview.py` — New test file with 17 protocol tests
- `.pi/extensions/autoagent/interview-runner.ts` — New module with `runInterview()` bidirectional subprocess driver
- `.pi/extensions/autoagent/index.ts` — Added `runInterview` import, `case "new"` routing, updated description and help text

## Forward Intelligence

### What the next slice should know
- The interview runner is a standalone function returning `{success, error?}` — it's not wired into SubprocessManager and doesn't need to be
- `index.ts` now has `case "run"`, `case "new"`, and a default case listing available subcommands — S03 adds `case "report"`, `case "stop"`, `case "status"`
- The `--project-dir` flag is a parser-level argument in argparse, not a subcommand argument — spawn args must place it before the subcommand name

### What's fragile
- The JSON protocol relies on strict one-line-at-a-time stdout — any stray print() in `--json` mode that bypasses the stderr redirect would corrupt the protocol stream
- readline close detection depends on the Python process actually closing its stdout pipe — a zombie process would leave the interview hanging

### Authoritative diagnostics
- `autoagent new --json 2>/dev/null` piped to jq — shows exact protocol messages for debugging
- Subprocess stderr tail (last 20 lines) captured in error messages — first place to look on unexpected exit
- `pytest tests/test_cli_json_interview.py -v` — authoritative protocol contract tests

### What assumptions changed
- Plan assumed `--json --project-dir` as subcommand args — actual argparse requires `--project-dir` before the subcommand
