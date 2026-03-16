# Milestone Queue

Append-only log of queued milestones.

## Queued

### M005 — Pi TUI Extension
- **Vision:** AutoAgent as a native pi extension — `/autoagent` command opens an interactive TUI with live loop monitoring, interview flow, interrupt/resume, and reporting dashboard. The Python core stays unchanged; a TypeScript extension in `.pi/extensions/autoagent/` wraps it with pi's TUI primitives (overlays, widgets, components, keyboard shortcuts).
- **Why:** Current CLI is functional but invisible — you can't see what's happening during optimization. The pi TUI gives real-time visibility into iterations, scores, keep/discard decisions, budget burn, plus the ability to interrupt mid-loop and add context. This is the "wake up surprised" experience done right.
- **Key deliverables:**
  - `/autoagent` slash command with contextual wizard (like `/gsd`)
  - `/autoagent new` — interactive interview as a TUI overlay with rich input
  - `/autoagent run` — live dashboard showing iteration progress, scores, decisions
  - `/autoagent report` — rendered markdown report in overlay
  - `Ctrl+Alt+A` shortcut to toggle dashboard overlay
  - Widget showing current optimization status in pi footer
  - Subprocess management of Python `autoagent` commands via `pi.exec()`
- **Depends on:** M004 (complete CLI with all subcommands)
- **Queued:** 2026-03-14
