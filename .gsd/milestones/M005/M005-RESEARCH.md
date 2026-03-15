# M005: Pi TUI Extension — Research

**Date:** 2026-03-14

## Summary

The pi extension system is well-documented by example: the GSD extension (`~/.gsd/agent/extensions/gsd/`) is a 30+ file TypeScript extension that registers commands, keyboard shortcuts, overlays, widgets, status lines, and lifecycle hooks. It's the authoritative pattern. The AutoAgent extension lives at `.pi/extensions/autoagent/index.ts`, loaded by pi's jiti-based TypeScript JIT. The extension API (`@gsd/pi-coding-agent`) provides `registerCommand`, `registerShortcut`, `ui.custom` (overlays), `ui.setStatus`, `ui.setWidget`, `ui.notify`, `ui.select`, `ui.input`, and `pi.exec()`. The TUI layer (`@gsd/pi-tui`) provides rendering primitives: `Text`, `Box`, `Input`, `SelectList`, `Markdown`, `Loader`, `Key`, `matchesKey`, `truncateToWidth`, `visibleWidth`.

The biggest technical challenge is **live subprocess streaming**. `pi.exec()` returns only when the process exits — unusable for monitoring an optimization loop that runs indefinitely. The extension must use Node.js `child_process.spawn()` directly and parse stdout line-by-line. This requires the Python CLI to emit structured output (JSON lines) so the TypeScript dashboard can parse iteration data in real-time. The Python `OptimizationLoop.run()` is currently a blocking call that writes only to `logging` and to disk state files — it prints nothing structured to stdout during iteration. A thin `--jsonl` output mode must be added to `cmd_run` that emits one JSON line per iteration event without touching the core loop logic (decorator pattern around state writes).

**Primary recommendation:** Prove subprocess streaming + dashboard rendering first (highest risk). Reuse the GSD dashboard overlay pattern exactly — same `ui.custom()` overlay, same `render(width): string[]` interface, same `handleInput()` for scrolling. For the interview, use a structured JSON protocol (Python `--json` mode emitting prompts, TypeScript rendering TUI inputs and piping answers back via stdin) rather than PTY forwarding — it's more work upfront but produces a native TUI experience. For the report, `pi.exec()` is sufficient since it's a one-shot command that exits.

## Recommendation

**Slice ordering by risk:**
1. **Extension scaffolding + live dashboard** (highest risk) — Prove the spawn+stream+overlay pipeline works. Add `--jsonl` to Python CLI. Build the dashboard overlay showing iteration progress from live subprocess output + disk state fallback.
2. **Interview in TUI** (medium risk) — Add `--json` interactive mode to Python interview. Build TUI overlay that renders interview phases as pi input/select dialogs.
3. **Report + status + stop + assembly** (low risk) — Report overlay (Markdown component), status from disk state, stop via process signal, Ctrl+Alt+A shortcut, footer widget. Final integration proof.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Overlay rendering with scroll, keyboard, box drawing | GSD `dashboard-overlay.ts` pattern — `ui.custom()` + Component with `render(width): string[]` + `handleInput()` | Proven pattern, handles scroll offset, viewport clamping, box borders, theme colors |
| Command registration with subcommands and autocomplete | GSD `commands.ts` — `registerCommand()` with `getArgumentCompletions` | Exact same shape needed for `/autoagent new|run|status|report|stop` |
| Keyboard shortcut registration | GSD `index.ts` — `registerShortcut(Key.ctrlAlt("g"), ...)` | Same pattern for `Ctrl+Alt+A` |
| Footer status widget | `ui.setStatus(key, text)` | One-liner, already in the API |
| Markdown rendering in overlay | `Markdown` component from `@gsd/pi-tui` | Already supports scrollable markdown rendering |
| JSON line parsing from subprocess | Node.js readline + `child_process.spawn()` | Standard Node.js — no library needed |

## Existing Code and Patterns

