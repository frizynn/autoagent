# M005: Pi TUI Extension — Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

## Project Description

AutoAgent has a complete Python CLI (M001–M004) but zero real-time visibility. You run `autoagent run` and stare at a blank terminal. The pi TUI framework provides exactly what's needed: overlays, components, keyboard shortcuts, widgets, and an extension API that can host AutoAgent's UX natively inside pi — where the user already lives.

## Why This Milestone

M004 completed the user experience in terms of capabilities — interview, benchmark generation, optimization loop, reporting. But the *interaction model* is wrong. You launch a Python subprocess and wait. You can't see iterations happening. You can't interrupt mid-loop to adjust constraints. You can't glance at a dashboard while doing other work in pi. The pi extension model fixes all of this: AutoAgent becomes a first-class citizen in the tool the user is already running.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Type `/autoagent` in pi and get a contextual wizard (like `/gsd`) that routes to new, run, status, or report
- Run `/autoagent new` and complete the interview in a TUI overlay with rich input, not raw `input()` calls
- Run `/autoagent run` and see a live dashboard showing iteration number, current score, best score, keep/discard decisions, budget burn, and elapsed time — updated in real-time as the Python subprocess produces output
- Press `Ctrl+Alt+A` at any time to toggle the AutoAgent dashboard overlay showing optimization status
- See a compact status line in pi's footer showing current optimization state (idle, running iteration 7/∞, paused)
- Run `/autoagent report` and see the rendered markdown report in a scrollable overlay
- Press `Ctrl+C` during a run to gracefully stop the optimization loop

### Entry point / environment

- Entry point: `/autoagent` slash command in pi, `Ctrl+Alt+A` keyboard shortcut
- Environment: pi terminal (interactive mode)
- Live dependencies involved: Python `autoagent` CLI via subprocess, `.autoagent/` directory on disk

## Completion Class

- Contract complete means: extension loads in pi, commands register, overlays render, subprocess management works
- Integration complete means: `/autoagent new` → interview → config on disk; `/autoagent run` → live dashboard with real iteration data; `/autoagent report` → rendered report
- Operational complete means: user can run optimization in background while using pi for other work, dashboard toggles without interruption

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- Full flow in pi: `/autoagent new` → interview in overlay → `/autoagent run` → live dashboard → `/autoagent report` → report overlay
- Dashboard updates in real-time as Python subprocess produces iteration output
- User can toggle dashboard with `Ctrl+Alt+A` while optimization runs, without affecting the loop
- Graceful interrupt: user can stop a running optimization from the TUI

## Risks and Unknowns

- **Subprocess output parsing** — The Python CLI writes to stdout/stderr. The extension needs to parse this into structured data for the dashboard. Need to define a machine-readable output format (JSON lines?) or parse the existing human-readable output.
- **Extension loading/development** — pi loads extensions from `.pi/extensions/` using jiti (TypeScript JIT). Development workflow for a project-local extension needs to be established.
- **Streaming subprocess updates** — `pi.exec()` returns when the process exits. For live loop monitoring, we need `spawn()` with streaming stdout. The extension API provides `exec()` but not streaming — we'll need raw `child_process.spawn()`.
- **Interview in TUI** — The Python interview uses `input()/print()`. The TUI version either wraps the Python subprocess with PTY forwarding or reimplements the interview flow in TypeScript using the LLM directly. PTY is simpler but less native; reimplementation is more work but gives a better UX.
- **State synchronization** — The extension reads `.autoagent/` state from disk (same as the Python CLI). Need to handle file watching or polling to keep the dashboard in sync.

## Existing Codebase / Prior Art

- `src/autoagent/cli.py` — Python CLI with cmd_new, cmd_run, cmd_report handlers
- `.gsd/agent/extensions/gsd/` — GSD extension: command registration, dashboard overlay, auto-mode dispatch. The authoritative pattern for how pi extensions work.
- `.gsd/agent/extensions/gsd/dashboard-overlay.ts` — GSD dashboard: overlay component with scrolling, sections, real-time refresh. Model for AutoAgent's dashboard.
- `.gsd/agent/extensions/gsd/commands.ts` — Command registration with subcommand routing and autocomplete.
- `@gsd/pi-tui` — TUI primitives: Box, Text, Input, Loader, Markdown, SelectList, Container, TUI, overlays.
- `@gsd/pi-coding-agent` — Extension API: registerCommand, registerShortcut, registerTool, ui.custom, ui.setWidget, ui.setStatus, exec.

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions — it is an append-only register; read it during planning, append to it during execution.

## Relevant Requirements

- R006 — CLI: extending from Python argparse to pi TUI (supporting)
- R019 — Fire-and-forget: dashboard gives visibility without requiring attention (supporting)
- R017 — Budget: dashboard shows budget burn in real-time (supporting)

## Scope

### In Scope

- Pi extension scaffolding in `.pi/extensions/autoagent/`
- `/autoagent` command with subcommand routing (new, run, report, status, stop)
- `/autoagent new` — interview flow in TUI (wrapping Python subprocess or reimplementing)
- `/autoagent run` — live dashboard overlay with streaming subprocess output
- `/autoagent report` — markdown report rendered in scrollable overlay
- `/autoagent status` — quick status check
- `/autoagent stop` — graceful interrupt of running optimization
- `Ctrl+Alt+A` keyboard shortcut to toggle dashboard overlay
- Footer widget showing optimization status
- Structured output format from Python CLI for machine-readable parsing

### Out of Scope / Non-Goals

- Modifying AutoAgent's Python core (the optimization engine stays unchanged)
- Web UI or browser-based dashboard
- Multi-project support (one AutoAgent project per pi session)
- Real LLM provider wiring (still uses MockLLM — real provider integration is a separate concern)

## Technical Constraints

- Extension must be TypeScript, loaded by pi's jiti-based extension loader
- Extension lives in `.pi/extensions/autoagent/` (project-local) with `index.ts` entry point
- Can import from `@gsd/pi-tui`, `@gsd/pi-coding-agent`, `@gsd/pi-agent-core`, `@sinclair/typebox`
- Python `autoagent` CLI must be available in PATH (installed in venv)
- Subprocess communication via stdout/stderr + disk state (`.autoagent/` directory)

## Integration Points

- **Python autoagent CLI** — subprocess execution for new, run, report commands
- **`.autoagent/` directory** — disk state: config.json, archive/, pipeline.py, report.md
- **pi TUI** — overlays, widgets, components, keyboard shortcuts
- **pi extension API** — command registration, UI context, exec

## Open Questions

- **Interview approach** — PTY forwarding (simpler, wraps Python input()) vs TypeScript reimplementation (better UX, more work)? Leaning toward structured JSON protocol: Python CLI gets a `--json` mode that outputs structured interview steps, TypeScript extension renders them as TUI and sends answers back via stdin.
- **Live output format** — JSON lines from Python subprocess, or parse human-readable output? JSON lines is cleaner but requires modifying the Python CLI to support `--json-output`. Could add a thin JSON output layer without touching core logic.
- **Dashboard refresh** — File watching (fs.watch on `.autoagent/archive/`) vs subprocess stdout streaming? Subprocess streaming is more immediate; file watching is more decoupled. Could use both: stream stdout for live updates, file watch for recovery after restart.
