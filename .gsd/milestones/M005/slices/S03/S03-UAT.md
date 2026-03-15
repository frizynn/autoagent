# S03: Report, Status, Stop, and Final Assembly — UAT

**Milestone:** M005
**Written:** 2026-03-14

## UAT Type

- UAT mode: mixed (artifact-driven structural checks + deferred live-runtime visual checks)
- Why this mode is sufficient: Extension code is TypeScript that only runs inside pi's jiti loader — structural verification confirms all wiring, exports, and error paths. Visual rendering requires an interactive pi session.

## Preconditions

- Python test suite passes: `pytest tests/ -q` → 496+ passed
- All 7 extension files exist in `.pi/extensions/autoagent/`
- An AutoAgent project exists in the working directory (`.autoagent/` with config.json, state.json, archive/)
- pi is running with the project-local extension loaded

## Smoke Test

Run `/autoagent status` in pi. Should display project state (goal, phase, iterations, cost) or "No AutoAgent project found" — either confirms the extension loaded and the status command routes correctly.

## Test Cases

### 1. Report overlay displays generated report

1. Ensure `.autoagent/` project directory exists with at least one completed iteration
2. Run `/autoagent report` in pi
3. Wait for report generation (execFile runs `autoagent report`)
4. **Expected:** Scrollable overlay opens with title "AutoAgent Report", showing markdown content from `.autoagent/report.md` — score trajectory, top architectures, cost breakdown, recommendations sections visible
5. Press `q` or `Escape`
6. **Expected:** Overlay closes, returns to normal pi view

### 2. Report overlay handles missing project

1. Navigate to a directory with no `.autoagent/` folder
2. Run `/autoagent report` in pi
3. **Expected:** Error notification appears (not a blank overlay) — message includes stderr from `autoagent report` (e.g., "Not an AutoAgent project")

### 3. Idle status reads disk state

1. Ensure `.autoagent/state.json` and `.autoagent/config.json` exist from a previous run
2. No optimization subprocess running
3. Run `/autoagent status` in pi
4. **Expected:** Output shows goal, phase, iteration count, best score, and total cost read from disk files

### 4. Status handles missing state files

1. Navigate to a directory with no `.autoagent/` folder
2. Run `/autoagent status` in pi
3. **Expected:** Message "No AutoAgent project found in <cwd>" (not a crash or empty output)

### 5. Tab completion returns subcommands

1. Type `/autoagent ` (with trailing space) and trigger tab completion
2. **Expected:** Completion list shows: run, stop, status, new, report
3. Type `/autoagent r` and trigger tab completion
4. **Expected:** Filtered list shows: run, report

### 6. Run subcommand budget flag completion

1. Type `/autoagent run --` and trigger tab completion
2. **Expected:** Completion includes `--budget`

### 7. Full command routing (all 5 subcommands)

1. Verify `case "run"` spawns subprocess and opens dashboard overlay
2. Verify `case "stop"` calls SubprocessManager.stop()
3. Verify `case "status"` reads disk state when idle, shows subprocess state when running
4. Verify `case "new"` calls runInterview()
5. Verify `case "report"` runs execFile and opens report overlay
6. **Expected:** All 5 subcommands route to their handlers without falling through to default case

## Edge Cases

### Report generation fails (non-zero exit)

1. Simulate `autoagent report` failing (e.g., corrupt state, missing archive)
2. Run `/autoagent report` in pi
3. **Expected:** Error notification with stderr content shown via `ctx.ui.notify` — overlay does NOT open

### Report file empty after generation

1. `autoagent report` succeeds but `.autoagent/report.md` is empty
2. **Expected:** Error notification "Report file is empty" — blank overlay does NOT open

### Status with state.json but no config.json

1. `.autoagent/state.json` exists, `config.json` missing
2. Run `/autoagent status`
3. **Expected:** Shows available state data, handles missing config gracefully (no crash)

### Stop when no subprocess running

1. No optimization running
2. Run `/autoagent stop`
3. **Expected:** Informational message (not running), no crash

## Failure Signals

- Any subcommand crashes pi or shows an unhandled exception
- Report overlay opens blank (no content)
- Status shows nothing when `.autoagent/` files exist
- Tab completion returns empty or wrong list
- Footer widget doesn't update after run/stop commands

## Requirements Proved By This UAT

- R006 — CLI extends into pi TUI: all 5 subcommands accessible as `/autoagent <sub>` with tab completion
- R019 — Fire-and-forget: report overlay lets user check results later without disrupting workflow
- R017 — Budget visibility: status command shows cost from disk state

## Not Proven By This UAT

- Visual rendering quality of overlays (requires interactive pi session)
- Scroll behavior in report overlay with long content
- Footer widget appearance and real-time updates during optimization
- Ctrl+Alt+A shortcut toggle behavior (structurally present but not visually verified)
- Live dashboard updating from real Python subprocess (verified in S01, not re-verified here)

## Notes for Tester

- Visual UAT is deferred — this slice was verified structurally. First interactive pi session should walk through all test cases above.
- The report overlay depends on `autoagent` being on PATH. If using a virtualenv, ensure it's activated before pi.
- TypeScript compilation wasn't checked (no tsconfig.json in extension dir) — import consistency was verified by grep audit.
