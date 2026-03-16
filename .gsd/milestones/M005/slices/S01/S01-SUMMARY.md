---
id: S01
parent: M005
milestone: M005
provides:
  - JSONL output mode for `autoagent run --jsonl` with structured iteration events
  - event_callback parameter on OptimizationLoop (output-agnostic)
  - Pi extension at `.pi/extensions/autoagent/` with `/autoagent` command, `Ctrl+Alt+A` shortcut, footer status
  - SubprocessManager singleton for spawning/controlling Python subprocess with JSONL parsing
  - Dashboard overlay rendering live iteration table from subprocess events
requires: []
affects:
  - S02
  - S03
key_files:
  - src/autoagent/cli.py
  - src/autoagent/loop.py
  - tests/test_cli_jsonl.py
  - .pi/extensions/autoagent/index.ts
  - .pi/extensions/autoagent/subprocess-manager.ts
  - .pi/extensions/autoagent/dashboard-overlay.ts
  - .pi/extensions/autoagent/types.ts
  - .pi/extensions/autoagent/package.json
key_decisions:
  - D065 — JSONL output mode instead of stdout parsing
  - D067 — Process lifecycle decoupled from overlay lifecycle
  - D068 — PYTHONUNBUFFERED=1 for all spawned subprocesses
  - D069 — Loop event_callback instead of JSONL hardcoded in loop
  - D070 — SubprocessManager as singleton with bounded event buffer (200)
patterns_established:
  - JSONL event emission via callback pattern — future event types added by calling _emit() at new points
  - Extension entry point exports default function receiving ExtensionAPI
  - Overlay subscribes to SubprocessManager.onEvent() for live updates plus 1s interval for elapsed timer
  - D067 enforced structurally — overlay dispose() only clears timer and unsubscribes, never touches SubprocessManager
observability_surfaces:
  - JSONL events on stdout — machine-parseable iteration telemetry via `autoagent run --jsonl 2>/dev/null | jq .`
  - `/autoagent status` prints one-line state with PID, event count, last error
  - SubprocessManager.status() returns structured { state, pid, exitCode, lastError, eventCount, startedAt }
  - SubprocessManager stores stderr tail (last 20 lines) for post-mortem inspection
  - Dashboard renders error events inline with iteration number and message
  - Footer widget shows state-specific icons (⚡/✓/✗/■)
drill_down_paths:
  - .gsd/milestones/M005/slices/S01/tasks/T01-SUMMARY.md
  - .gsd/milestones/M005/slices/S01/tasks/T02-SUMMARY.md
duration: 50m
verification_result: passed
completed_at: 2026-03-14
---

# S01: Live Dashboard with Streaming Subprocess

**Added JSONL output mode to the Python CLI and built a pi extension with live dashboard overlay, subprocess management, and user controls for monitoring optimization runs.**

## What Happened

**T01 — JSONL output mode:** Added an `event_callback` parameter to `OptimizationLoop.__init__()` — an optional callable that receives event dicts at five points: `loop_start`, `iteration_start`, `iteration_end`, `loop_end`, and `error`. Added `--jsonl` flag to `autoagent run` that wires a JSON-line-per-event callback writing to stdout with flush, while overriding `builtins.print` to redirect human output to stderr. `iteration_end` events carry all required fields: iteration, score, decision, cost_usd, elapsed_ms, best_iteration_id, rationale, mutation_type.

**T02 — Pi extension:** Created five files in `.pi/extensions/autoagent/`. `types.ts` defines TypeScript interfaces matching the Python JSONL event schema. `subprocess-manager.ts` is a singleton that spawns `autoagent run --jsonl` with `PYTHONUNBUFFERED=1`, parses stdout line-by-line via readline into typed events, stores in bounded buffer (200), exposes `start()/stop()/status()/getEvents()/onEvent()`. Stop sends SIGTERM with 5s SIGKILL timeout. `dashboard-overlay.ts` follows GSD's overlay pattern — renders header with state badge + elapsed, goal line, iteration table (#/Score/Decision/Cost/Time/Rationale), summary and error sections, with scroll support (↑↓/j/k/g/G). `index.ts` registers `/autoagent` with `run`/`stop`/`status` subcommands, `Ctrl+Alt+A` toggle shortcut, and footer status via `ctx.ui.setStatus()` with state-specific icons.

## Verification

- `pytest tests/test_cli_jsonl.py -v` — 10/10 passed (parser flags, callback validity, event types, stderr redirect, error events, field schema)
- `pytest tests/ -q` — 479/479 passed (exceeds 469+ threshold, no regressions)
- Extension structure: all 5 expected files created with correct exports
- Manual verification in pi: deferred to UAT (requires interactive pi session)

## Requirements Advanced

- R006 — CLI now extends into pi TUI via project-local extension with commands and shortcuts
- R019 — Fire-and-forget now has dashboard visibility: start run, close overlay, reopen later
- R017 — Budget burn visible in real-time dashboard via cost_usd column

## Requirements Validated

- None moved to validated — R006/R019/R017 were already validated; this slice extends them into the TUI surface

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

None — implemented exactly as planned.

## Known Limitations

- Manual verification in pi deferred to UAT — requires interactive pi session with the extension loaded
- Dashboard renders from JSONL events only — no retroactive loading from archive (by design: dashboard is a live view)
- Event buffer capped at 200 entries — long runs lose early events from the dashboard view (archive has full history)

## Follow-ups

- S02 consumes extension scaffold and command routing for interview overlay
- S03 consumes extension scaffold for report overlay, `/autoagent stop` wiring, and final assembly

## Files Created/Modified

- `src/autoagent/loop.py` — Added event_callback parameter, _emit() helper, event emissions at 5 points
- `src/autoagent/cli.py` — Added --jsonl flag, JSONL callback wiring, builtins.print stderr redirect
- `tests/test_cli_jsonl.py` — New test file with 10 tests
- `.pi/extensions/autoagent/package.json` — Extension manifest
- `.pi/extensions/autoagent/types.ts` — JSONL event TypeScript interfaces and SubprocessState enum
- `.pi/extensions/autoagent/subprocess-manager.ts` — Python subprocess lifecycle manager (singleton)
- `.pi/extensions/autoagent/dashboard-overlay.ts` — Live dashboard overlay component
- `.pi/extensions/autoagent/index.ts` — Extension entry point with commands, shortcuts, footer

## Forward Intelligence

### What the next slice should know
- Extension entry point is `index.ts` default export receiving `ExtensionAPI` — S02/S03 add commands and overlays to the same file or import from it
- SubprocessManager is a singleton — `new SubprocessManager()` always returns the same instance. Interview (S02) needs a different subprocess mode (`--json` instead of `--jsonl`), so either extend SubprocessManager or create a separate InterviewManager
- Command routing in index.ts uses `args[0]` switch — add `new` and `report` cases for S02/S03

### What's fragile
- `builtins.print` override for stderr redirect — any code that imports print directly or uses sys.stdout.write bypasses the redirect. Works today because all existing code uses bare `print()`.
- SubprocessManager's readline parsing assumes one complete JSON object per line — if Python ever writes partial lines or multi-line JSON, parsing will break

### Authoritative diagnostics
- `autoagent run --jsonl 2>/dev/null | jq .` — validates Python JSONL output directly without the extension
- `/autoagent status` in pi — shows subprocess state, PID, event count, last error
- SubprocessManager `.stderrTail` property — last 20 lines of Python stderr for post-mortem

### What assumptions changed
- No assumptions changed — both tasks executed exactly as planned
