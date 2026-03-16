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

## Tasks

- [ ] **T01: Delete old framework + clean extension**
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
