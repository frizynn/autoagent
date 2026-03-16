# S03: Multi-Experiment + Dashboard — UAT

**Milestone:** M006
**Written:** 2026-03-16

## UAT Type

- UAT mode: mixed (artifact-driven + live-runtime)
- Why this mode is sufficient: Dashboard rendering and stop command require live TUI to verify visual output and ctx.abort() behavior. Artifact checks confirm code structure and wiring are correct.

## Preconditions

- Pi TUI builds and launches cleanly (`tsc` compiles without errors in the tui directory)
- Working git repository (git initialized, can run `git branch`)
- No active experiment running (clean state for testing)

## Smoke Test

Press Ctrl+Alt+A in a running pi session with the autoagent extension loaded. A centered overlay should appear with "AutoAgent Dashboard" header, "No experiments yet" message (if no .autoagent/results.tsv), and keyboard hints at the bottom. Press Escape to close.

## Test Cases

### 1. Dashboard opens and closes via Ctrl+Alt+A

1. Launch pi in a directory without `.autoagent/`
2. Press Ctrl+Alt+A
3. **Expected:** Overlay appears centered (80% width) with box borders, "AutoAgent Dashboard" header, "No experiments yet — use /autoagent go to start" message, and "↑↓ scroll · g/G top/end · esc close" footer
4. Press Escape
5. **Expected:** Overlay closes, returns to normal pi session
6. Press Ctrl+Alt+A again, then press Ctrl+Alt+A while overlay is open
7. **Expected:** Overlay closes (toggle behavior)

### 2. Dashboard shows score summary from results.tsv

1. Create `.autoagent/` directory in the project
2. Create `.autoagent/results.tsv` with content:
   ```
   commit	score	status	description
   abc1234	0.7500	keep	initial baseline
   def5678	0.6200	discard	tried adding cache
   ghi9012	0.8100	keep	optimized prompt
   jkl3456	0.0000	crash	syntax error in pipeline
   ```
3. Press Ctrl+Alt+A
4. **Expected:** Score summary shows: Best: 0.81, Latest: 0, Iterations: 4, Keeps: 2, Discards: 1, Crashes: 1
5. Results table shows all 4 rows in reverse order (newest first): jkl3456, ghi9012, def5678, abc1234
6. Status colors: "keep" in green/success, "discard" in yellow/warning, "crash" in red/error

### 3. Dashboard auto-refreshes from disk

1. Open dashboard with Ctrl+Alt+A (results.tsv has 4 rows from test 2)
2. In a separate terminal, append a new line to `.autoagent/results.tsv`:
   ```
   mno7890	0.8500	keep	better prompt template
   ```
3. Wait 2-3 seconds
4. **Expected:** Dashboard updates without user interaction — score summary now shows Best: 0.85, Iterations: 5, Keeps: 3. New row appears at top of results table.

### 4. Dashboard scroll support

1. Create `.autoagent/results.tsv` with 25+ rows (enough to exceed viewport)
2. Press Ctrl+Alt+A
3. Press ↓ or j multiple times
4. **Expected:** Content scrolls down, showing later rows
5. Press G
6. **Expected:** Jumps to end of content
7. Press g
8. **Expected:** Jumps back to top
9. Press ↑ or k
10. **Expected:** Scrolls up one line

### 5. Dashboard shows git branch info

1. Create and checkout a branch: `git checkout -b autoagent/test-experiment`
2. Press Ctrl+Alt+A
3. **Expected:** Header shows branch name "autoagent/test-experiment" in warning/highlight color
4. Switch back: `git checkout main`
5. Reopen dashboard
6. **Expected:** Header shows "main" in dim color (not an experiment branch)

### 6. Dashboard lists experiment branches

1. Create branches: `git branch autoagent/exp-1` and `git branch autoagent/exp-2`
2. Checkout `autoagent/exp-1`
3. Press Ctrl+Alt+A
4. **Expected:** "Experiment Branches" section lists both branches. Current branch (autoagent/exp-1) has ▸ icon in accent color. Other branch (autoagent/exp-2) has ○ icon in dim color.

