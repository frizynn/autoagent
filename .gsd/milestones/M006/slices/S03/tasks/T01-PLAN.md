---
estimated_steps: 6
estimated_files: 1
---

# T01: Build dashboard overlay component

**Slice:** S03 — Multi-Experiment + Dashboard
**Milestone:** M006

## Description

Create the `DashboardOverlay` class in a new `dashboard.ts` file. This is the riskiest piece of S03 — it handles component rendering, TSV parsing, scroll, and a 2-second refresh timer. It follows the GSD Dashboard overlay pattern exactly: a class with `render(width): string[]`, `handleInput(data)`, `invalidate()`, `dispose()`.

The dashboard reads `.autoagent/results.tsv` from disk, parses tab-separated rows, shows score summaries and a results table, displays the current git branch name, and handles the case where no results exist yet.

## Steps

1. Create `tui/src/resources/extensions/autoagent/dashboard.ts` with the `DashboardOverlay` class.
2. Implement the constructor taking `(tui: { requestRender: () => void }, theme: Theme, onClose: () => void)`. Store refs, initialize `scrollOffset = 0`, start a `setInterval` refresh timer at 2000ms that reads disk state, calls `invalidate()` + `tui.requestRender()`.
3. Implement helper functions:
   - `getCurrentBranch(): string | null` — runs `execSync("git branch --show-current", { encoding: "utf-8", cwd: process.cwd() }).trim()` in try/catch, returns null on failure.
   - `getExperimentBranches(): string[]` — runs `execSync("git branch --list 'autoagent/*'", { encoding: "utf-8", cwd: process.cwd() })`, splits lines, trims, filters empty.
   - `parseResultsTsv(projectDir: string): { rows: Array<{ commit: string, score: string, status: string, description: string }>, error: string | null }` — reads `.autoagent/results.tsv` via `readFileSync`, splits by `\n`, filters out empty lines and header line (starts with "commit"), splits each line with `split('\t', 4)`. Returns `{ rows: [], error: "No results file" }` if file doesn't exist.
4. Implement `render(width): string[]`:
   - Build content lines inside `buildContentLines(width)`:
     - **Header**: "AutoAgent Dashboard" (themed accent) + current git branch name (or "no branch") + idle/running status hint
     - **Score summary**: if rows exist, compute best score (`Math.max`), latest score, total iterations, count of keeps/discards/crashes from status column. Show as a compact summary block.
     - **Experiment branches**: list `autoagent/*` branches if multiple exist.
     - **Results table**: show last 20 rows from results.tsv in reverse chronological order (newest first). Each row: `commit_short  score  status  description` truncated to width.
     - **Footer**: `"↑↓ scroll · g/G top/end · esc close"` centered and dimmed.
   - Apply scroll: compute viewport height from `process.stdout.rows`, slice content by `scrollOffset`.
   - Wrap in box using `wrapInBox()` — draws `╭─╮ │ │ ╰─╯` borders using `theme.fg("borderAccent", ...)`.
   - Cache result in `cachedLines`/`cachedWidth`, return cache on matching width.
5. Implement `handleInput(data)`:
   - Escape or Ctrl+C: clear timer, call `onClose()`.
   - Down arrow or "j": increment `scrollOffset`, invalidate + requestRender.
   - Up arrow or "k": decrement `scrollOffset` (min 0), invalidate + requestRender.
   - "g": scroll to top (offset 0), invalidate + requestRender.
   - "G": scroll to end (offset 999, clamped in render), invalidate + requestRender.
   - Use `matchesKey(data, Key.escape)`, `matchesKey(data, Key.down)`, etc. from `@gsd/pi-tui`.
6. Implement `invalidate()` (clear cachedWidth/cachedLines) and `dispose()` (clearInterval on refresh timer). Export the class.

## Must-Haves

- [ ] Class exports with render(width): string[], handleInput(data), invalidate(), dispose()
- [ ] Reads `.autoagent/results.tsv` with readFileSync, parses tab-separated rows with split('\t', 4)
- [ ] Handles missing results.tsv gracefully — shows "No experiments yet" instead of crashing
- [ ] Shows git branch name from `execSync('git branch --show-current')`
- [ ] Score summary: best score, latest score, total iterations, keeps/discards/crashes
- [ ] Scroll support with ↑↓/j/k and g/G for top/end
- [ ] 2-second setInterval refresh timer, cleared in dispose()
- [ ] Box rendering with ╭─╮│╰─╯ borders via theme.fg("borderAccent")

## Verification

```bash
FILE="tui/src/resources/extensions/autoagent/dashboard.ts"
test -f "$FILE" || (echo "FAIL: dashboard.ts missing" && exit 1)
grep -q "export.*class.*Dashboard" "$FILE" || (echo "FAIL: no exported class" && exit 1)
grep -q "render.*width.*string\[\]" "$FILE" || (echo "FAIL: no render method" && exit 1)
grep -q "handleInput" "$FILE" || (echo "FAIL: no handleInput" && exit 1)
grep -q "invalidate" "$FILE" || (echo "FAIL: no invalidate" && exit 1)
grep -q "dispose" "$FILE" || (echo "FAIL: no dispose" && exit 1)
grep -q "results\.tsv" "$FILE" || (echo "FAIL: no results.tsv reading" && exit 1)
grep -q "setInterval" "$FILE" || (echo "FAIL: no refresh timer" && exit 1)
grep -q "scrollOffset" "$FILE" || (echo "FAIL: no scroll" && exit 1)
grep -q "git branch" "$FILE" || (echo "FAIL: no git branch detection" && exit 1)
grep -q "borderAccent" "$FILE" || (echo "FAIL: no box borders" && exit 1)
echo "ALL PASS"
```

## Inputs

- GSD Dashboard overlay pattern — the authoritative reference is `gsd-2/src/resources/extensions/gsd/dashboard-overlay.ts`. Key elements: class structure (constructor with tui/theme/onClose, render/handleInput/invalidate/dispose), setInterval refresh, wrapInBox borders, scroll offset handling, cache invalidation.
- results.tsv format from `program.md`: header `commit\tscore\tstatus\tdescription`, data rows are tab-separated with those 4 columns.
- Imports: `import type { Theme } from "@gsd/pi-coding-agent"` and `import { Key, matchesKey, truncateToWidth, visibleWidth } from "@gsd/pi-tui"` — these are available at pi runtime, not in this project's node_modules.
- `readFileSync`, `existsSync` from `node:fs`; `join` from `node:path`; `execSync` from `node:child_process`.

## Expected Output

- `tui/src/resources/extensions/autoagent/dashboard.ts` — new file exporting `DashboardOverlay` class with full component lifecycle, TSV parsing, git branch detection, scroll handling, and themed box rendering.
