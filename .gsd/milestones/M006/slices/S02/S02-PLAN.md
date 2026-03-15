# S02: Interview flow inside TUI

**Goal:** User can configure a new project via the multi-turn interview without leaving the TUI.
**Demo:** User presses `n` in the TUI, sees interview questions one by one as input prompts, answers them, and the project is configured.

## Must-Haves

- Keybind `n` triggers interview from the TUI home screen
- Interview runs as subprocess (`autoagent new --json`) per D066/D071
- Each prompt renders as a Textual Input widget
- Confirmation summary displayed before final accept
- On completion, project state reloads in the TUI
- Escape cancels the interview cleanly

## Proof Level

- This slice proves: integration
- Real runtime required: yes (subprocess communication)
- Human/UAT required: yes (visual check of input flow)

## Verification

- `python -m pytest tests/test_tui.py -v` — all tests pass
- `python -m pytest tests/ -v` — full suite passes (512+)

## Tasks

- [ ] **T01: Interview screen with subprocess JSON protocol** `est:1h`
  - Why: The interview flow needs to run inside the TUI as an interactive screen
  - Files: `src/autoagent/tui.py`
  - Do: Add an interview mode triggered by `n` keybind. Spawn `autoagent new --json` subprocess. Read JSON prompts from stdout, render as Textual Input widgets. Send answers back via stdin. Handle confirmation, completion, error, and abort (Escape). On completion, reload project state.
  - Verify: `python -m pytest tests/test_tui.py -v`
  - Done when: Full interview flow works inside the TUI, project gets configured

## Files Likely Touched

- `src/autoagent/tui.py`
- `tests/test_tui.py`