- `~/.gsd/agent/extensions/gsd/index.ts` — Extension entry point pattern: default export function receiving `ExtensionAPI`, registers commands, shortcuts, hooks. **Reuse structure exactly.**
- `~/.gsd/agent/extensions/gsd/commands.ts` — `registerCommand("gsd", { handler, getArgumentCompletions })` with subcommand dispatch via string parsing. **Clone for `/autoagent`.**
- `~/.gsd/agent/extensions/gsd/dashboard-overlay.ts` — `GSDDashboardOverlay` class: constructor takes `(tui, theme, onClose)`, has `handleInput(data)` for keyboard, `render(width): string[]` for drawing, `refreshTimer` for periodic updates, `scrollOffset` for scrolling, `invalidate()` for cache bust. **Model the AutoAgent dashboard identically.**
- `src/autoagent/cli.py` — Python CLI with `cmd_new`, `cmd_run`, `cmd_report`, `cmd_status`. All print to stdout/stderr. `cmd_run` calls `loop.run()` which blocks. **Extend, don't modify core.**
- `src/autoagent/loop.py` — `OptimizationLoop.run()` — blocking loop, writes state via `StateManager.write_state()` after each iteration. Logs via `logging.getLogger()`. **Add event callback hooks or JSON line output wrapper.**
- `src/autoagent/state.py` — `ProjectState` (phase, current_iteration, best_iteration_id, total_cost_usd, started_at, updated_at), `ProjectConfig` (goal, benchmark, budget_usd, search_space, constraints, metric_priorities). **Read these from disk in the extension for state sync.**
- `src/autoagent/archive.py` — Archive entries as `NNN-{keep|discard}.json` + `NNN-pipeline.py`. `ArchiveEntry` has evaluation_result, decision, rationale, mutation_type, pareto_evaluation. **Parse JSON files directly for dashboard data.**
- `src/autoagent/interview.py` — `InterviewOrchestrator` with 6 phases, vague-input detection, follow-up probes. Uses `input()/print()`. **Add JSON protocol mode for TUI integration.**
- `src/autoagent/report.py` — `generate_report()` returns `ReportResult` with `.markdown` and `.summary`. **Call via subprocess, render `.markdown` in Markdown component.**

## Constraints

- **Extension must be TypeScript** — loaded by pi's jiti-based extension loader from `.pi/extensions/autoagent/index.ts`
- **Can import from** `@gsd/pi-tui`, `@gsd/pi-coding-agent`, `@gsd/pi-agent-core`, `@sinclair/typebox` — these are available in the pi runtime, no npm install needed
- **Cannot import from** npm packages not bundled with pi — no adding dependencies
- **Python `autoagent` must be in PATH** — the venv must be activated or the package installed
- **`pi.exec()` is one-shot only** — returns `ExecResult` after process exits. For streaming, must use `child_process.spawn()` directly
- **Extension directory**: `.pi/extensions/autoagent/` (project-local, auto-discovered by pi)
- **No modification to Python core loop logic** — the `--jsonl` output mode must be a wrapper around existing `cmd_run`, not changes to `OptimizationLoop` internals
- **Disk state is the source of truth** — `.autoagent/state.json`, `.autoagent/archive/`, `.autoagent/config.json` are read by both Python CLI and TypeScript extension

## Common Pitfalls

- **Subprocess stdout buffering** — Python buffers stdout by default when piped. The extension will see no output until the buffer fills or the process exits. **Fix: launch Python with `-u` flag (unbuffered) or `PYTHONUNBUFFERED=1` env var, or use `flush=True` in print statements.**
- **JSON line parsing with partial reads** — Spawn stdout comes as arbitrary chunks, not line-aligned. **Fix: buffer incoming data and split on newlines, parsing only complete lines.**
- **Process cleanup on overlay close** — If the user closes the dashboard overlay, the Python subprocess must keep running. If the user runs `/autoagent stop`, the subprocess must be killed gracefully. **Fix: decouple process lifecycle from overlay lifecycle. Process is managed by the extension module, overlay is just a view.**
- **State file race conditions** — Both the Python loop and the TypeScript extension read `.autoagent/state.json`. The Python side writes atomically (temp file + rename), so reads are safe. But the extension should not assume state.json reflects the very latest iteration — it may lag by one write cycle.
- **Interview stdin/stdout interleaving** — If the Python interview emits a JSON prompt to stdout and reads from stdin, the TypeScript extension must not write to stdin before reading the full prompt line. **Fix: strict request-response protocol — Python writes one JSON line, waits for one JSON line response.**
- **Overlay component lifecycle** — The `custom()` overlay promise resolves when `done()` is called. If the overlay is used for the interview flow, the interview must complete (or be cancelled) before `done()` fires. Timer-based dashboard refreshes must be cleaned up in `dispose()`.

