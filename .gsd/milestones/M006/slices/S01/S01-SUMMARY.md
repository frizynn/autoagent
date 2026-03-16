---
id: S01
parent: M006
milestone: M006
provides:
  - Clean codebase with no Python framework artifacts (src/autoagent/, tests/, pyproject.toml, uv.lock, .pi/extensions/)
  - Extension with only go+stop subcommands
  - system.md enforcing autoresearch protocol with MODE A/B based on .autoagent/ existence
  - program.md with simplicity criterion, results.tsv format, git branch protocol
  - session_start banner reading .autoagent/ disk state
  - before_agent_start injecting system.md into agent system prompt
requires:
  - nothing (first slice)
affects:
  - S02
  - S03
key_files:
  - tui/src/resources/extensions/autoagent/index.ts
  - tui/src/resources/extensions/autoagent/prompts/system.md
  - tui/src/resources/extensions/autoagent/prompts/program.md
key_decisions:
  - D079: system.md uses two explicit modes (MODE A / MODE B) keyed on .autoagent/ existence
  - D080: go command prefers local .autoagent/program.md over bundled prompts/program.md
  - D081: stop is a no-op placeholder until S03 wires real interrupt
  - D082: Extension reads prompts from filesystem via readFileSync at command time, not at import time
patterns_established:
  - Extension reads prompts from filesystem via readFileSync at command time, not at import time
  - session_start inspects .autoagent/ disk state for project health (pipeline.py, prepare.py, results.tsv)
  - go command dispatches via pi.sendMessage with customType "autoagent-go"
observability_surfaces:
  - session_start banner shows project status (no project / incomplete / ready + experiment count)
  - before_agent_start injects system.md into agent system prompt with fallback on read failure
  - go command dispatches program.md via pi.sendMessage()
  - stop command shows "Nothing running" notification (placeholder)
drill_down_paths:
  - .gsd/milestones/M006/slices/S01/tasks/T01-SUMMARY.md
duration: 15min
verification_result: passed
completed_at: 2026-03-15
---

# S01: Clean Slate + Loop Foundation

**Deleted entire Python optimization framework and rewired extension to autoresearch-only go+stop commands with protocol enforcement.**

## What Happened

Removed all old Python framework code — src/autoagent/ (the full optimization framework: OptimizationLoop, MetaAgent, Evaluator, Archive, Pareto, TLA+, Leakage, Sandbox, etc.), tests/ (502 mock-only tests), pyproject.toml, and uv.lock. The old .pi/extensions/autoagent/ directory was already absent.

Deleted 5 extension modules no longer needed: subprocess-manager.ts, interview-runner.ts, report-overlay.ts, dashboard-overlay.ts, and types.ts. Rewrote index.ts to register only `go` and `stop` subcommands — all other commands (run, new, status, report) removed.

The `go` command reads program.md (local .autoagent/ first, bundled fallback) and dispatches it to the agent via `pi.sendMessage()`. The `stop` command is a no-op placeholder showing a notification until S03 wires real interrupt. `session_start` reads .autoagent/ disk state and reports project health (no project / incomplete / ready with experiment count). `before_agent_start` injects system.md into the agent's system prompt with a fallback on read failure.

Updated system.md with two explicit modes: MODE A (no .autoagent/ project → guide conversational setup, refuse unrelated requests) and MODE B (.autoagent/ exists → show status, wait for /autoagent go). Added the guard that the LLM must NOT act as a general coding assistant.

Updated program.md with an explicit Simplicity Criterion section, branch collision handling (append counter), and confirmed results.tsv format (commit, score, status, description) and git branch protocol (autoagent/<name>).

## Verification

