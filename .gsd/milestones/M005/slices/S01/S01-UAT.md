# S01: Live Dashboard with Streaming Subprocess — UAT

**Milestone:** M005
**Written:** 2026-03-14

## UAT Type

- UAT mode: mixed
- Why this mode is sufficient: Python JSONL output is artifact-driven (automated tests), but the pi extension dashboard, shortcut, and footer require live-runtime visual confirmation in an interactive pi session

## Preconditions

- Python venv active with autoagent installed (`pip install -e .`)
- A valid `.autoagent/` project directory with `config.json` and `benchmark.json` (run `autoagent new` first or use an existing project)
- pi installed and able to load project-local extensions from `.pi/extensions/`
- `pytest tests/test_cli_jsonl.py -v` passes (10/10) — confirms JSONL contract before testing extension

## Smoke Test

Run `autoagent run --jsonl 2>/dev/null | head -5` in the project directory. You should see 1+ valid JSON lines with `"event"` keys. If this fails, the extension has nothing to render.

## Test Cases

### 1. JSONL output produces valid structured events

1. Run `autoagent run --jsonl 2>/dev/null | head -20`
2. Pipe through `jq .` to validate JSON
3. **Expected:** Each line is valid JSON. First line has `"event": "loop_start"` with `goal` and `budget_usd`. Subsequent lines include `"event": "iteration_start"` and `"event": "iteration_end"` with fields: iteration, score, decision, cost_usd, elapsed_ms, best_iteration_id, rationale, mutation_type

### 2. Human output redirected to stderr under --jsonl

1. Run `autoagent run --jsonl 2>stderr.log 1>stdout.log`
2. Wait for at least one iteration or Ctrl+C after a few seconds
3. Inspect `stdout.log` — should contain only JSON lines
4. Inspect `stderr.log` — should contain human-readable output (iteration messages, status)
5. **Expected:** stdout is pure JSONL, stderr has human text. No mixing.

### 3. Extension loads and /autoagent command is available

1. Start pi in the autoagent project directory
2. Type `/autoagent` and press Enter
3. **Expected:** Command is recognized. Shows usage or subcommand help (run/stop/status). No "unknown command" error.

### 4. /autoagent run spawns subprocess and shows dashboard

1. In pi, type `/autoagent run`
2. **Expected:** Dashboard overlay appears with header showing "AutoAgent Dashboard" and state badge "RUNNING". Iteration table populates as events arrive. Columns visible: #, Score, Decision, Cost, Time, Rationale.

### 5. Dashboard updates in real-time

1. With dashboard open from test 4, watch for 2-3 iterations
2. **Expected:** New rows appear in the iteration table without manual refresh. Elapsed time in header ticks up. Score and decision values match what the optimization loop is doing.

### 6. Ctrl+Alt+A toggles dashboard overlay

1. With dashboard open, press `Ctrl+Alt+A`
2. **Expected:** Dashboard closes, returning to normal pi view
3. Press `Ctrl+Alt+A` again
4. **Expected:** Dashboard reopens showing the same data (subprocess still running)

### 7. Closing overlay does NOT kill subprocess (D067)

1. Open dashboard with `/autoagent run` or `Ctrl+Alt+A`
2. Press `Esc` to close the overlay
3. Type `/autoagent status`
4. **Expected:** Status shows "running" with a PID and event count. The subprocess was NOT killed by closing the overlay.

### 8. /autoagent stop terminates subprocess

1. With a running optimization (from test 4 or 7), type `/autoagent stop`
2. **Expected:** Subprocess terminates. Footer status changes to "■ stopped" or similar. `/autoagent status` shows state as "stopped" with exit code.

### 9. Footer status widget reflects optimization state

1. Before running: check footer — should show no autoagent status or "idle"
2. Run `/autoagent run` — footer should show "⚡ Running iteration N" (updating with each iteration)
3. After optimization completes or is stopped — footer should show "✓ done" or "■ stopped"
4. **Expected:** Footer accurately reflects subprocess state at each phase

### 10. /autoagent status shows diagnostic info

1. Run `/autoagent run`, wait for a few iterations
2. Type `/autoagent status` (may need to close overlay first or use in another way)
3. **Expected:** One-line output showing state (running), PID, event count, and optionally last error

## Edge Cases

### Subprocess exits with error

1. Ensure `.autoagent/config.json` points to a nonexistent benchmark file
2. Run `/autoagent run`
3. **Expected:** Dashboard shows an error event with the exception message. Footer status changes to "✗ error". Process state becomes "error" with exit code.

### Double-run attempt

1. With an optimization already running, type `/autoagent run` again
2. **Expected:** Refused with a message like "optimization already running" — does NOT spawn a second process

### Stop when nothing is running

1. Without any running optimization, type `/autoagent stop`
2. **Expected:** Message indicating nothing to stop — no crash or unhandled error

### Toggle overlay when nothing has run

1. Press `Ctrl+Alt+A` before ever running `/autoagent run`
2. **Expected:** Dashboard opens but shows empty state or "No optimization running" — no crash

## Failure Signals

- `/autoagent` returns "unknown command" → extension not loaded (check `.pi/extensions/autoagent/index.ts` exists and exports default function)
- Dashboard never shows data → SubprocessManager not parsing JSONL (check `autoagent run --jsonl` produces output directly)
- Footer never updates → `ctx.ui.setStatus()` not being called or SubprocessManager events not firing
- Overlay close kills the subprocess → D067 violation, check `dispose()` implementation
- JSON parse errors in pi console → Python outputting non-JSON to stdout (check stderr redirect is working)

## Requirements Proved By This UAT

- R006 — CLI extends into pi TUI (extension loads, commands register, overlays render)
- R019 — Fire-and-forget with dashboard visibility (start run, close overlay, reopen later, process survives)
- R017 — Budget burn visible in real-time dashboard (cost_usd column updates per iteration)

## Not Proven By This UAT

- Interview overlay (S02 scope)
- Report overlay, end-to-end assembly (S03 scope)
- Real LLM provider wiring (uses MockLLM in tests)
- Long-running stability (200+ iterations, buffer eviction behavior)

## Notes for Tester

- The Python subprocess uses MockLLM by default, so iterations will be fast (~100ms each). Real LLM runs would be slower but the streaming behavior is identical.
- If pi doesn't discover the extension, check that the extension loader supports `.pi/extensions/` directory and that `package.json` has the right structure.
- The `PYTHONUNBUFFERED=1` env var (D068) is critical — without it, you may see no output until the process exits. If the dashboard is blank, verify the env var is being set in subprocess-manager.ts.
