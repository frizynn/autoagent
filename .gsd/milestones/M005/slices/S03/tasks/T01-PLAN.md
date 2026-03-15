---
estimated_steps: 5
estimated_files: 2
---

# T01: Build report overlay, enhance status, add autocomplete

**Slice:** S03 — Report, Status, Stop, and Final Assembly
**Milestone:** M005

## Description

Create the report overlay component, wire `case "report"` into the command handler, enhance `/autoagent status` to show disk state when idle, and add `getArgumentCompletions` for subcommand tab-completion. All TypeScript, all in the extension.

## Steps

1. **Create `report-overlay.ts`** — Follow the `dashboard-overlay.ts` pattern exactly: constructor receives `(tui, theme, onClose)`, stores scroll state. `render(width)` builds content lines via `Markdown` component from `@gsd/pi-tui`, wraps in box chrome using the same `wrapInBox` method. `handleInput` handles scroll (↑↓/j/k/g/G) and close (Esc/Ctrl+C). `dispose()` cleans up. Constructor takes the markdown text and creates `new Markdown(text, 1, 1, markdownTheme)` where `markdownTheme` comes from `getMarkdownTheme()` imported from `@gsd/pi-coding-agent`. The overlay renders whatever markdown was passed — it's a dumb viewer.

2. **Wire `case "report"` in `index.ts`** — Use `child_process.execFile` to run `autoagent --project-dir <cwd> report`. On success, read `.autoagent/report.md` via `fs.readFileSync`. If the file exists, open report overlay via `ctx.ui.custom()` (same pattern as `openDashboard`). If `execFile` fails or file doesn't exist, show error via `ctx.ui.notify`. Handle the "no project" case (exit code non-zero).

3. **Enhance `case "status"` in `index.ts`** — When `SubprocessManager.status().state === SubprocessState.Idle`, try reading `.autoagent/state.json` and `.autoagent/config.json` from `process.cwd()`. If they exist, parse and show: phase, current iteration, best score, total cost, goal (from config). If files don't exist, show "No project found" or current idle message.

4. **Add `getArgumentCompletions`** — On the `registerCommand("autoagent", { ... })` options, add `getArgumentCompletions: (prefix) => { ... }` following the GSD commands.ts pattern. Subcommands: `["run", "stop", "status", "new", "report"]`. Filter by `startsWith(prefix)`, return `{ value, label }` array.

5. **Update the default case message** — Change the "Unknown subcommand" notification to include "report" in the list.

## Must-Haves

- [ ] `report-overlay.ts` exports `AutoagentReportOverlay` class with `render(width): string[]`, `handleInput(data: string): void`, `dispose(): void`
- [ ] Report overlay uses `Markdown` component from `@gsd/pi-tui` with `getMarkdownTheme()` from `@gsd/pi-coding-agent`
- [ ] Report overlay renders inside box chrome with scroll support (same pattern as dashboard)
- [ ] `case "report"` runs `autoagent report` via `execFile`, reads `.autoagent/report.md`, opens overlay
- [ ] `case "report"` handles errors gracefully: no project, report generation failure, missing file
- [ ] `case "status"` reads disk state (state.json + config.json) when subprocess is idle
- [ ] `getArgumentCompletions` returns filtered subcommand suggestions
- [ ] All existing pytest tests still pass (479+)

## Verification

- All 7 extension files exist: `package.json`, `types.ts`, `subprocess-manager.ts`, `dashboard-overlay.ts`, `report-overlay.ts`, `interview-runner.ts`, `index.ts`
- `report-overlay.ts` imports `Markdown` from `@gsd/pi-tui` and `getMarkdownTheme` from `@gsd/pi-coding-agent`
- `index.ts` has `case "report"` in the switch statement
- `index.ts` has `getArgumentCompletions` in registerCommand options
- `pytest tests/ -q` — 479+ tests pass

## Inputs

- `.pi/extensions/autoagent/dashboard-overlay.ts` — Pattern to follow for report overlay (box chrome, scroll, render/handleInput/dispose)
- `.pi/extensions/autoagent/index.ts` — Command handler to extend with `case "report"`, status enhancement, autocomplete
- `~/.gsd/agent/extensions/gsd/commands.ts` — `getArgumentCompletions` pattern reference
- S01 summary — SubprocessManager.status(), SubprocessState enum, overlay lifecycle pattern
- S03 research — Markdown component API, getMarkdownTheme, execFile vs pi.exec() tradeoff

## Observability Impact

- **Report generation failure visibility:** `case "report"` captures stderr from `autoagent report` and surfaces it via `ctx.ui.notify` with severity "warning". A future agent running `/autoagent report` and seeing a notification knows exactly what went wrong.
- **Idle status disk state:** `/autoagent status` when idle now reads `.autoagent/state.json` and `.autoagent/config.json`, showing phase, iteration, best score, cost, and goal. This is the primary inspection surface for checking optimization results after a run completes and the subprocess has exited.
- **Missing project detection:** Both `case "report"` and `case "status"` detect when no `.autoagent/` project exists and display a specific "No AutoAgent project" message rather than a generic error.

## Expected Output

- `.pi/extensions/autoagent/report-overlay.ts` — New file, report viewer overlay component
- `.pi/extensions/autoagent/index.ts` — Modified with report case, enhanced status, autocomplete
