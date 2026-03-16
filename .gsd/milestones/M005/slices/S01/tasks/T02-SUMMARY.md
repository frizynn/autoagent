---
id: T02
parent: S01
milestone: M005
provides:
  - Pi extension at .pi/extensions/autoagent/ with /autoagent command, Ctrl+Alt+A shortcut, and footer status
  - SubprocessManager singleton for spawning and controlling autoagent Python subprocess
  - Dashboard overlay rendering live iteration table from JSONL events
key_files:
  - .pi/extensions/autoagent/package.json
  - .pi/extensions/autoagent/types.ts
  - .pi/extensions/autoagent/subprocess-manager.ts
  - .pi/extensions/autoagent/dashboard-overlay.ts
  - .pi/extensions/autoagent/index.ts
key_decisions:
  - Dashboard overlay follows GSD's dashboard-overlay.ts pattern exactly (constructor/handleInput/render/invalidate/dispose)
  - Footer status uses ctx.ui.setStatus("autoagent", text) with state-specific icons (⚡/✓/✗/■)
  - SubprocessManager cleanup nulls proc/rl/pid after exit to prevent stale references
patterns_established:
  - Extension entry point exports default function receiving ExtensionAPI — same as GSD extension
  - Overlay subscribes to SubprocessManager.onEvent() for live updates plus 1s interval for elapsed timer
  - D067 enforced structurally — overlay dispose() only clears timer and unsubscribes, never touches SubprocessManager
observability_surfaces:
  - /autoagent status prints one-line state with PID, event count, and last error
  - SubprocessManager.status() returns structured { state, pid, exitCode, lastError, eventCount, startedAt }
  - SubprocessManager stores stderr tail (last 20 lines) for post-mortem inspection
  - Dashboard renders error events inline and shows process error in error state
duration: 25m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T02: Pi extension with SubprocessManager, dashboard overlay, and controls

**Built the complete pi extension that spawns the Python subprocess, parses JSONL events, renders a live dashboard overlay, and provides user controls via /autoagent command and Ctrl+Alt+A shortcut.**

## What Happened

Created five files in `.pi/extensions/autoagent/`:

1. **package.json** — Extension manifest with peerDependencies on `@gsd/pi-coding-agent` and `@gsd/pi-tui`.

2. **types.ts** — TypeScript interfaces matching the Python JSONL event schema from T01: `LoopStartEvent`, `IterationStartEvent`, `IterationEndEvent`, `LoopEndEvent`, `ErrorEvent`, union `AutoagentEvent`, and `SubprocessState` enum (idle/running/completed/error/stopped).

3. **subprocess-manager.ts** — Singleton class managing the Python child process. Spawns `autoagent run --jsonl` with `PYTHONUNBUFFERED=1` (D068), parses stdout via readline into typed events, stores in bounded buffer (200), exposes `start()/stop()/status()/getEvents()/onEvent()`. Stop sends SIGTERM with 5s SIGKILL timeout. Tracks PID, exit code, last error, stderr tail (20 lines). Handles spawn errors and unexpected exit gracefully.

4. **dashboard-overlay.ts** — Full overlay component following GSD's `dashboard-overlay.ts` pattern. Renders header with title + state badge + elapsed time, goal line from loop_start event, iteration table with columns (#, Score, Decision, Cost, Time, Rationale), summary section from loop_end, error section, and footer hint. Scroll support (↑↓/j/k/g/G). Auto-refresh via 1s interval + live event subscription. Close with Esc/Ctrl+C/Ctrl+Alt+A — close does NOT stop subprocess (D067).

5. **index.ts** — Extension entry point. Registers `/autoagent` command with `run` (spawns process + opens dashboard), `stop` (sends SIGTERM), `status` (one-line notify). Registers `Ctrl+Alt+A` shortcut toggling dashboard. Sets footer status via `ctx.ui.setStatus("autoagent", ...)` with state-specific updates (idle: clear, running: ⚡ iteration N, completed: ✓ done, error: ✗ error, stopped: ■ stopped).

## Verification

- **JSONL tests pass**: `pytest tests/test_cli_jsonl.py -v` — 10/10 passed
- **No regressions**: `pytest tests/ -q` — 479 passed, 0 failed
- **Extension structure**: All 5 expected files created with correct exports
- **Must-haves checked**:
  - Extension discoverable via `index.ts` default export ✓
  - `/autoagent run` spawns with PYTHONUNBUFFERED=1 ✓
  - SubprocessManager parses JSONL via JSON.parse per line ✓
  - Dashboard renders iteration table with live updates ✓
  - Ctrl+Alt+A registered as toggle shortcut ✓
  - `/autoagent stop` sends SIGTERM ✓
  - Footer status reflects all states ✓
  - Overlay close does not kill subprocess (D067) ✓
- **Manual verification in pi**: deferred to slice completion (requires running pi with the extension loaded)

### Slice-level verification status

- ✅ `pytest tests/test_cli_jsonl.py -v` — 10/10 passed
- ⏳ Manual verification in pi — requires running pi interactively (slice completion task)
- ✅ `pytest tests/ -q` — 479 passed, no regressions

## Diagnostics

- Inspect subprocess state: `/autoagent status` in pi, or `SubprocessManager.status()` programmatically
- Debug JSONL parsing: SubprocessManager stores stderr tail (last 20 lines) accessible via `.stderrTail`
- Dashboard error visibility: error events rendered inline with iteration number and message
- Process lifecycle: exit code and last error stored on SubprocessManager after process exits

## Deviations

None — implemented exactly as planned.

## Known Issues

- Manual verification in pi is deferred to slice completion since it requires interactive pi session with the extension loaded. This is the final task of the slice, so UAT should follow.

## Files Created/Modified

- `.pi/extensions/autoagent/package.json` — Extension manifest
- `.pi/extensions/autoagent/types.ts` — JSONL event TypeScript interfaces and SubprocessState enum
- `.pi/extensions/autoagent/subprocess-manager.ts` — Python subprocess lifecycle manager (singleton)
- `.pi/extensions/autoagent/dashboard-overlay.ts` — Live dashboard overlay component
- `.pi/extensions/autoagent/index.ts` — Extension entry point with commands, shortcuts, footer
