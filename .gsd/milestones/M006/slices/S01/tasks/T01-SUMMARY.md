---
id: T01
parent: S01
milestone: M006
provides:
  - Clean codebase with no Python framework artifacts
  - Extension with only go+stop subcommands
  - system.md enforcing autoresearch protocol (no-project guard)
  - program.md with simplicity criterion, results.tsv format, git branch protocol
key_files:
  - tui/src/resources/extensions/autoagent/index.ts
  - tui/src/resources/extensions/autoagent/prompts/system.md
  - tui/src/resources/extensions/autoagent/prompts/program.md
key_decisions:
  - system.md uses two explicit modes (MODE A / MODE B) keyed on .autoagent/ existence
  - go command prefers local .autoagent/program.md over bundled prompts/program.md
  - stop is a no-op placeholder that notifies "Nothing running" until S03 wires real interrupt
patterns_established:
  - Extension reads prompts from filesystem via readFileSync at command time, not at import time
  - session_start inspects .autoagent/ disk state for project health (pipeline.py, prepare.py, results.tsv)
observability_surfaces:
  - session_start banner shows project status (no project / incomplete / ready + experiment count)
  - before_agent_start injects system.md into agent system prompt with fallback on read failure
  - go command dispatches via pi.sendMessage with customType "autoagent-go"
  - stop command shows "Nothing running" notification (placeholder)
duration: 15min
verification_result: passed
completed_at: 2026-03-15
blocker_discovered: false
---

# T01: Delete old framework + clean extension

**Deleted entire Python framework and stripped extension to go+stop only with autoresearch protocol enforcement.**

## What Happened

Removed all old Python framework code (src/autoagent/, tests/, pyproject.toml, uv.lock) and the old .pi/extensions/autoagent/ directory. Deleted 5 extension modules that are no longer needed (subprocess-manager.ts, interview-runner.ts, report-overlay.ts, dashboard-overlay.ts, types.ts).

Rewrote index.ts to register only `go` and `stop` subcommands. `go` reads program.md (local .autoagent/ first, bundled fallback) and dispatches it to the agent via `pi.sendMessage()`. `stop` is a placeholder that shows a notification. `session_start` reads .autoagent/ disk state and reports project health. `before_agent_start` injects system.md into the agent's system prompt.

Updated system.md with two explicit modes: MODE A (no project → guide setup, refuse unrelated requests) and MODE B (project exists → show status, wait for /autoagent go). Added the critical constraint that the LLM must NOT act as a general coding assistant when no project exists.

Updated program.md with an explicit Simplicity Criterion section, branch collision handling (append counter), and confirmed results.tsv format and git branch protocol were already correct.

## Verification

- `tsc --noEmit` — PASS (zero errors)
- src/autoagent/, tests/, pyproject.toml, uv.lock, .pi/extensions/autoagent/ — all confirmed absent
- subprocess-manager.ts, interview-runner.ts, report-overlay.ts, dashboard-overlay.ts, types.ts — all confirmed absent
- index.ts has exactly 2 case statements: "go" and "stop"
- index.ts session_start reads .autoagent/ via existsSync
- system.md contains "NOT a general coding assistant" guard
- program.md contains Simplicity Criterion, results.tsv format, git branch protocol

## Diagnostics

- **Session start**: On TUI launch, the session_start handler reads .autoagent/ and shows one of: "No project", "Project incomplete — missing X", "Project ready · N experiments logged", or "Project ready · no experiments yet"
- **System prompt**: Injected via before_agent_start. If system.md read fails, falls back to inline string.
- **Go dispatch**: Sends program.md content via pi.sendMessage() with customType "autoagent-go". Observable as the agent's next turn following the experiment protocol.
- **Stop placeholder**: Shows "Nothing running to stop." notification.

## Deviations

- src/ directory was left as an empty shell after deleting src/autoagent/ — cleaned up the empty src/ too
- .pi/extensions/autoagent/ was already absent (no-op deletion)

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/` — DELETED (entire Python framework)
- `tests/` — DELETED (502 mock-only tests)
- `pyproject.toml` — DELETED
- `uv.lock` — DELETED
- `tui/src/resources/extensions/autoagent/subprocess-manager.ts` — DELETED
- `tui/src/resources/extensions/autoagent/interview-runner.ts` — DELETED
- `tui/src/resources/extensions/autoagent/report-overlay.ts` — DELETED
- `tui/src/resources/extensions/autoagent/dashboard-overlay.ts` — DELETED
- `tui/src/resources/extensions/autoagent/types.ts` — DELETED
- `tui/src/resources/extensions/autoagent/index.ts` — rewritten (go+stop only, session_start, before_agent_start, Ctrl+Alt+A placeholder)
- `tui/src/resources/extensions/autoagent/prompts/system.md` — rewritten (MODE A/B autoresearch protocol)
- `tui/src/resources/extensions/autoagent/prompts/program.md` — updated (simplicity criterion, branch collision handling)
- `.gsd/milestones/M006/slices/S01/S01-PLAN.md` — added Observability/Diagnostics and Verification sections
- `.gsd/milestones/M006/slices/S01/tasks/T01-PLAN.md` — added Observability Impact section
