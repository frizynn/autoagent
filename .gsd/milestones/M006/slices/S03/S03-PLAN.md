# S03: Multi-Experiment + Dashboard

**Goal:** Each experiment on its own git branch, dashboard overlay reads results.tsv and shows iteration progress with scores and decisions, stop command interrupts the running loop.
**Demo:** Press Ctrl+Alt+A → dashboard overlay appears showing current branch, score summary, results table from results.tsv. `/autoagent stop` calls ctx.abort() when the agent is running. session_start shows branch info for autoagent/* branches.

## Must-Haves

- Dashboard overlay component with render/handleInput/invalidate/dispose lifecycle
- Dashboard reads `.autoagent/results.tsv` and parses tab-separated rows (commit, score, status, description)
- Dashboard shows: header with git branch name, score summary (best/latest/count/keeps/discards), results table, keyboard hints
- Dashboard handles missing results.tsv gracefully (shows "No experiments yet")
- 2-second refresh timer reads disk state and calls invalidate + requestRender
- Scroll support (↑↓/j/k, g/G for top/end) and Escape to close
- Ctrl+Alt+A shortcut opens dashboard via `ctx.ui.custom()` with `overlay: true`
- `/autoagent stop` calls `ctx.abort()` when not idle, shows "Nothing running" when idle
- session_start shows current git branch name for `autoagent/*` branches
- Git branch detection via `execSync('git branch --show-current')` with try/catch fallback

## Proof Level

- This slice proves: integration
- Real runtime required: yes (overlay renders in pi TUI, ctx.abort() requires agent session)
- Human/UAT required: yes (dashboard usability, visual rendering quality)

## Verification

```bash
cd tui/src/resources/extensions/autoagent

# Dashboard component exists and has required structure
grep -q "class.*Dashboard" dashboard.ts
grep -q "render.*width.*string\[\]" dashboard.ts
grep -q "handleInput" dashboard.ts
grep -q "invalidate" dashboard.ts
grep -q "dispose" dashboard.ts

# Dashboard reads results.tsv
grep -q "results.tsv" dashboard.ts

# Dashboard has refresh timer
grep -q "setInterval\|refreshTimer" dashboard.ts

# Dashboard has scroll handling
grep -q "scrollOffset" dashboard.ts

# Dashboard has git branch detection
grep -q "git branch" dashboard.ts

# Dashboard exports the class
grep -q "export" dashboard.ts

# Stop command wired to ctx.abort()
grep -q "ctx.abort()" index.ts

# Stop checks idle state
grep -q "isIdle" index.ts

# Dashboard wired as overlay
grep -q "overlay.*true" index.ts

# Ctrl+Alt+A opens dashboard (not placeholder)
grep -q "dashboard\|Dashboard" index.ts

# Session start has branch detection
grep -q "git branch\|getCurrentBranch\|autoagent/" index.ts

# Diagnostic: dashboard handles missing results.tsv gracefully (failure path)
grep -q "No experiments yet\|No results file" dashboard.ts

# Diagnostic: stop on idle shows user-visible feedback
grep -q "Nothing running" index.ts
```

## Observability / Diagnostics

- Runtime signals: session_start notification shows branch name and experiment count; dashboard refresh timer reads disk every 2s
- Inspection surfaces: Ctrl+Alt+A opens dashboard overlay; session_start banner on TUI launch
- Failure visibility: missing results.tsv shows "No experiments yet" in dashboard; git errors show "unknown" for branch; stop on idle shows "Nothing running"
- Redaction constraints: none

## Integration Closure

- Upstream surfaces consumed: `program.md` (results.tsv format, git branch protocol), `index.ts` (existing extension with go/stop/session_start/shortcut)
- New wiring introduced in this slice: dashboard.ts imported into index.ts; Ctrl+Alt+A handler creates overlay; stop wired to ctx.abort(); session_start enhanced with branch info
- What remains before the milestone is truly usable end-to-end: nothing — this is the final slice

## Tasks

- [x] **T01: Build dashboard overlay component** `est:45m`
  - Why: The dashboard is the riskiest piece — component rendering, TSV parsing, scroll handling, refresh timer. Must follow the GSD Dashboard overlay pattern exactly (class with render/handleInput/invalidate/dispose, setInterval refresh, wrapInBox borders).
  - Files: `tui/src/resources/extensions/autoagent/dashboard.ts`
  - Do: Create DashboardOverlay class following GSD Dashboard pattern. Constructor takes (tui, theme, onClose), starts 2s refresh timer. render(width) builds content lines: header with branch name + running/idle status, score summary (best score, latest score, total iterations, keeps/discards/crashes), results table from last N rows, footer with keyboard hints. Wrap in box with `╭─╮ │ │ ╰─╯` borders using theme.fg("borderAccent"). handleInput handles Escape/scroll keys (↑↓/j/k, g/G). TSV parsing: readFileSync `.autoagent/results.tsv`, split lines, skip header, split('\t', 4) for each row. Git branch via execSync('git branch --show-current'). Handle missing file with try/catch → "No experiments yet". Import from @gsd/pi-coding-agent (Theme) and @gsd/pi-tui (truncateToWidth, visibleWidth, matchesKey, Key).
  - Verify: `grep -q "class.*Dashboard" tui/src/resources/extensions/autoagent/dashboard.ts && grep -q "results.tsv" tui/src/resources/extensions/autoagent/dashboard.ts && grep -q "handleInput" tui/src/resources/extensions/autoagent/dashboard.ts && grep -q "setInterval" tui/src/resources/extensions/autoagent/dashboard.ts`
  - Done when: dashboard.ts exports a class with render/handleInput/invalidate/dispose, reads results.tsv, detects git branch, handles empty state, has scroll support and 2s refresh timer

- [ ] **T02: Wire dashboard, stop, and branch info into index.ts** `est:30m`
  - Why: Connects the dashboard component to the shortcut and wires the real stop command. Also enhances session_start with git branch awareness. Completes all S03 integration.
  - Files: `tui/src/resources/extensions/autoagent/index.ts`
  - Do: (1) Import DashboardOverlay from ./dashboard.js. (2) Replace Ctrl+Alt+A placeholder handler with: `await ctx.ui.custom<void>((tui, theme, _kb, done) => new DashboardOverlay(tui, theme, () => done()), { overlay: true, overlayOptions: { width: "80%", minWidth: 60, maxHeight: "80%", anchor: "center" } })`. (3) Replace stop case with: check ctx.isIdle(), if idle show "Nothing running" notification, else call ctx.abort() and show "Experiment loop stopped" notification. (4) Add getCurrentBranch() helper using execSync('git branch --show-current') with try/catch. (5) Enhance session_start: if current branch starts with "autoagent/", include branch name in status line. (6) Add execSync import from node:child_process.
  - Verify: `grep -q "ctx.abort()" tui/src/resources/extensions/autoagent/index.ts && grep -q "overlay.*true" tui/src/resources/extensions/autoagent/index.ts && grep -q "isIdle" tui/src/resources/extensions/autoagent/index.ts && grep -q "git branch" tui/src/resources/extensions/autoagent/index.ts`
  - Done when: Ctrl+Alt+A opens dashboard overlay, stop calls ctx.abort() when not idle, session_start shows branch name for autoagent/* branches

## Files Likely Touched

- `tui/src/resources/extensions/autoagent/dashboard.ts` (NEW)
- `tui/src/resources/extensions/autoagent/index.ts` (MODIFIED)
