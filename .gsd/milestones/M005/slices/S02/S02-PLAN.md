# S02: Interview Overlay with JSON Protocol

**Goal:** User runs `/autoagent new` in pi and completes the full 6-phase interview in a TUI overlay with native pi input/select dialogs, driven by bidirectional JSON protocol to the Python subprocess.
**Demo:** `/autoagent new` spawns `autoagent new --json`, each phase appears as a `ctx.ui.input()` dialog, vague answers trigger follow-up probes, completion writes config + context to disk, user sees success notification.

## Must-Haves

- Python `autoagent new --json` emits JSON prompts to stdout, reads JSON answers from stdin
- Strict request-response protocol: one JSON line out, one JSON line in, no interleaving
- All 6 phases + confirmation work through the protocol (vague-input detection and follow-up probes included)
- `builtins.print` redirected to stderr in `--json` mode (same pattern as `--jsonl` in D065)
- TypeScript `/autoagent new` subcommand spawns subprocess and drives interview via `ctx.ui.input()`/`ctx.ui.select()`
- User cancellation (Escape on any `ctx.ui.input()`) sends abort and kills subprocess gracefully
- Subprocess crash mid-interview detected and reported to user
- Config + context written to disk on completion (same paths as regular `cmd_new`)

## Proof Level

- This slice proves: contract + integration (Python protocol contract via pytest; TypeScript wiring is structural)
- Real runtime required: yes (Python subprocess tests)
- Human/UAT required: yes (visual confirmation of TUI dialogs deferred to UAT)

## Verification

- `pytest tests/test_cli_json_interview.py -v` — protocol tests: JSON prompt emission, answer reading, vague follow-up cycle, confirmation phase, completion event, cancellation handling, stderr redirect, subprocess error
- `pytest tests/ -q` — full suite passes (479+ tests, no regressions)
- TypeScript structural check: `new` case exists in index.ts switch, interview runner module exists with spawn + readline + stdin write logic

## Observability / Diagnostics

- Runtime signals: JSON protocol messages on stdout (machine-parseable interview telemetry)
- Inspection surfaces: `autoagent new --json` runnable directly from terminal for protocol debugging (`echo '{"type":"answer","text":"test"}' | autoagent new --json 2>/dev/null`)
- Failure visibility: subprocess exit with non-zero code + stderr captured; protocol error events include phase and error message
- Redaction constraints: none (interview answers are not secrets)

## Integration Closure

- Upstream surfaces consumed: extension scaffold and command routing from S01 (`index.ts` switch), `PYTHONUNBUFFERED=1` pattern (D068)
- New wiring introduced: `new` subcommand case in `index.ts`, `interview-runner.ts` module for bidirectional subprocess I/O
- What remains before milestone is truly usable end-to-end: S03 (report overlay, stop wiring, final assembly)

## Tasks

- [x] **T01: Python `--json` interview protocol** `est:35m`
  - Why: Establishes the bidirectional JSON contract that the TypeScript side will consume — protocol must exist and be tested before wiring the TUI
  - Files: `src/autoagent/cli.py`, `src/autoagent/interview.py`, `tests/test_cli_json_interview.py`
  - Do: Add `--json` flag to `cmd_new`. Create JSON-wrapping `input_fn` and `print_fn` that emit `{"type":"prompt","phase":"...","question":"..."}` to stdout and read `{"type":"answer","text":"..."}` from stdin. Emit `{"type":"confirm","summary":"..."}` for confirmation phase, read `{"type":"answer","text":"yes/no"}`. Emit `{"type":"complete","config":{...},"context":"..."}` at end. Redirect `builtins.print` to stderr. Handle `EOFError` on stdin as abort. Skip overwrite confirmation in `--json` mode (TUI side handles it). Emit benchmark generation status as `{"type":"status","message":"..."}`.
  - Verify: `pytest tests/test_cli_json_interview.py -v` — all tests pass; `pytest tests/ -q` — no regressions
  - Done when: `autoagent new --json` completes a full interview round-trip with JSON on stdio, tested with ≥8 test cases covering happy path, vague input, cancellation, and error handling

- [x] **T02: TypeScript interview command and subprocess driver** `est:35m`
  - Why: Wires the JSON protocol into pi's TUI — the user-facing half of the interview experience
  - Files: `.pi/extensions/autoagent/interview-runner.ts`, `.pi/extensions/autoagent/index.ts`
  - Do: Create `interview-runner.ts` with `runInterview(projectDir: string, ui: ExtensionCommandContext["ui"]): Promise<{success: boolean, error?: string}>`. Spawns `autoagent new --json` with `PYTHONUNBUFFERED=1` and `stdio: ["pipe", "pipe", "pipe"]`. Uses readline on stdout. For each `prompt` message, calls `ctx.ui.input(question, placeholder)` — if user returns undefined (Escape), writes `{"type":"abort"}` to stdin and kills process. For `confirm` messages, calls `ctx.ui.select()` with Yes/No. For `status` messages, calls `ctx.ui.notify()`. On `complete`, notifies success. Handle readline `close` event as subprocess crash. Add `new` case to index.ts command switch that calls `runInterview()`.
  - Verify: Extension file structure check: `interview-runner.ts` exports `runInterview`, `index.ts` has `case "new"` routing to it. Manual protocol test: run `autoagent new --json` and pipe JSON answers to verify round-trip.
  - Done when: `/autoagent new` case wired in index.ts, interview-runner.ts implements full protocol driver with input collection, cancellation, and error handling

## Files Likely Touched

- `src/autoagent/cli.py`
- `src/autoagent/interview.py`
- `tests/test_cli_json_interview.py`
- `.pi/extensions/autoagent/interview-runner.ts`
- `.pi/extensions/autoagent/index.ts`
