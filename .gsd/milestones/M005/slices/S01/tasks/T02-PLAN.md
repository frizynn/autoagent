---
estimated_steps: 5
estimated_files: 5
---

# T02: Pi extension with SubprocessManager, dashboard overlay, and controls

**Slice:** S01 — Live Dashboard with Streaming Subprocess
**Milestone:** M005

## Description

Build the pi extension that spawns the Python subprocess, parses JSONL events, renders a live dashboard overlay, and provides user controls. This is the user-facing integration — `/autoagent run` starts the optimization, the dashboard streams results, `Ctrl+Alt+A` toggles visibility, `/autoagent stop` kills the subprocess, and the footer always shows current state.

## Steps

1. Create `.pi/extensions/autoagent/package.json` with name, version, and peerDependencies on `@gsd/pi-coding-agent` and `@gsd/pi-tui`. Create `types.ts` defining TypeScript interfaces for each JSONL event type (LoopStartEvent, IterationStartEvent, IterationEndEvent, LoopEndEvent, ErrorEvent) matching the Python schema from T01, plus a union AutoagentEvent type and SubprocessState enum (idle, running, completed, error, stopped).
2. Create `subprocess-manager.ts`: a singleton-pattern class that manages the Python child process. Key methods: `start(projectDir, args)` spawns `autoagent run --jsonl` via `child_process.spawn` with env `PYTHONUNBUFFERED=1` (D068), reads stdout via readline interface parsing JSON per line, stores events in a bounded buffer (last 200), exposes `stop()` sending SIGTERM then SIGKILL after 5s timeout, `status()` returning SubprocessState, `getEvents()` returning buffered events, `onEvent(callback)` for live subscribers. Track PID, exit code, last error. Handle spawn errors and unexpected exit gracefully.
3. Create `dashboard-overlay.ts` following GSD's `dashboard-overlay.ts` pattern: Component with render(width)/handleInput(data)/invalidate()/dispose(). Constructor subscribes to SubprocessManager events. Render: header with "AutoAgent Dashboard" + state badge + elapsed time, iteration table with columns (#, Score, Decision, Cost, Elapsed, Rationale), scroll support (↑↓/j/k/g/G), footer hint line. Auto-refresh via setInterval(1000) reading new events. Close with Esc/Ctrl+C/Ctrl+Alt+A. Box border using theme colors.
4. Create `index.ts`: default export function receiving ExtensionAPI. Register `/autoagent` command with subcommand parsing: `run [--budget N]` calls SubprocessManager.start(), opens dashboard overlay via `ctx.ui.custom()` with overlay options; `stop` calls SubprocessManager.stop(); `status` shows one-line state summary via ctx.ui.notify(). Register `Ctrl+Alt+A` shortcut (Key.ctrlAlt("a")) toggling dashboard overlay — if subprocess running, open overlay attached to it; if idle, notify "no optimization running". Set footer status via `ctx.ui.setStatus("autoagent", text)` — update on every SubprocessManager state change (idle: nothing, running: "⚡ iteration N", completed: "✓ done (N iterations)", error: "✗ error"). Ensure overlay close does NOT call SubprocessManager.stop() (D067).
5. Manual verification: start pi in the autoagent project directory, confirm `/autoagent` command appears, run `/autoagent run`, verify dashboard overlay renders with streaming events, toggle with Ctrl+Alt+A, stop with `/autoagent stop`, confirm footer updates throughout.

## Must-Haves

- [ ] Extension discovered and loaded by pi from `.pi/extensions/autoagent/index.ts`
- [ ] `/autoagent run` spawns subprocess with PYTHONUNBUFFERED=1 and opens dashboard
- [ ] SubprocessManager parses JSONL lines into typed events
- [ ] Dashboard overlay renders iteration table with live updates
- [ ] `Ctrl+Alt+A` toggles dashboard overlay without affecting subprocess
- [ ] `/autoagent stop` sends SIGTERM to subprocess, updates footer
- [ ] Footer status widget reflects subprocess state (idle/running/completed/error)
- [ ] Closing overlay does not kill subprocess (D067)

## Verification

- Extension loads without errors in pi (no console errors on startup)
- `/autoagent` command appears in command list
- `/autoagent run` spawns Python subprocess (visible via `ps aux | grep autoagent`)
- Dashboard overlay shows iteration events as they arrive
- `Ctrl+Alt+A` opens/closes overlay while subprocess continues
- `/autoagent stop` terminates subprocess (PID no longer exists)
- Footer shows state transitions: idle → running → completed/stopped

## Observability Impact

- Signals added: Footer status widget showing subprocess state; dashboard overlay with iteration history
- How a future agent inspects this: `/autoagent status` prints one-line state; SubprocessManager.status() returns structured state
- Failure state exposed: SubprocessManager stores last error message, exit code, stderr tail; dashboard renders error events inline

## Inputs

- `src/autoagent/cli.py` — T01's `--jsonl` flag and JSONL event format
- `~/.gsd/agent/extensions/gsd/dashboard-overlay.ts` — pattern reference for overlay component
- `~/.gsd/agent/extensions/gsd/index.ts` — pattern reference for command/shortcut registration

## Expected Output

- `.pi/extensions/autoagent/package.json` — extension package manifest
- `.pi/extensions/autoagent/types.ts` — JSONL event TypeScript interfaces
- `.pi/extensions/autoagent/subprocess-manager.ts` — Python subprocess lifecycle manager
- `.pi/extensions/autoagent/dashboard-overlay.ts` — live dashboard overlay component
- `.pi/extensions/autoagent/index.ts` — extension entry point with commands, shortcuts, footer
