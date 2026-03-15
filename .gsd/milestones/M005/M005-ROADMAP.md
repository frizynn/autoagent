# M005: Pi TUI Extension

**Vision:** AutoAgent becomes a first-class pi citizen — live dashboard, interview overlay, report viewer, all accessible from `/autoagent` and `Ctrl+Alt+A` without leaving the terminal.

## Success Criteria

- User types `/autoagent run` in pi and sees a live dashboard updating with iteration number, score, decision, cost, and elapsed time as the Python subprocess runs
- User types `/autoagent new` and completes the interview in a TUI overlay with native pi inputs, not raw terminal input()
- User types `/autoagent report` and reads the markdown report in a scrollable overlay
- User presses `Ctrl+Alt+A` at any time to toggle the dashboard overlay without affecting a running optimization
- A footer status widget shows optimization state (idle / running iteration N / paused)
- User can stop a running optimization from the TUI via `/autoagent stop`

## Key Risks / Unknowns

- **Subprocess streaming** — `pi.exec()` is one-shot only; live dashboard needs `child_process.spawn()` with line-buffered JSONL parsing. Python stdout buffering when piped could mean zero output until process exit.
- **Bidirectional subprocess protocol** — Interview requires request-response JSON protocol over stdin/stdout between Python and TypeScript. Interleaving, partial reads, and deadlocks are real risks.
- **Extension loading** — First project-local extension in this codebase. Need to confirm `.pi/extensions/autoagent/index.ts` is discovered and loaded by pi's jiti loader.

## Proof Strategy

- Subprocess streaming → retire in S01 by shipping a working live dashboard that renders real iteration data from a Python subprocess via spawn + JSONL
- Bidirectional protocol → retire in S02 by shipping the interview overlay completing a full 6-phase interview via JSON stdin/stdout
- Extension loading → retire in S01 by having the extension register commands and a shortcut on pi startup

## Verification Classes

- Contract verification: Python `--jsonl` / `--json` output validated by existing pytest suite + new protocol tests
- Integration verification: Extension loaded in pi, commands registered, overlays render with real subprocess data
- Operational verification: Dashboard updates while optimization runs in background; stop command kills subprocess gracefully
- UAT / human verification: Visual confirmation that dashboard layout, interview inputs, and report rendering look correct in the pi TUI

## Milestone Definition of Done

This milestone is complete only when all are true:

- All three slices complete with checkboxes checked
- Full flow exercised in pi: `/autoagent new` → interview overlay → `/autoagent run` → live dashboard → `/autoagent report` → report overlay
- Dashboard updates in real-time from live Python subprocess output
- `Ctrl+Alt+A` toggles dashboard without affecting running optimization
- `/autoagent stop` gracefully terminates a running optimization
- Footer widget reflects current optimization state
- Python test suite still passes (469+ tests)

## Requirement Coverage

- Covers: R006 (CLI extends into pi TUI), R019 (fire-and-forget with dashboard visibility), R017 (budget burn visible in real-time dashboard)
- Partially covers: none
- Leaves for later: R011, R012, R013, R024 (search intelligence — M002 scope), R018 (provider-agnostic — active but orthogonal), R009, R014 (validated, not touched)
- Orphan risks: none — all active requirements either covered or explicitly orthogonal to this UX milestone

## Slices

- [x] **S01: Live Dashboard with Streaming Subprocess** `risk:high` `depends:[]`
  > After this: user runs `/autoagent run` in pi and sees a live dashboard overlay showing iteration progress, scores, decisions, cost, and elapsed time — all rendering from real Python subprocess JSONL output via spawn
- [ ] **S02: Interview Overlay with JSON Protocol** `risk:medium` `depends:[S01]`
  > After this: user runs `/autoagent new` in pi and completes the full 6-phase interview in a TUI overlay with native pi input/select dialogs, driven by bidirectional JSON protocol to the Python subprocess
- [ ] **S03: Report, Status, Stop, and Final Assembly** `risk:low` `depends:[S01]`
  > After this: user has the complete `/autoagent` experience — report overlay, status check, stop command, `Ctrl+Alt+A` shortcut, footer widget — all wired together and exercised end-to-end in pi

## Boundary Map

### S01 → S02

Produces:
- Extension scaffold at `.pi/extensions/autoagent/index.ts` with `registerCommand("autoagent")` and subcommand dispatch
- `SubprocessManager` module handling spawn, JSONL line parsing, process lifecycle (start/stop/status)
- Python `--jsonl` output mode in `cmd_run` emitting structured iteration events to stdout
- Dashboard overlay component following GSD `dashboard-overlay.ts` pattern (render/handleInput/scroll)
- `Ctrl+Alt+A` keyboard shortcut registration toggling dashboard
- Footer status widget via `ui.setStatus()`

Consumes:
- nothing (first slice)

### S01 → S03

Produces:
- Same as S01 → S02: extension scaffold, subprocess manager, command registration infrastructure
- Established pattern for overlay components (render width, handleInput, scroll, dispose)

Consumes:
- nothing (first slice)

### S02 → S03

Produces:
- Python `--json` interactive mode for interview with request-response protocol
- Interview overlay component demonstrating bidirectional subprocess communication
- Proven pattern for multi-step TUI flows (phase progression, input collection, completion)

Consumes:
- Extension scaffold and command routing from S01
