# S03: Report, Status, Stop, and Final Assembly — Research

**Date:** 2026-03-14

## Summary

S03 is the assembly slice — most of the hard infrastructure is already built. S01 delivered the extension scaffold, SubprocessManager, dashboard overlay, `Ctrl+Alt+A` shortcut, footer widget, and `/autoagent run|stop|status`. S02 delivered the interview runner and `case "new"` routing. What remains is: (1) a report overlay that runs `autoagent report` via `pi.exec()`, reads `report.md` from disk, and renders it in a scrollable `Markdown` component overlay, (2) enhancing `/autoagent status` to read disk state when no subprocess is running, (3) adding `getArgumentCompletions` for subcommand autocomplete, and (4) verification that the whole system hangs together.

The `Markdown` component from `@gsd/pi-tui` is a ready-to-use renderer: `new Markdown(text, paddingX, paddingY, markdownTheme)` with `render(width): string[]`. The `getMarkdownTheme()` function from `@gsd/pi-coding-agent` provides a theme. The report overlay follows the exact same `ui.custom()` pattern as the dashboard but wraps a `Markdown` component instead of custom line rendering. `pi.exec("autoagent", ["--project-dir", dir, "report"])` generates the report and writes `.autoagent/report.md` — then the overlay reads that file. Two-step because `pi.exec()` returns stdout (the summary line), but the full markdown is on disk.

The `/autoagent stop` command is already fully wired in S01 via `SubprocessManager.stop()` with SIGTERM + 5s SIGKILL fallback. The `/autoagent status` currently shows SubprocessManager state via notification — enhancement is to also read `.autoagent/state.json` for disk-based status when subprocess is idle (iteration count, best score, phase, cost).

Primary recommendation: one task for the TypeScript extension changes (report overlay, status enhancement, autocomplete), one task for end-to-end verification. No Python changes needed — `cmd_report` and `cmd_status` already work correctly.

## Recommendation

**Two tasks:**
1. **Report overlay + status enhancement + autocomplete** — Build the report overlay using `Markdown` component, enhance status to read disk state, add `getArgumentCompletions` for subcommand tab-completion. All TypeScript, all in the extension.
2. **End-to-end verification** — Run the full flow: verify `pytest` still passes, verify extension structure is complete, confirm all subcommands route correctly, verify dashboard/report/interview/stop/status/shortcut/footer all present.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Markdown rendering in overlay | `Markdown` from `@gsd/pi-tui` + `getMarkdownTheme()` from `@gsd/pi-coding-agent` | Full markdown parser with code highlighting, tables, lists, headings — already themed |
| Report generation | `pi.exec("autoagent", ["report"])` → reads `.autoagent/report.md` from disk | One-shot exec, report lands on disk, overlay reads the file |
| Overlay with scroll + keyboard | Same `ui.custom()` + Component pattern from dashboard overlay (S01) | Proven pattern — render/handleInput/dispose lifecycle |
| Subcommand autocomplete | `getArgumentCompletions` on `registerCommand` (GSD commands.ts pattern) | Returns `AutocompleteItem[]` filtered by prefix |
| Disk state reading | `fs.readFileSync` on `.autoagent/state.json` and `.autoagent/config.json` | JSON files with known schemas, same as Python reads |

## Existing Code and Patterns

- `.pi/extensions/autoagent/index.ts` — Extension entry with `case "run"`, `case "stop"`, `case "status"`, `case "new"`. **Add `case "report"` and enhance `case "status"`. Add `getArgumentCompletions` to `registerCommand`.**
- `.pi/extensions/autoagent/dashboard-overlay.ts` — `AutoagentDashboardOverlay` class. **Model the report overlay identically: constructor(tui, theme, onClose), handleInput for scroll + close, render(width) wrapping Markdown output in a box.**
- `.pi/extensions/autoagent/subprocess-manager.ts` — Singleton with `stop()`, `status()`. **Already complete for S03 needs — no changes required.**
- `src/autoagent/cli.py` `cmd_report` — Runs `generate_report()`, writes `report.md` to `.autoagent/report.md`, prints summary to stdout. **No changes needed — extension calls this via exec and reads the file.**
- `src/autoagent/cli.py` `cmd_status` — Reads state + config from disk, prints formatted status. **No changes needed — extension reads the same JSON files directly.**
- `~/.gsd/agent/extensions/gsd/commands.ts` — `getArgumentCompletions` pattern returning `AutocompleteItem[]` filtered by `startsWith(prefix)`. **Clone this pattern.**
- `src/autoagent/state.py` — `ProjectState` (phase, current_iteration, best_iteration_id, total_cost_usd, started_at, updated_at) and `ProjectConfig` (goal, budget_usd). **Read JSON directly — these are the disk schemas.**