## Open Risks

- **Python venv detection** — The extension needs to find and invoke `autoagent`. If installed in a venv, the extension must either find the venv's Python or assume `autoagent` is on PATH. Could fail silently if the venv isn't activated. Mitigation: check `which autoagent` at extension load, notify user if not found.
- **Interview JSON protocol design** — No existing protocol exists. Must be designed from scratch: phase prompts, user responses, follow-up probes, validation errors, completion. Risk of protocol evolution breaking compatibility. Mitigation: version the protocol, keep it simple (one request → one response per phase).
- **Dashboard data richness** — The current Python loop logs via `logging` but doesn't emit structured iteration events to stdout. The `--jsonl` mode is new code that must capture: iteration number, score, decision (keep/discard), cost, elapsed time, safety gate results. This data exists in the loop but isn't surfaced — must tap into state writes without modifying loop logic.
- **Graceful stop** — Sending SIGINT to the Python subprocess triggers KeyboardInterrupt. The loop has no explicit signal handler — it would crash mid-iteration. Need to verify the loop's `finally` block (lock release) handles this, and add clean shutdown logic if not.

## Requirements Analysis

**Active requirements touched by M005:**
- R006 (PI-Based CLI) — supporting. The Python CLI stays; the pi extension is the TUI layer on top. D017 reinterpreted R006 as Python CLI, but M005 context says "supporting" — this extends the UX into pi.
- R019 (Fire-and-Forget) — supporting. Dashboard gives visibility without requiring attention. User can toggle dashboard while optimization runs in background.
- R017 (Budget) — supporting. Dashboard shows budget burn in real-time.

**No new Active requirements needed.** M005 is a UX layer — it doesn't add core capabilities, just surfaces existing ones. The interview, run, report, and status capabilities already work via Python CLI. The extension wraps them.

**Candidate requirements to consider (advisory, not auto-binding):**
- **CR001: Live iteration visibility** — User can see iteration progress, scores, and decisions in real-time during optimization. (Currently implicit in M005 scope, could be explicit.)
- **CR002: Non-blocking optimization** — Optimization runs in background while user continues other pi work. (Currently in M005 scope as "operational complete".)

These are captured in the M005 context's "user-visible outcome" and "completion class" sections already — no need to formalize as separate requirements unless the user wants them tracked.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| TUI design | `hyperb1iss/hyperskills@tui-design` (111 installs) | available — generic TUI design patterns, not pi-specific |
| Pi extensions | (none) | no pi-specific extension skill exists |

The `tui-design` skill is generic and not pi-specific. The GSD extension source code is a better reference than any external skill. **No skill installation recommended.**

## Sources

- Pi extension API types — `@gsd/pi-coding-agent` ExtensionAPI, ExtensionUIContext, ExtensionCommandContext (source: type definitions in node_modules)
- Pi TUI primitives — `@gsd/pi-tui` Text, Box, Input, Markdown, SelectList, Key, matchesKey (source: type definitions in node_modules)
- GSD extension — authoritative extension pattern with commands, overlays, shortcuts, widgets, lifecycle hooks (source: `~/.gsd/agent/extensions/gsd/`)
- Python autoagent CLI — cmd_new, cmd_run, cmd_report, cmd_status (source: `src/autoagent/cli.py`)
- Python optimization loop — blocking run(), state persistence, archive writes (source: `src/autoagent/loop.py`)
- Pi extension loader — discovers from `.pi/extensions/` with jiti TypeScript JIT (source: `@gsd/pi-coding-agent/dist/core/extensions/loader.js`)
