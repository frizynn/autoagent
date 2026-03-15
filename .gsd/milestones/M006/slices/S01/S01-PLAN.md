# S01: Home screen and subprocess loop runner

**Goal:** `autoagent` opens a persistent TUI with project status, can start/stop optimization runs via subprocess, and shows live iteration progress.
**Demo:** User types `autoagent`, sees a dashboard with current project state. Presses a key to start a run, sees live iterations scroll by with scores and decisions, can press a key to stop it.

## Must-Haves

- TUI opens on `autoagent` with no args
- Home screen shows project state (phase, iteration, best score, cost)
- "Run" action spawns `autoagent run --jsonl` as a subprocess
- Live JSONL event streaming into the dashboard
- "Stop" action sends SIGTERM to the subprocess
- Subprocess crash doesn't crash the TUI
- All existing headless CLI modes still work
- No project → shows init prompt with action to create one

## Proof Level

- This slice proves: integration
- Real runtime required: yes (subprocess spawning)
- Human/UAT required: yes (visual TUI check)

## Verification

- `python -m pytest tests/test_tui.py -v` — all headless tests pass
- `python -m pytest tests/ -v` — full suite passes (509+)
- Manual: `autoagent` opens TUI, can start and stop a run

## Tasks

- [ ] **T01: Subprocess runner and event streaming** `est:1h`
  - Why: The loop must run as a subprocess for crash isolation, streaming JSONL events back to the TUI
  - Files: `src/autoagent/tui.py`
  - Do: Replace the in-process thread worker with a subprocess that spawns `autoagent run --jsonl`. Parse JSONL lines from stdout. Handle subprocess lifecycle (start, stop via SIGTERM, crash detection). Buffer events in a queue for the UI to consume.
  - Verify: `python -m pytest tests/test_tui.py -v`
  - Done when: TUI can start a subprocess, receive events, and handle subprocess exit/crash without crashing itself

- [ ] **T02: Home screen with actions** `est:1h`
  - Why: The TUI needs an interactive home screen, not just a passive dashboard
  - Files: `src/autoagent/tui.py`, `src/autoagent/cli.py`
  - Do: Redesign the TUI layout as a proper home screen: project status panel at top, action bar (Run / Stop / Report / Init / Quit), live event log, score sparkline. Wire keybinds: `r` to run, `s` to stop, `q` to quit. Handle the no-project state (show init action). Wire `autoagent` (no args) to always open the TUI.
  - Verify: `python -m pytest tests/test_tui.py -v` and manual visual check
  - Done when: TUI shows status, responds to keybinds, and can launch/stop runs

- [ ] **T03: Integration test and polish** `est:30m`
  - Why: Need to verify the full flow works end-to-end and clean up rough edges
  - Files: `tests/test_tui.py`, `src/autoagent/tui.py`
  - Do: Add tests for subprocess lifecycle (start, stop, crash). Verify existing headless CLI still works. Polish error messages, loading states, and edge cases (double-start, stop when not running).
  - Verify: `python -m pytest tests/ -v` — full suite passes
  - Done when: All tests pass, no regressions, TUI handles edge cases gracefully

## Files Likely Touched

- `src/autoagent/tui.py`
- `src/autoagent/cli.py`
- `tests/test_tui.py`
- `pyproject.toml`
