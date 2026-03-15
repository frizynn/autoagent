---
estimated_steps: 5
estimated_files: 2
---

# T02: TypeScript interview command and subprocess driver

**Slice:** S02 — Interview Overlay with JSON Protocol
**Milestone:** M005

## Description

Create `interview-runner.ts` — a function that spawns `autoagent new --json`, drives the bidirectional protocol using `ctx.ui.input()` and `ctx.ui.select()`, and handles cancellation and subprocess errors. Wire it into `index.ts` as the `new` subcommand of `/autoagent`.

This is NOT a custom overlay. The interview is sequential input collection — each phase appears as a native pi input dialog. Progress between phases shown via `ctx.ui.notify()`. This matches the GSD preferences wizard pattern (sequential `ctx.ui.input()` / `ctx.ui.select()` calls).

## Steps

1. Create `.pi/extensions/autoagent/interview-runner.ts` exporting `async function runInterview(projectDir: string, ui: ExtensionCommandContext["ui"]): Promise<{success: boolean, error?: string}>`
2. Spawn `autoagent new --json --project-dir <dir>` with `{ stdio: ["pipe", "pipe", "pipe"], env: { ...process.env, PYTHONUNBUFFERED: "1" } }`. Set up readline on stdout for line-buffered JSON parsing (same pattern as SubprocessManager).
3. Implement the protocol loop: read JSON line from stdout → dispatch on `type`:
   - `prompt`: call `await ui.input(msg.question, "")`. If result is `undefined` (Escape), write `{"type":"abort"}\n` to stdin and kill process. Otherwise write `{"type":"answer","text":"..."}\n` to stdin.
   - `confirm`: call `await ui.select(msg.summary, ["Yes", "No"])`. Write answer back.
   - `status`: call `ui.notify(msg.message, "info")`. No response needed — continue reading.
   - `complete`: call `ui.notify("Interview complete! Config saved.", "success")`. Return `{success: true}`.
   - `error`: return `{success: false, error: msg.message}`.
4. Handle readline `close` event (subprocess exit without `complete`): if interview not done, return `{success: false, error: "Interview subprocess exited unexpectedly"}`. Capture stderr tail for diagnostics.
5. Add `case "new"` to `index.ts` command switch: call `runInterview(process.cwd(), ctx.ui)`, on failure notify with error message.

## Must-Haves

- [ ] `interview-runner.ts` exports `runInterview` function
- [ ] Spawns `autoagent new --json` with `PYTHONUNBUFFERED=1` and bidirectional stdio
- [ ] Each `prompt` message renders as `ctx.ui.input()` dialog
- [ ] Confirmation renders as `ctx.ui.select()` with Yes/No
- [ ] Status messages shown via `ctx.ui.notify()`
- [ ] User pressing Escape sends abort and kills subprocess
- [ ] Subprocess crash detected and reported via error notification
- [ ] `index.ts` routes `/autoagent new` to `runInterview()`

## Verification

- `interview-runner.ts` exists with correct function signature and export
- `index.ts` has `case "new"` in the subcommand switch
- Code review: readline setup matches SubprocessManager pattern, `PYTHONUNBUFFERED=1` set, stdin.write uses `JSON.stringify() + "\n"`
- Manual protocol test: `autoagent new --json` is spawnable and produces JSON lines (T01 contract)

## Inputs

- T01 output — Python `--json` protocol contract (message types, format, behavior)
- `.pi/extensions/autoagent/index.ts` — existing command switch to extend
- `.pi/extensions/autoagent/subprocess-manager.ts` — readline + JSONL parsing pattern reference (NOT reused directly — interview is a separate function, not the singleton manager)
- GSD preferences wizard pattern (`~/.gsd/agent/extensions/gsd/commands.ts` lines 310-405) — sequential `ctx.ui.input()` / `ctx.ui.select()` reference

## Observability Impact

- **Interview subprocess lifecycle** visible via `ui.notify()` — status messages surface phase transitions, completion, and errors as pi notifications
- **Subprocess crash detection**: unexpected readline close triggers error notification with stderr tail context (last lines from Python process)
- **Abort flow**: user pressing Escape sends `{"type":"abort"}` to subprocess stdin, kills process, and notifies — full cancellation path is observable
- **Protocol debugging**: the same `autoagent new --json` subprocess can be run manually in a terminal to inspect raw JSON protocol messages independent of the TypeScript driver
- **Failure state**: `runInterview()` returns `{success: false, error: "..."}` with descriptive message — callers can surface or log the error

## Expected Output

- `.pi/extensions/autoagent/interview-runner.ts` — new module with `runInterview()` function implementing full protocol driver
- `.pi/extensions/autoagent/index.ts` — extended with `case "new"` routing to `runInterview()`