### 7. Stop command when idle

1. Ensure no agent is running (session is idle)
2. Type `/autoagent stop`
3. **Expected:** Notification appears: "Nothing running to stop."

### 8. Stop command when agent is running

1. Run `/autoagent go` (with valid .autoagent/pipeline.py and prepare.py in place)
2. While agent is processing, type `/autoagent stop`
3. **Expected:** Notification appears: "⚡ Experiment loop stopped." and the agent's current turn is aborted

### 9. Session start shows branch info

1. Checkout `autoagent/my-experiment` branch
2. Start a new pi session
3. **Expected:** Session start notification includes `· branch: autoagent/my-experiment` in the status line, plus `Ctrl+Alt+A dashboard` hint

### 10. Session start on non-experiment branch

1. Checkout `main` branch
2. Start a new pi session
3. **Expected:** Session start notification does NOT include branch info (no `· branch:` text). Still shows project status and dashboard hint.

## Edge Cases

### Missing git repository

1. Open pi in a directory that is not a git repository
2. Press Ctrl+Alt+A
3. **Expected:** Dashboard shows "no branch" in dim color. No crash, no error notification. Experiment branches section omitted.

### Empty results.tsv (header only)

1. Create `.autoagent/results.tsv` with only the header line: `commit	score	status	description`
2. Press Ctrl+Alt+A
3. **Expected:** Dashboard shows "No experiments yet" — header row is skipped, zero data rows parsed

### Malformed results.tsv rows

1. Create `.autoagent/results.tsv` with a row that has fewer than 4 tab-separated columns
2. Press Ctrl+Alt+A
3. **Expected:** Malformed row is silently skipped. Valid rows still display correctly.

### Non-numeric scores

1. Create a results.tsv row with `abc1234	N/A	crash	failed to evaluate`
2. Press Ctrl+Alt+A
3. **Expected:** Score summary treats non-numeric scores as NaN — best/latest calculations exclude them. Row still appears in the results table.

## Failure Signals

- Ctrl+Alt+A does nothing or crashes the TUI — shortcut wiring broken
- Dashboard shows stale data after 5+ seconds — refresh timer not working
- "Nothing running" appears when agent is actively running — isIdle() check inverted
- Stop doesn't actually stop the agent — ctx.abort() not called or not effective
- Session start notification missing branch info when on autoagent/* branch — getCurrentBranch() or string check broken
- TypeScript compilation errors in dashboard.ts or index.ts — import paths or type signatures wrong

## Requirements Proved By This UAT

- R103 (Multi-Experiment via Git Branches) — Tests 5, 6, 9, 10 prove branch detection, listing, and display
- R104 (Live Dashboard for Agent Loop) — Tests 1-6 prove dashboard overlay reads results.tsv, shows scores, refreshes, scrolls
- R106 (Minimal Command Surface) — Tests 7, 8 prove stop command works as expected
- R107 (Results Tracking in TSV) — Tests 2, 3 prove TSV parsing and display

## Not Proven By This UAT

- R103 full git branch lifecycle (creating branches, keep = advance, discard = revert) — these are executed by the LLM following program.md, not by the extension code
- R101 full autonomous loop execution — requires live LLM to run the complete edit → eval → keep/discard cycle
- R102 conversational setup quality — requires human evaluation of LLM-generated prepare.py/pipeline.py
- Dashboard rendering fidelity at various terminal sizes — would need visual regression testing

## Notes for Tester

- The dashboard component follows the same pattern as the GSD dashboard-overlay. If you've tested GSD overlays before, the interaction model is identical.
- The 2s refresh timer means you may need to wait up to 2 seconds to see disk changes reflected. Don't test faster than that.
- Test 8 (stop while running) requires a valid project setup with pipeline.py and prepare.py — use a simple setup or the one generated by conversational setup.
- Branch tests (5, 6, 9) create real git branches — clean up after testing with `git branch -d autoagent/test-experiment` etc.
