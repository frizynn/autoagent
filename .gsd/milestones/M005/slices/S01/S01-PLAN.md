# S01: Live Dashboard with Streaming Subprocess

**Goal:** User runs `/autoagent run` in pi and sees a live dashboard overlay updating with iteration progress, scores, decisions, cost, and elapsed time from a real Python subprocess.
**Demo:** Start pi in the autoagent project, run `/autoagent run`, see dashboard overlay appear with streaming JSONL iteration events rendered in real-time. `Ctrl+Alt+A` toggles the overlay. Footer shows optimization state. `/autoagent stop` kills the subprocess.

## Must-Haves

- Python `autoagent run --jsonl` emits one JSON line per iteration event to stdout (iteration_start, iteration_end, loop_start, loop_end, error)
- JSONL events include: iteration number, phase, score, decision (keep/discard), cost_usd, elapsed_ms, best_iteration_id, rationale summary
- Pi extension at `.pi/extensions/autoagent/index.ts` is discovered and loaded by pi's jiti loader
- `/autoagent` command registered with subcommand dispatch (run, stop, status)
- SubprocessManager spawns `autoagent run --jsonl` with `PYTHONUNBUFFERED=1`, parses JSONL lines, exposes process lifecycle (start/stop/status/events)
- Dashboard overlay renders iteration table with columns: #, score, decision, cost, elapsed
- `Ctrl+Alt+A` keyboard shortcut toggles dashboard overlay
- Footer status widget shows optimization state (idle / running iteration N / paused / completed)
- Closing the overlay does NOT kill the subprocess (D067: process lifecycle decoupled from overlay lifecycle)
- `/autoagent stop` sends SIGTERM to the subprocess and updates footer status

## Proof Level

- This slice proves: integration
- Real runtime required: yes (Python subprocess + pi extension loading)
- Human/UAT required: yes (visual confirmation of dashboard layout and streaming updates)

## Verification

- `pytest tests/test_cli_jsonl.py -v` — Python JSONL output mode tests: correct event structure, line-buffered JSON, all event types emitted, error event on failure
- Manual verification in pi: load extension, run `/autoagent run`, confirm dashboard renders, `Ctrl+Alt+A` toggles, footer updates, `/autoagent stop` kills subprocess
- `pytest tests/ -q` — existing 469+ tests still pass (no regressions)

## Observability / Diagnostics

- Runtime signals: JSONL events on stdout (machine-parseable), stderr preserved for human-readable errors/warnings
- Inspection surfaces: `/autoagent status` command shows subprocess PID, state, last event; footer widget shows state at a glance
- Failure visibility: SubprocessManager captures stderr, exposes last error, exit code; dashboard shows error events inline
- Redaction constraints: none (no secrets in optimization telemetry)

## Integration Closure

- Upstream surfaces consumed: `src/autoagent/cli.py` (cmd_run), `src/autoagent/loop.py` (OptimizationLoop)
- New wiring introduced in this slice: `.pi/extensions/autoagent/index.ts` → command registration + shortcut + footer; SubprocessManager → child_process.spawn → Python `--jsonl`; JSONL stdout pipe → dashboard overlay state
- What remains before the milestone is truly usable end-to-end: S02 (interview overlay), S03 (report overlay, full assembly, end-to-end verification)

## Tasks

- [x] **T01: Add JSONL output mode to Python CLI** `est:1.5h`
  - Why: The extension needs structured machine-readable events from the Python subprocess — human-readable stdout is fragile to parse (D065). This provides the data contract that T02 consumes.
  - Files: `src/autoagent/cli.py`, `src/autoagent/loop.py`, `tests/test_cli_jsonl.py`
  - Do: Add `--jsonl` flag to `cmd_run`. Create a JSONL emitter callback that the loop calls at iteration boundaries (start/end). Emit structured events: `{"event": "iteration_end", "iteration": N, "score": 0.85, "decision": "keep", "cost_usd": 0.001, "elapsed_ms": 1200, "best_iteration_id": "3", "rationale": "..."}`. Also emit `loop_start`, `loop_end`, and `error` events. Route JSONL to stdout, human output to stderr when `--jsonl` is active. Ensure existing non-JSONL behavior is unchanged.
  - Verify: `pytest tests/test_cli_jsonl.py -v` passes; `pytest tests/test_cli.py -v` still passes (no regression)
  - Done when: `autoagent run --jsonl` emits valid JSON lines for all iteration events, and existing CLI tests pass unchanged

- [x] **T02: Pi extension with SubprocessManager, dashboard overlay, and controls** `est:2.5h`
  - Why: This is the user-facing integration — everything from T01's JSONL events needs to render in a live TUI dashboard that the user can toggle, with subprocess lifecycle controls.
  - Files: `.pi/extensions/autoagent/index.ts`, `.pi/extensions/autoagent/subprocess-manager.ts`, `.pi/extensions/autoagent/dashboard-overlay.ts`, `.pi/extensions/autoagent/types.ts`, `.pi/extensions/autoagent/package.json`
  - Do: (1) Create package.json with `@gsd/pi-coding-agent` and `@gsd/pi-tui` as peerDependencies. (2) Create types.ts defining JSONL event interfaces. (3) Create SubprocessManager class: spawns `autoagent run --jsonl` via child_process.spawn with `PYTHONUNBUFFERED=1`, reads stdout line-by-line, parses JSON, emits typed events, tracks process state (idle/running/completed/error), exposes start()/stop()/status()/onEvent(). (4) Create dashboard overlay following GSD's `dashboard-overlay.ts` pattern: render iteration table, auto-refresh from SubprocessManager events, scroll with ↑↓/j/k, close with Esc. (5) Create index.ts: register `/autoagent` command with `run`/`stop`/`status` subcommands, register `Ctrl+Alt+A` shortcut toggling overlay, set footer status widget via `ctx.ui.setStatus()`. Ensure overlay close doesn't kill subprocess (D067). `/autoagent stop` sends SIGTERM.
  - Verify: Extension loads in pi without errors (`/autoagent` command appears). `/autoagent run` spawns subprocess and dashboard shows streaming events. `Ctrl+Alt+A` toggles overlay. `/autoagent stop` terminates subprocess. Footer reflects state.
  - Done when: Full live dashboard flow works in pi: run → stream → toggle → stop, with footer status throughout

## Files Likely Touched

- `src/autoagent/cli.py`
- `src/autoagent/loop.py`
- `tests/test_cli_jsonl.py`
- `.pi/extensions/autoagent/index.ts`
- `.pi/extensions/autoagent/subprocess-manager.ts`
- `.pi/extensions/autoagent/dashboard-overlay.ts`
- `.pi/extensions/autoagent/types.ts`
- `.pi/extensions/autoagent/package.json`
