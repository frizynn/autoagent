# S01: Clean Slate + Loop Foundation

**Goal:** Delete the old Python framework entirely, keep only the TUI and autoresearch protocol files. Wire `/autoagent go` and `/autoagent stop` as the only commands. Prove the loop dispatches correctly.

**Demo:** Old framework gone (no src/, no tests/, no pyproject.toml, no .pi/extensions/). `/autoagent go` dispatches the LLM to follow program.md. Only `go` and `stop` as subcommands.

## Must-Haves
- No `src/autoagent/` directory exists
- No `tests/` directory exists
- No `pyproject.toml` exists
- No `.pi/extensions/` directory exists
- No `uv.lock` exists
- Extension index.ts only has `go` and `stop` subcommands (no `run`, `new`, `status`, `report`)
- `/autoagent go` sends program.md content to the agent via `pi.sendMessage()`
- `/autoagent stop` interrupts the loop
- system.md updated for the autoresearch model
- Extension builds cleanly (tsc)
- Old SubprocessManager, interview-runner, report-overlay deleted from extension

## Observability / Diagnostics

- **Session start banner**: `session_start` event reads `.autoagent/` disk state and displays status (project exists vs. no project). Observable in the TUI notification on launch.
- **System prompt injection**: `before_agent_start` appends system.md content. Verify by checking the LLM's behavior matches autoresearch protocol (no-project → guides setup, project → runs loop).
- **`/autoagent go` dispatch**: Sends program.md via `pi.sendMessage()`. Observable as the agent immediately beginning the experiment protocol.
- **`/autoagent stop` placeholder**: Wired but no-op until S03. Displays "Nothing running" notification.
- **Build health**: `tsc --noEmit` must pass with zero errors — captures type regressions.
- **Failure visibility**: If program.md is missing, `go` shows a warning notification. If system.md read fails, falls back to inline prompt.

## Verification

- `tsc --noEmit` passes with 0 errors
- `src/autoagent/`, `tests/`, `pyproject.toml`, `uv.lock`, `.pi/extensions/autoagent/` do not exist
- Extension only exports `go` and `stop` subcommands (grep for registered commands)
- system.md contains autoresearch protocol enforcement (no-project guard)
- program.md contains simplicity criterion and results.tsv format
- **Diagnostic check**: index.ts `session_start` handler reads `.autoagent/` and reports status — verify the code path exists

## Tasks

- [x] **T01: Delete old framework + clean extension**
  Delete src/autoagent/, tests/, pyproject.toml, uv.lock, .pi/extensions/. Strip extension to go+stop only. Delete SubprocessManager, interview-runner, report-overlay, dashboard-overlay (will be rewritten in S03). Update system.md and program.md. Verify build.

## Files Likely Touched
- `src/autoagent/` — DELETED
- `tests/` — DELETED  
- `pyproject.toml` — DELETED
- `uv.lock` — DELETED
- `.pi/extensions/autoagent/` — DELETED
- `tui/src/resources/extensions/autoagent/index.ts` — rewritten (go+stop only)
- `tui/src/resources/extensions/autoagent/prompts/system.md` — updated
- `tui/src/resources/extensions/autoagent/prompts/program.md` — updated
- `tui/src/resources/extensions/autoagent/subprocess-manager.ts` — DELETED
- `tui/src/resources/extensions/autoagent/interview-runner.ts` — DELETED
- `tui/src/resources/extensions/autoagent/report-overlay.ts` — DELETED
- `tui/src/resources/extensions/autoagent/dashboard-overlay.ts` — DELETED
- `tui/src/resources/extensions/autoagent/types.ts` — simplified or deleted