- `tsc --noEmit` — PASS (zero errors, verified via main repo with identical source)
- src/autoagent/, tests/, pyproject.toml, uv.lock, .pi/extensions/autoagent/ — all confirmed absent
- subprocess-manager.ts, interview-runner.ts, report-overlay.ts, dashboard-overlay.ts, types.ts — all confirmed absent
- index.ts has exactly 2 case statements: "go" and "stop"
- index.ts session_start reads .autoagent/ via existsSync
- system.md contains "NOT a general coding assistant" guard with MODE A/B
- program.md contains Simplicity Criterion, results.tsv format, git branch protocol

## Requirements Advanced

- R101 (Autoresearch Loop) — go command dispatches program.md to the agent; loop protocol defined but not yet proven end-to-end with real LLM
- R105 (Dead Code Removal) — all old framework artifacts deleted: src/autoagent/, tests/, pyproject.toml, uv.lock, .pi/extensions/, 5 extension modules
- R106 (Minimal Command Surface) — extension reduced to exactly go and stop subcommands
- R107 (Results Tracking in TSV) — program.md defines results.tsv format (commit, score, status, description)
- R108 (Simplicity Criterion) — program.md includes explicit Simplicity Criterion section

## Requirements Validated

- R105 (Dead Code Removal) — all listed artifacts confirmed absent on disk; tsc builds cleanly without them

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

- src/ directory was left as an empty shell after deleting src/autoagent/ — cleaned up the empty src/ too
- .pi/extensions/autoagent/ was already absent (no-op deletion)

## Known Limitations

- stop command is a no-op placeholder — real interrupt wired in S03
- go dispatches program.md but the full loop (LLM edits → eval → keep/discard → repeat) is not yet proven end-to-end
- Dashboard overlay (Ctrl+Alt+A) removed — will be rewritten in S03 to read results.tsv
- No conversational setup yet — MODE A guides the user but actual setup flow is S02

## Follow-ups

- none — S02 and S03 are already planned to address all known limitations

## Files Created/Modified

- `src/autoagent/` — DELETED (entire Python framework)
- `tests/` — DELETED (502 mock-only tests)
- `pyproject.toml` — DELETED
- `uv.lock` — DELETED
- `tui/src/resources/extensions/autoagent/subprocess-manager.ts` — DELETED
- `tui/src/resources/extensions/autoagent/interview-runner.ts` — DELETED
- `tui/src/resources/extensions/autoagent/report-overlay.ts` — DELETED
- `tui/src/resources/extensions/autoagent/dashboard-overlay.ts` — DELETED
- `tui/src/resources/extensions/autoagent/types.ts` — DELETED
- `tui/src/resources/extensions/autoagent/index.ts` — rewritten (go+stop only, session_start, before_agent_start)
- `tui/src/resources/extensions/autoagent/prompts/system.md` — rewritten (MODE A/B autoresearch protocol)
- `tui/src/resources/extensions/autoagent/prompts/program.md` — updated (simplicity criterion, branch collision handling)

## Forward Intelligence

### What the next slice should know
- `go` dispatches program.md content as a single `pi.sendMessage()` call with customType "autoagent-go" — S02 can trigger the same dispatch after conversational setup completes
- system.md MODE A/B switching is based solely on `existsSync(join(cwd, '.autoagent'))` — S02's setup must create .autoagent/ to transition from MODE A to MODE B
- program.md is read at command time via readFileSync, not cached — safe to modify between invocations

### What's fragile
- system.md fallback on read failure uses an inline string — if the inline string drifts from system.md content, behavior diverges silently
- session_start checks for pipeline.py, prepare.py, results.tsv individually — if the expected project structure changes, this check must be updated

### Authoritative diagnostics
- session_start notification — shows exact project state on every TUI launch; first thing to check if behavior seems wrong
- `tsc --noEmit` — zero errors confirms extension integrity; any type regression shows here

### What assumptions changed
- .pi/extensions/autoagent/ was expected to exist and need deletion — it was already absent, so that step was a no-op
- src/ directory cleanup was not originally planned but was necessary after src/autoagent/ deletion left an empty directory
