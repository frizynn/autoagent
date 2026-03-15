# M006: Standalone TUI

**Vision:** `autoagent` is a fully interactive terminal application. Type `autoagent`, get a dashboard that lets you do everything: init projects, configure them via interview, launch optimization runs, monitor them live, view reports, and stop runs — all from one persistent TUI.

## Success Criteria

- Typing `autoagent` (no args) opens a live TUI that stays open
- From the TUI, user can initialize a new project if none exists
- From the TUI, user can configure a project via the interview flow
- From the TUI, user can start an optimization run and see it progress live
- From the TUI, user can stop a running optimization
- From the TUI, user can view the optimization report
- The TUI shows current project status at all times (iteration, score, cost, phase)
- All existing headless CLI modes still work (`autoagent run`, `autoagent run --jsonl`, etc.)

## Key Risks / Unknowns

- Interview flow is multi-turn interactive — needs to work inside the TUI without blocking the event loop
- The optimization loop currently runs in-process via thread worker — need to decide if it should be a subprocess (like the Pi extension) for crash isolation
- Textual's input widgets need to handle the interview's vague-answer detection and follow-up probes

## Proof Strategy

- Interview-in-TUI → retire in S02 by proving the full interview flow works inside Textual
- Loop isolation → retire in S01 by proving subprocess-based loop with JSONL streaming works

## Verification Classes

- Contract verification: pytest + headless Textual tests
- Integration verification: end-to-end flow from TUI init → interview → run → report
- Operational verification: subprocess lifecycle (start/stop/crash recovery)
- UAT / human verification: visual check that the TUI looks right and responds to input

## Milestone Definition of Done

This milestone is complete only when all are true:

- All slice deliverables are complete
- `autoagent` with no args opens a fully functional TUI
- User can go from zero to a running optimization without leaving the TUI
- Headless CLI modes are unbroken
- Reports viewable inside the TUI
- 509+ tests passing

## Slices

- [ ] **S01: Home screen and subprocess loop runner** `risk:high` `depends:[]`
  > After this: `autoagent` opens a TUI with project status, can start/stop an optimization run via subprocess, and shows live iteration progress
- [ ] **S02: Interview flow inside TUI** `risk:high` `depends:[S01]`
  > After this: user can configure a new project via the multi-turn interview without leaving the TUI
- [ ] **S03: Report viewer and polish** `risk:low` `depends:[S01]`
  > After this: user can view the optimization report inside the TUI, and the overall UX is polished (keybinds, error states, help text)

## Boundary Map

### S01 → S02

Produces:
- `AutoagentApp` Textual app with screen-based navigation
- `SubprocessRunner` that spawns `autoagent run --jsonl` and streams events
- Home screen with status cards, event log, and action buttons

Consumes:
- nothing (first slice)

### S01 → S03

Produces:
- Screen infrastructure and navigation patterns
- Subprocess lifecycle management

Consumes:
- nothing (first slice)

### S02 → S03

Produces:
- Interview screen with multi-turn input handling

Consumes:
- Screen navigation from S01
