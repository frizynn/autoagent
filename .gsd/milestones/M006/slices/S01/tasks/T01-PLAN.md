# T01: Delete old framework + clean extension

**Slice:** S01
**Milestone:** M006

## Goal
Remove the entire Python optimization framework and strip the TUI extension down to `go` and `stop` commands only. The system prompt must enforce the autoresearch protocol — when there's no project, guide setup through conversation; when there is one, `/autoagent go` runs the loop.

## Must-Haves

### Truths
- `src/autoagent/` directory does not exist
- `tests/` directory does not exist
- `pyproject.toml` does not exist
- `uv.lock` does not exist
- `.pi/extensions/autoagent/` directory does not exist
- Extension index.ts registers only `go` and `stop` subcommands
- `/autoagent go` reads program.md and sends it to the agent via `pi.sendMessage()`
- `/autoagent stop` is wired (even if there's nothing to stop yet — placeholder for S03)
- system.md enforces the autoresearch protocol: no project → guide setup, project exists → show status
- program.md is the autoresearch loop protocol
- `tsc` builds the TUI without errors

### Artifacts
- `tui/src/resources/extensions/autoagent/index.ts` — extension entry point (go + stop commands, session_start with status, Ctrl+Alt+A shortcut placeholder)
- `tui/src/resources/extensions/autoagent/prompts/system.md` — system prompt enforcing autoresearch model
- `tui/src/resources/extensions/autoagent/prompts/program.md` — experiment loop protocol
- `tui/src/resources/extensions/autoagent/templates/pipeline.py` — baseline pipeline template (already exists)
- `tui/src/resources/extensions/autoagent/package.json` — extension manifest

### Key Links
- `index.ts` reads `prompts/program.md` via `readFileSync` and sends it via `pi.sendMessage()`
- `system.md` is injected via `pi.on("before_agent_start")` in index.ts
- `session_start` event in index.ts reads `.autoagent/` disk state and shows status

## Steps
1. Delete `src/autoagent/` directory entirely
2. Delete `tests/` directory entirely
3. Delete `pyproject.toml` and `uv.lock`
4. Delete `.pi/extensions/autoagent/` directory entirely (old pi extension, separate from tui extension)
5. Delete `tui/src/resources/extensions/autoagent/subprocess-manager.ts`
6. Delete `tui/src/resources/extensions/autoagent/interview-runner.ts`
7. Delete `tui/src/resources/extensions/autoagent/report-overlay.ts`
8. Delete `tui/src/resources/extensions/autoagent/dashboard-overlay.ts`
9. Delete `tui/src/resources/extensions/autoagent/types.ts`
10. Rewrite `tui/src/resources/extensions/autoagent/index.ts` — only `go` and `stop` subcommands, `session_start` with disk status, `before_agent_start` with system prompt injection, `Ctrl+Alt+A` as placeholder
11. Update `tui/src/resources/extensions/autoagent/prompts/system.md` — enforce autoresearch model. Key constraint: when no `.autoagent/` exists, the LLM MUST guide the user into creating prepare.py + pipeline.py through conversation before doing anything else. It must NOT act as a general coding assistant.
12. Review and update `tui/src/resources/extensions/autoagent/prompts/program.md` — ensure it has the simplicity criterion, results.tsv format, git branch protocol
13. Run `cd tui && npx tsc --noEmit` to verify build
14. Delete old `tests/fixtures/` directory if it still exists
15. Commit: `feat(M006/S01): delete old framework, wire go+stop`

## Context
- The old Python framework (502 tests, all mocks) never ran a real optimization — all of it goes
- The TUI shell (loader.ts, cli.ts, onboarding.ts, app-paths.ts) survives untouched
- The bug in the screenshot: when a user types a goal with no project, the LLM starts editing their codebase instead of guiding setup. system.md must fix this.
- program.md already exists and is close to correct — review for completeness
- pipeline.py template already exists — keep as-is
- D073-D078 in DECISIONS.md already capture the architectural rationale

## Observability Impact

- **Session start**: `session_start` event handler reads `.autoagent/` directory presence and `state.json` to display project status on launch. Future agents inspect this path to understand project state.
- **System prompt injection**: `before_agent_start` appends system.md to the agent's system prompt. If read fails, falls back to inline fallback string (logged via catch).
- **`go` command dispatch**: Sends program.md content via `pi.sendMessage()` with `customType: "autoagent-go"`. The agent's next turn reflects the dispatched content.
- **`stop` placeholder**: Shows "Nothing running" notification — visible in TUI. Will gain real behavior in S03.
- **Build signal**: `tsc --noEmit` pass/fail is the primary build health indicator for this extension.
