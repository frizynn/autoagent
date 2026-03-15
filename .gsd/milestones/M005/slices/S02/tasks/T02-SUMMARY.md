---
id: T02
parent: S02
milestone: M005
provides:
  - "runInterview() TypeScript function — subprocess driver for autoagent new --json"
  - "/autoagent new command wired into pi extension"
key_files:
  - .pi/extensions/autoagent/interview-runner.ts
  - .pi/extensions/autoagent/index.ts
key_decisions:
  - "Async line reader with bufferedLines/pendingWaiters pattern — cleaner than overriding push or using async iterators, handles strict request-response protocol and close-before-read edge case"
  - "Confirm response sent as {type:'answer', text:'Yes'/'No'} — matches Python json_input_fn which reads data.get('text') for both prompts and confirmations"
  - "--project-dir placed before subcommand in spawn args — matches argparse top-level argument position"
patterns_established:
  - "nextLine() async reader: bufferedLines array + pendingWaiters array, readline feeds one, close resolves all waiters with null"
  - "writeLine(obj) helper: JSON.stringify + newline to subprocess stdin, guarded by !stdin.destroyed"
  - "killProc() with SIGTERM + SIGKILL timeout fallback (same 5s pattern as SubprocessManager)"
observability_surfaces:
  - "ui.notify() surfaces phase transitions (status), completion (success), and errors (warning) as pi notifications"
  - "Subprocess stderr captured (last 20 lines) and included in error message on unexpected exit"
  - "runInterview() returns {success, error?} — callers get structured result for downstream handling"
duration: 1 task
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T02: TypeScript interview command and subprocess driver

**Created `interview-runner.ts` with `runInterview()` function that spawns `autoagent new --json` and drives the bidirectional JSON protocol via pi's native `ui.input()`/`ui.select()` dialogs. Wired as `/autoagent new` subcommand.**

## What Happened

Created `interview-runner.ts` exporting `runInterview(projectDir, ui)` that:

1. Spawns `autoagent --project-dir <dir> new --json` with `PYTHONUNBUFFERED=1` and full stdio pipes
2. Sets up readline on stdout for line-buffered JSON parsing (same pattern as SubprocessManager)
3. Captures stderr tail (last 20 lines) for diagnostics on unexpected exit
4. Implements protocol dispatch loop:
   - `prompt` → `ui.input()` dialog, Escape sends abort + kills process
   - `confirm` → `ui.select("Yes"/"No")`, Escape also aborts
   - `status` → `ui.notify()` info notification, no response
   - `complete` → success notification, returns `{success: true}`
   - `error` → returns `{success: false, error: msg.message}`
5. Handles readline close (subprocess exit without complete) with descriptive error + stderr context

Extended `index.ts` with `case "new"` routing to `runInterview(process.cwd(), ctx.ui)`, with failure notification on error.

## Verification

- ✅ `interview-runner.ts` exists with correct function signature and export
- ✅ `index.ts` has `case "new"` in subcommand switch with `runInterview` import
- ✅ Structural checks: readline setup, `PYTHONUNBUFFERED=1`, `JSON.stringify() + "\n"`, `--project-dir` arg order
- ✅ Manual protocol test: `autoagent new --json` produces JSON lines (status, prompt messages confirmed)
- ✅ `pytest tests/test_cli_json_interview.py -v` — 17 tests pass
- ✅ `pytest tests/ -q` — 496 passed, no regressions

### Slice-level verification status (T02 of 3):
- ✅ `pytest tests/test_cli_json_interview.py -v` — protocol tests pass (17/17)
- ✅ `pytest tests/ -q` — full suite passes (496 tests)
- ✅ TypeScript structural check — `new` case exists in index.ts, interview runner module has spawn + readline + stdin write logic

## Diagnostics

- `autoagent new --json` spawnable directly for protocol debugging — pipe answers via stdin, inspect JSON on stdout
- Subprocess crash surfaces as `{success: false, error: "Interview subprocess exited unexpectedly\n<stderr tail>"}` 
- User cancellation (Escape) sends `{"type":"abort"}` to stdin, kills process, notifies user
- Error messages from Python side propagated directly through `{success: false, error: msg.message}`

## Deviations

- `--project-dir` placed as top-level arg before `new --json` (plan had `new --json --project-dir`) — matches actual argparse structure where `--project-dir` is a parser-level argument, not subcommand-level

## Known Issues

None.

## Files Created/Modified

- `.pi/extensions/autoagent/interview-runner.ts` — New module with `runInterview()` function implementing full bidirectional JSON protocol driver
- `.pi/extensions/autoagent/index.ts` — Added `runInterview` import, `case "new"` subcommand routing, updated description and unknown-command help text
- `.gsd/milestones/M005/slices/S02/tasks/T02-PLAN.md` — Added missing Observability Impact section
