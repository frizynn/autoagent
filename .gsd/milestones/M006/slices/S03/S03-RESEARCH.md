# S03: Multi-Experiment + Dashboard — Research

**Date:** 2026-03-16

## Summary

S03 adds three capabilities to the extension: (1) a dashboard overlay toggled by Ctrl+Alt+A that reads `.autoagent/results.tsv` from disk and shows experiment progress, (2) multi-experiment awareness via git branch detection, and (3) a real stop command that calls `ctx.abort()`.

The implementation is straightforward — the GSD Dashboard overlay (`gsd-2/src/resources/extensions/gsd/dashboard-overlay.ts`) provides the exact pattern: a Component class with `render(width)`, `handleInput(data)`, `invalidate()`, `dispose()`, wired via `ctx.ui.custom<void>()` with `overlay: true` and a 2-second `setInterval` refresh. Results.tsv parsing is trivial (split by `\n`, split by `\t`). Git branch detection is a single `git branch --show-current` exec call.

All work is in one file (`index.ts`) plus a new dashboard component. The extension's `src/resources/` directory is excluded from tsconfig compilation — the pi SDK loads it at runtime.

## Recommendation

Follow the GSD Dashboard overlay pattern exactly. Create a `DashboardOverlay` class in a new `dashboard.ts` file alongside `index.ts`. Wire it via `ctx.ui.custom()` in both the Ctrl+Alt+A shortcut handler and a potential `/autoagent status` alias. For stop, use `ctx.abort()` which is already available on ExtensionContext. For git branch detection, use `execSync('git branch --show-current')` (same as the extension already uses `readFileSync` for disk reads).

Build the dashboard first — it's the riskiest piece (component rendering, TSV parsing, scroll handling). Stop is trivial (one-liner). Multi-experiment awareness is just adding git branch info to the dashboard and session_start.

## Implementation Landscape

### Key Files

- `tui/src/resources/extensions/autoagent/index.ts` — Current extension entry point. Has the Ctrl+Alt+A placeholder shortcut, the no-op stop command, and session_start. All three need updates.
- `tui/src/resources/extensions/autoagent/dashboard.ts` — NEW. Dashboard overlay component. Follows the GSD Dashboard pattern from `gsd-2/src/resources/extensions/gsd/dashboard-overlay.ts`.
- `tui/src/resources/extensions/autoagent/prompts/program.md` — Already defines results.tsv format (`commit\tscore\tstatus\tdescription`) and git branch protocol (`autoagent/run-<date>`). No changes needed.
- `tui/src/resources/extensions/autoagent/prompts/system.md` — Already has MODE A/B. No changes needed.

### Pattern to Follow (GSD Dashboard)

The GSD Dashboard overlay at `gsd-2/src/resources/extensions/gsd/dashboard-overlay.ts` is the authoritative pattern. Key elements:

1. **Class structure**: `GSDDashboardOverlay implements Component` with:
   - `constructor(tui, theme, onClose)` — stores refs, starts refresh timer
   - `render(width): string[]` — renders content with scroll, wraps in box
   - `handleInput(data)` — handles escape/scroll keys, calls `onClose()`
   - `invalidate()` — clears render cache
   - `dispose()` — clears refresh timer

2. **Refresh via setInterval**: 2-second poll interval. Reads disk state, calls `invalidate()` + `tui.requestRender()`.

3. **Wiring via ctx.ui.custom()**:
   ```typescript
   await ctx.ui.custom<void>(
     (tui, theme, _kb, done) => {
       return new DashboardOverlay(tui, theme, () => done());
     },
     {
       overlay: true,
       overlayOptions: {
         width: "80%",
         minWidth: 60,
         maxHeight: "80%",
         anchor: "center",
       },
     },
   );
   ```

4. **Box rendering**: `wrapInBox()` draws `╭─╮ │ │ ╰─╯` borders using `theme.fg("borderAccent", ...)`.

5. **Scroll**: `scrollOffset` integer, arrow/j/k keys, g/G for top/end. Content sliced by viewport height.

### Imports from Pi SDK

From the existing extension and GSD dashboard examples:
- `import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "@gsd/pi-coding-agent"` — already used
- `import { Key, matchesKey, truncateToWidth, visibleWidth } from "@gsd/pi-tui"` — Key already imported, add matchesKey/truncateToWidth/visibleWidth
- `import type { Theme } from "@gsd/pi-coding-agent"` — for theming (GSD dashboard imports this)

### Dashboard Content

