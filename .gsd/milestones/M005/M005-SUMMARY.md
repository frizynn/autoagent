---
id: M005
provides:
  - Pi TUI extension at `.pi/extensions/autoagent/` with 7 files (1222 LOC TypeScript)
  - `/autoagent run` with live dashboard overlay rendering JSONL subprocess events
  - `/autoagent new` with interview overlay via bidirectional JSON protocol
  - `/autoagent report` with scrollable markdown report viewer
  - `/autoagent stop` for graceful subprocess termination (SIGTERM + 5s SIGKILL)
  - `/autoagent status` with idle disk-state reading (state.json + config.json)
  - `Ctrl+Alt+A` keyboard shortcut toggling dashboard overlay
  - Footer status widget with state-specific icons (⚡/✓/✗/■)
  - Tab completion for all subcommands and --budget flag
  - JSONL output mode (`autoagent run --jsonl`) with event_callback on OptimizationLoop
  - JSON interview protocol (`autoagent new --json`) with bidirectional stdin/stdout
  - SubprocessManager singleton with bounded event buffer (200), subscriber pattern, SIGTERM/SIGKILL lifecycle
key_decisions:
  - "D064: Three slices ordered by risk — streaming dashboard (high), interview protocol (medium), assembly (low)"
  - "D065: JSONL output mode for Python CLI, not stdout parsing"
  - "D066: JSON request-response protocol for interview, not PTY forwarding"
  - "D067: Process lifecycle decoupled from overlay lifecycle"
  - "D068: PYTHONUNBUFFERED=1 for all spawned subprocesses"
  - "D069: Loop event_callback instead of JSONL hardcoded in loop"
  - "D070: SubprocessManager as singleton with bounded event buffer (200)"
  - "D071: Interview runner as standalone function, not SubprocessManager extension"
  - "D072: ctx.ui.input()/select() native dialogs, not custom overlay"
patterns_established:
  - "JSONL event emission via callback — future event types added by calling _emit() at new points"
  - "Extension entry point exports default function receiving ExtensionAPI"
  - "Overlay subscribes to SubprocessManager.onEvent() for live updates"
  - "JSON protocol: prompt/confirm/status/complete/error/abort message types with strict request-response"
  - "nextLine() async reader: bufferedLines + pendingWaiters for subprocess stdout"
  - "Static content overlay pattern using Markdown component inside box chrome"
  - "_build_json_orchestrator factory wiring JSON I/O into existing orchestrator without modification"
observability_surfaces:
  - "JSONL events on stdout — `autoagent run --jsonl 2>/dev/null | jq .`"
  - "JSON interview protocol — `autoagent new --json 2>/dev/null | jq .`"
  - "/autoagent status in pi — subprocess state, PID, event count, last error, disk state"
  - "SubprocessManager.stderrTail — last 20 lines of Python stderr for post-mortem"
  - "Footer widget — real-time optimization state visible without opening overlay"
  - "Dashboard error events rendered inline with iteration number and message"
requirement_outcomes: []
duration: 3 slices (~90min)
verification_result: passed
completed_at: 2026-03-14
---

# M005: Pi TUI Extension

**AutoAgent becomes a first-class pi citizen — live dashboard, interview overlay, report viewer, status widget, and keyboard shortcuts, all driven by structured subprocess protocols and native TUI components.**

## What Happened

Three slices shipped the full pi TUI surface for AutoAgent.

**S01 (high risk — streaming)** added `event_callback` to `OptimizationLoop` and `--jsonl` to `autoagent run`, emitting structured JSON lines at five lifecycle points (loop_start, iteration_start, iteration_end, loop_end, error). The pi extension scaffold landed: `index.ts` with `/autoagent` command registration and `Ctrl+Alt+A` shortcut, `subprocess-manager.ts` as a singleton managing spawn/stop/status with JSONL line parsing via readline, `dashboard-overlay.ts` rendering a live iteration table with scroll support, `types.ts` for shared interfaces, and `package.json` for the extension manifest. Footer status widget wired via `ctx.ui.setStatus()` with state-specific icons. This retired the highest risk: subprocess streaming with real-time TUI rendering.

**S02 (medium risk — bidirectional protocol)** added `--json` to `autoagent new` with a strict request-response JSON protocol over stdin/stdout. `_build_json_orchestrator()` wraps the existing `InterviewOrchestrator` with JSON I/O closures — no orchestrator modifications needed. `interview-runner.ts` spawns the subprocess, reads JSON prompts via an async line reader (bufferedLines/pendingWaiters pattern), renders them as native `ctx.ui.input()`/`ctx.ui.select()` dialogs, and writes answers back to stdin. Escape sends abort and kills the process. This retired the bidirectional protocol risk.

**S03 (low risk — assembly)** added `report-overlay.ts` as a static markdown viewer using pi's `Markdown` component, enhanced `case "status"` to read `.autoagent/state.json` and `config.json` for idle-state detail, and added `getArgumentCompletions` for tab completion of all subcommands plus `--budget`. The final extension has 7 files, 1222 lines of TypeScript, with a clean acyclic dependency graph.

All three slices executed without deviations from risk ordering. The Python test suite grew from 479 (post-S01) to 496 (post-S03) with zero regressions.

