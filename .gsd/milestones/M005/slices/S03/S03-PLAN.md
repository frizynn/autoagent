# S03: Report, Status, Stop, and Final Assembly

**Goal:** Complete the `/autoagent` experience in pi — report overlay, enhanced status, subcommand autocomplete — and verify the full milestone hangs together.
**Demo:** User runs `/autoagent report` and sees a scrollable markdown report overlay; `/autoagent status` shows disk state when idle; tab-completing `/autoagent ` shows all subcommands.

## Must-Haves

- `/autoagent report` runs `autoagent report` via `execFile`, reads `.autoagent/report.md`, renders in a scrollable `Markdown` overlay
- `/autoagent status` reads `.autoagent/state.json` and `.autoagent/config.json` for disk-based status when subprocess is idle
- `getArgumentCompletions` returns filtered subcommand list (run, stop, status, new, report)
- Report overlay handles missing report file gracefully (runs generation first, shows error if that fails)
- All existing pytest tests still pass (479+)
- Extension has all 7 expected files (6 existing + 1 new report-overlay.ts)

## Proof Level

- This slice proves: final-assembly
- Real runtime required: no (extension structure + pytest; visual UAT deferred to interactive pi session)
- Human/UAT required: yes (visual confirmation of overlay rendering deferred)

## Verification

- `pytest tests/ -q` — 479+ tests pass, no regressions
- Extension structure audit: all expected files exist with correct exports
- TypeScript compilation check: `npx tsc --noEmit` on extension files (or manual review of import resolution)
- Report overlay class exports `AutoagentReportOverlay` with `render()`, `handleInput()`, `dispose()`
- `case "report"` exists in index.ts command handler switch
- `getArgumentCompletions` function exists on registerCommand options

## Integration Closure

- Upstream surfaces consumed: `dashboard-overlay.ts` pattern (box, scroll, handleInput), `subprocess-manager.ts` (status), `types.ts` (SubprocessState), GSD `getArgumentCompletions` pattern
- New wiring introduced in this slice: `report-overlay.ts` component, `case "report"` command routing, `getArgumentCompletions` on registerCommand, disk state reading in `case "status"`
- What remains before the milestone is truly usable end-to-end: visual UAT in interactive pi session (deferred — requires human)

## Observability / Diagnostics

- **Report generation errors surfaced to user:** When `autoagent report` fails (exit code non-zero, missing project, no archive), the error message from stderr is shown via `ctx.ui.notify` — the user sees why it failed, not a silent no-op.
- **Disk state in status:** `/autoagent status` when idle reads `state.json` and `config.json` and displays phase, iteration count, best score, total cost, and goal. If files are missing, shows "No AutoAgent project found in <cwd>" — tells the agent/user where to look.
- **Structured failure in report overlay:** If the report file is empty or unreadable after generation, the overlay shows an error notification rather than opening a blank overlay.
- **Redaction:** No secrets flow through these surfaces — report.md is user-generated content, state.json contains only phase/iteration/cost metadata.

## Verification (Failure-Path Check)

- `case "report"` in index.ts contains error handling for both `execFile` failure and missing report file (grep for `notify.*error\|warning`)
- `case "status"` handles missing state.json gracefully (grep for `No AutoAgent project\|ENOENT\|existsSync`)

## Tasks

- [x] **T01: Build report overlay, enhance status, add autocomplete** `est:35m`
  - Why: Delivers the three remaining extension features — report viewing, richer status, tab completion
  - Files: `.pi/extensions/autoagent/report-overlay.ts`, `.pi/extensions/autoagent/index.ts`
  - Do: Create `report-overlay.ts` using `Markdown` component inside box chrome (same pattern as dashboard overlay). In `index.ts`: add `case "report"` that spawns `autoagent report` via `execFile`, reads `.autoagent/report.md`, opens overlay. Enhance `case "status"` to read `state.json`/`config.json` when subprocess is idle. Add `getArgumentCompletions` to `registerCommand` options returning filtered subcommand list.
  - Verify: All files exist with correct exports. `pytest tests/ -q` passes 479+. Report overlay has render/handleInput/dispose methods. Index.ts handles all 5 subcommands (run/stop/status/new/report).
  - Done when: Extension is structurally complete with all subcommands routed, report overlay renders markdown, status reads disk state, and autocomplete returns subcommand suggestions.

- [x] **T02: End-to-end structural verification and milestone audit** `est:15m`
  - Why: Final assembly proof — confirms the full milestone deliverable is structurally sound before declaring done
  - Files: `.gsd/milestones/M005/slices/S03/S03-UAT.md`
  - Do: Run pytest full suite. Audit extension file structure (7 files, correct imports, no missing modules). Verify all 6 success criteria from M005 roadmap are structurally met. Verify command routing covers all subcommands. Check footer status, shortcut registration, overlay lifecycle. Write S03-UAT.md documenting verification results.
  - Verify: `pytest tests/ -q` passes 479+. All extension files present and import-consistent. UAT document written with pass/fail for each milestone criterion.
  - Done when: All structural checks pass and UAT document confirms milestone readiness (visual UAT noted as deferred).

## Files Likely Touched

- `.pi/extensions/autoagent/report-overlay.ts` (new)
- `.pi/extensions/autoagent/index.ts` (modified — report case, status enhancement, autocomplete)
- `.gsd/milestones/M005/slices/S03/S03-UAT.md` (new)