The dashboard reads `.autoagent/results.tsv` and shows:
- **Header**: "AutoAgent Dashboard" + current git branch name + running/idle status
- **Score summary**: best score, latest score, total iterations, keeps/discards/crashes
- **Results table**: last N rows from results.tsv showing commit, score, status, description
- **Footer**: keyboard hints (scroll, close)

### Results.tsv Parsing

Format from program.md:
```
commit	score	status	description
a1b2c3d	0.7500	keep	Added prompt caching
f4e5d6c	0.7200	discard	Tried chain-of-thought
```

Parse: `readFileSync(path, 'utf-8').split('\n').filter(line => line.trim() && !line.startsWith('commit')).map(line => line.split('\t'))`

### Stop Command

Replace the no-op with:
```typescript
case "stop": {
  if (ctx.isIdle()) {
    ctx.ui.notify("Nothing running to stop.", "info");
  } else {
    ctx.abort();
    ctx.ui.notify("⚡ Experiment loop stopped.", "info");
  }
  return;
}
```

`ctx.abort()` and `ctx.isIdle()` are available on `ExtensionContext` (confirmed in types.d.ts).

### Git Branch Detection

```typescript
import { execSync } from "node:child_process";

function getCurrentBranch(): string | null {
  try {
    return execSync("git branch --show-current", { encoding: "utf-8", cwd: process.cwd() }).trim() || null;
  } catch { return null; }
}
```

For listing experiment branches:
```typescript
function getExperimentBranches(): string[] {
  try {
    const output = execSync("git branch --list 'autoagent/*'", { encoding: "utf-8", cwd: process.cwd() });
    return output.split('\n').map(b => b.trim().replace(/^\* /, '')).filter(Boolean);
  } catch { return []; }
}
```

### Session Start Enhancement

Update `session_start` to show the current git branch if it's an `autoagent/*` branch, and count experiments from results.tsv on that branch.

### Build Order

1. **Dashboard overlay component** (`dashboard.ts`) — the riskiest piece. Prove: renders results.tsv data in a boxed overlay, handles scroll and close, refreshes on timer. This unblocks the shortcut wiring.
2. **Wire dashboard + stop in index.ts** — Connect Ctrl+Alt+A to the dashboard, wire stop to `ctx.abort()`, enhance session_start with branch info. Low risk — straight wiring.

### Verification Approach

1. **File structure**: `dashboard.ts` exists alongside `index.ts`
2. **Dashboard class**: exports a class with `render(width): string[]`, `handleInput(data)`, `invalidate()`, `dispose()`
3. **TSV parsing**: dashboard reads `.autoagent/results.tsv` and extracts rows
4. **Stop command**: `index.ts` stop case calls `ctx.abort()` when not idle
5. **Shortcut wiring**: Ctrl+Alt+A handler creates dashboard via `ctx.ui.custom()` with `overlay: true`
6. **Git branch**: dashboard shows current branch name from `git branch --show-current`
7. **Session start**: shows branch info for `autoagent/*` branches
8. **tsc --noEmit**: passes (though extension is excluded from compilation, this confirms the rest of the TUI isn't broken)

Verification script checks:
- `grep -q "ctx.abort()" index.ts` — stop is wired
- `grep -q "overlay: true" index.ts` — dashboard is wired as overlay
- `grep -q "results.tsv" dashboard.ts` — dashboard reads results
- `grep -q "git branch" dashboard.ts` or `index.ts` — branch detection present
- `grep -q "handleInput" dashboard.ts` — scroll/close handling exists
- `grep -q "setInterval\|refreshTimer" dashboard.ts` — polling refresh exists

## Constraints

- Extension `src/resources/` is excluded from tsconfig compilation — no build-time type checking. Runtime errors only surface when pi loads the extension.
- The dashboard must import from `@gsd/pi-coding-agent` and `@gsd/pi-tui` which are only available at pi runtime, not in this project's node_modules.
- `readFileSync` is used for disk reads (established pattern from D082) — no async file watching needed.
- results.tsv may not exist yet (no experiments run) — dashboard must handle empty/missing file gracefully.

## Common Pitfalls

- **Missing results.tsv** — Dashboard must not crash when the file doesn't exist. Wrap reads in try/catch and show "No experiments yet" state.
- **Tab characters in description field** — The description column could theoretically contain tabs. Use `split('\t', 4)` to limit splitting to 4 columns, keeping the rest as description.
- **Git not available** — `execSync('git ...')` will throw if git isn't installed. Wrap in try/catch and show "unknown" for branch.
- **Overlay dispose cleanup** — Must clear the refresh `setInterval` in `dispose()`. The GSD dashboard does this correctly — follow the same pattern.