## Cross-Slice Verification

**Success Criterion: `/autoagent run` shows live dashboard** — Verified. `case "run"` in index.ts calls `SubprocessManager.start()` which spawns `autoagent run --jsonl` with `PYTHONUNBUFFERED=1`. Dashboard overlay subscribes via `onEvent()` and renders iteration table. 10 JSONL protocol tests pass.

**Success Criterion: `/autoagent new` completes interview in TUI overlay** — Verified. `case "new"` routes to `runInterview()` in interview-runner.ts. Bidirectional JSON protocol handles all 6 interview phases including vague-input follow-ups. 17 protocol tests pass.

**Success Criterion: `/autoagent report` renders markdown in scrollable overlay** — Verified. `case "report"` runs `autoagent report` via execFile, reads `.autoagent/report.md`, opens ReportOverlay with Markdown component and scroll support.

**Success Criterion: `Ctrl+Alt+A` toggles dashboard without affecting running optimization** — Verified. `pi.registerShortcut(Key.ctrlAlt("a"), ...)` registered at index.ts:287. D067 enforced structurally: overlay dispose() only clears timer and unsubscribes, never touches SubprocessManager.

**Success Criterion: Footer status widget shows optimization state** — Verified. `ctx.ui.setStatus("autoagent", ...)` with five states: idle (empty), running (`⚡ iteration N`), done (`✓ done`), error (`✗ error`), stopped (`■ stopped`).

**Success Criterion: `/autoagent stop` gracefully terminates** — Verified. `case "stop"` calls `SubprocessManager.stop()` which sends SIGTERM with 5-second SIGKILL timeout.

**Test suite: 496 passed**, 0 failed (threshold: 469+). No regressions from M004 baseline.

**Visual/interactive UAT** — Deferred. Overlay rendering, scroll behavior, and footer appearance require an interactive pi session. All structural contracts verified by code audit and protocol tests.

## Requirement Changes

No requirements changed status during M005. R006, R019, and R017 were already validated — this milestone extended their surfaces into the pi TUI but did not change their validation status. The 5 active requirements (R011, R012, R013, R018, R024) remain active and are M002 search intelligence scope.

## Forward Intelligence

### What the next milestone should know
- The extension has 7 files with a clean dependency graph rooted at `index.ts`. All overlay patterns are established — dashboard (live-updating), interview (sequential dialogs), report (static markdown).
- SubprocessManager is a singleton for `run --jsonl`. Interview uses a separate `runInterview()` function with its own short-lived subprocess. If future features need another subprocess mode, follow the interview pattern (standalone function) not the singleton pattern.
- `--project-dir` is a parser-level argument in argparse, placed before the subcommand name in spawn args.
- `builtins.print` override redirects to stderr in both `--jsonl` and `--json` modes. Any code using `sys.stdout.write` directly bypasses this.

### What's fragile
- `builtins.print` stderr redirect — any code that imports print directly or uses sys.stdout.write bypasses it. Works today because all existing code uses bare `print()`.
- JSON protocol relies on strict one-line-at-a-time stdout — any stray print in `--json` mode corrupts the protocol stream.
- Report overlay assumes `.autoagent/report.md` exists after `autoagent report` succeeds — if CLI changes output paths, overlay breaks silently.
- `execFile` paths assume `autoagent` is on PATH — if the venv isn't activated, all subprocess commands fail.

### Authoritative diagnostics
- `autoagent run --jsonl 2>/dev/null | jq .` — validates JSONL output directly without the extension
- `autoagent new --json 2>/dev/null | jq .` — validates interview protocol messages
- `.venv/bin/python -m pytest tests/ -q` — 496 tests, authoritative contract verification
- `/autoagent status` in pi — subprocess state, PID, event count, last error, disk state

### What assumptions changed
- No major assumptions changed. The extension loader, subprocess streaming, and bidirectional protocol all worked as designed. Minor discovery: `--project-dir` must precede the subcommand in argparse, not follow it.

## Files Created/Modified

- `.pi/extensions/autoagent/package.json` — Extension manifest
- `.pi/extensions/autoagent/types.ts` — JSONL event TypeScript interfaces and SubprocessState enum
- `.pi/extensions/autoagent/subprocess-manager.ts` — Python subprocess lifecycle manager (singleton, JSONL parsing, bounded buffer)
- `.pi/extensions/autoagent/dashboard-overlay.ts` — Live dashboard overlay with iteration table and scroll
- `.pi/extensions/autoagent/interview-runner.ts` — Bidirectional JSON protocol driver for interview
- `.pi/extensions/autoagent/report-overlay.ts` — Scrollable markdown report overlay
- `.pi/extensions/autoagent/index.ts` — Extension entry point: commands, shortcuts, footer, completions
- `src/autoagent/loop.py` — event_callback parameter, _emit() helper
- `src/autoagent/cli.py` — --jsonl flag, --json flag, _json_emit, _build_json_orchestrator, _cmd_new_inner
- `tests/test_cli_jsonl.py` — 10 JSONL protocol tests
- `tests/test_cli_json_interview.py` — 17 interview protocol tests