## Constraints

- `Markdown` component requires a `MarkdownTheme` — obtain via `getMarkdownTheme()` from `@gsd/pi-coding-agent`
- `pi.exec()` is available on `ExtensionAPI` (the `pi` parameter), not on `ExtensionCommandContext`. The command handler receives `ctx` (ExtensionCommandContext) but the `pi` reference is from the outer `default export function(pi)` scope — need to capture `pi` in module scope or use `child_process.execFileSync`/`execFile` directly.
- Report file lives at `.autoagent/report.md` relative to `process.cwd()` — must use `path.join(process.cwd(), ".autoagent", "report.md")`
- State file at `.autoagent/state.json`, config at `.autoagent/config.json` — both are JSON with known schemas
- `fs.readFileSync` is available (Node.js stdlib) — no async needed for small JSON/markdown files
- No Python changes — all work is TypeScript in the extension

## Common Pitfalls

- **`pi.exec()` accessibility** — The `pi` object is the `ExtensionAPI` parameter in the default export. If report generation needs `exec()`, either capture `pi` in a module-level variable or use `child_process.execFile` directly (simpler, avoids closure gymnastics). Given the interview runner already uses `spawn` directly, using `execFile` for report is consistent.
- **Report file missing** — If user hasn't run `autoagent report` yet, `.autoagent/report.md` won't exist. The extension must run the Python command first (generating the file), then read it. If `autoagent report` fails (no project, no archive), show the error from stderr/exit code.
- **Empty archive** — `autoagent report` on a fresh project with zero iterations produces a minimal report ("No iterations recorded"). The overlay should handle this gracefully — it will, since it just renders whatever markdown comes out.
- **Markdown component inside overlay box** — The dashboard overlay uses a custom `wrapInBox` method. The report overlay needs the same box border but delegates inner content to `Markdown.render(width)`. The `Markdown` component handles its own padding (paddingX/paddingY constructor args), so the overlay only needs to handle the box chrome and scroll offset.
- **State.json race during running optimization** — Reading state.json while the loop is writing is safe (Python uses atomic write via temp+rename), but the values may lag by one iteration. This is fine for status display.

## Open Risks

- **`Markdown` component rendering quality** — Haven't verified how the pi `Markdown` component handles the specific format of AutoAgent's `report.md` (which includes tables, code blocks, bullet lists, score trajectories). Risk is low — the component is battle-tested by pi's own assistant message rendering — but visual UAT will confirm.
- **`getMarkdownTheme()` availability in overlay factory** — The overlay factory receives `(tui, theme, keybindings, done)` where `theme` is the pi `Theme` object, not a `MarkdownTheme`. Need to call `getMarkdownTheme()` inside the factory or constructor. This function is a module-level export, should be callable anywhere.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Pi TUI extensions | (none) | no pi-specific skill exists — GSD extension source is the reference |
| TUI design | `hyperb1iss/hyperskills@tui-design` | available (111 installs) — generic, not needed for this low-risk slice |

No skill installation recommended — existing GSD extension patterns are sufficient.

## Sources

- `@gsd/pi-tui` Markdown component — `new Markdown(text, paddingX, paddingY, theme)` with `render(width): string[]` and `setText(text)` (source: `@gsd/pi-tui/dist/components/markdown.d.ts`)
- `@gsd/pi-coding-agent` getMarkdownTheme — `getMarkdownTheme(): MarkdownTheme` (source: `@gsd/pi-coding-agent/dist/modes/interactive/theme/theme.d.ts`)
- Extension API types — `ExtensionAPI.exec()`, `ExtensionCommandContext`, `ui.custom()` (source: `@gsd/pi-coding-agent/dist/core/extensions/types.d.ts`)
- GSD commands.ts — `getArgumentCompletions` pattern with prefix filtering (source: `~/.gsd/agent/extensions/gsd/commands.ts`)
- AutoAgent CLI — `cmd_report` writes `.autoagent/report.md`, `cmd_status` reads state.json + config.json (source: `src/autoagent/cli.py`)
- S01 forward intelligence — SubprocessManager singleton, overlay pattern, command routing via `args[0]` switch (source: S01-SUMMARY.md)
- S02 forward intelligence — `--project-dir` before subcommand, `case "new"` routing, interview runner standalone function (source: S02-SUMMARY.md)
