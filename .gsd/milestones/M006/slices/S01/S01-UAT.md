# S01: Clean Slate + Loop Foundation — UAT

**Milestone:** M006
**Written:** 2026-03-15

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: S01 is a deletion + rewrite slice — all verification is confirming absence of old artifacts, presence of new code paths, and build health. No live runtime behavior to test (go dispatch requires a running Pi agent session which is S02+ territory).

## Preconditions

- Repository checked out at the S01-completed commit
- Node.js and npm available (for tsc)
- Working directory is the repo root

## Smoke Test

Run `cd tui && npx tsc --noEmit` — must exit 0 with no output. This confirms the extension builds cleanly after all deletions and rewrites.

## Test Cases

### 1. Old Python framework fully removed

1. Check `ls src/autoagent/ 2>&1`
2. Check `ls tests/ 2>&1`
3. Check `ls pyproject.toml 2>&1`
4. Check `ls uv.lock 2>&1`
5. Check `ls .pi/extensions/autoagent/ 2>&1`
6. **Expected:** All five commands return "No such file or directory"

### 2. Old extension modules fully removed

1. Check `ls tui/src/resources/extensions/autoagent/subprocess-manager.ts 2>&1`
2. Check `ls tui/src/resources/extensions/autoagent/interview-runner.ts 2>&1`
3. Check `ls tui/src/resources/extensions/autoagent/report-overlay.ts 2>&1`
4. Check `ls tui/src/resources/extensions/autoagent/dashboard-overlay.ts 2>&1`
5. Check `ls tui/src/resources/extensions/autoagent/types.ts 2>&1`
6. **Expected:** All five return "No such file or directory"

### 3. Extension has exactly go and stop subcommands

1. Run `grep 'case "' tui/src/resources/extensions/autoagent/index.ts`
2. **Expected:** Exactly two matches: `case "go"` and `case "stop"`. No `case "run"`, `case "new"`, `case "status"`, or `case "report"`.

### 4. TypeScript builds with zero errors

1. Run `cd tui && npx tsc --noEmit`
2. **Expected:** Exit code 0, no output

### 5. session_start reads .autoagent/ disk state

1. Run `grep -A5 'session_start' tui/src/resources/extensions/autoagent/index.ts | head -20`
2. **Expected:** Code path shows `existsSync` checking `.autoagent/` directory and conditionally checking for pipeline.py, prepare.py, results.tsv

### 6. before_agent_start injects system.md

1. Run `grep -A5 'before_agent_start' tui/src/resources/extensions/autoagent/index.ts | head -15`
2. **Expected:** Code reads system.md via readFileSync and appends to system prompt. Fallback path exists for read failure.

### 7. go command reads and dispatches program.md

1. Run `grep -B2 -A10 'case "go"' tui/src/resources/extensions/autoagent/index.ts`
2. **Expected:** Code reads program.md (checks .autoagent/program.md first, falls back to bundled prompts/program.md), then calls `pi.sendMessage()` with the content.

### 8. stop command is a no-op placeholder

1. Run `grep -B2 -A10 'case "stop"' tui/src/resources/extensions/autoagent/index.ts`
2. **Expected:** Shows a notification like "Nothing running" without killing any process.

### 9. system.md enforces autoresearch protocol

1. Run `grep -c "MODE A\|MODE B" tui/src/resources/extensions/autoagent/prompts/system.md`
2. Run `grep -c "NOT a general coding assistant\|NOT act as a general" tui/src/resources/extensions/autoagent/prompts/system.md`
3. **Expected:** MODE A and MODE B both present (count ≥ 2). "NOT a general coding assistant" guard present (count ≥ 1).

### 10. program.md contains required protocol elements

1. Run `grep -c "Simplicity Criterion\|simplicity criterion" tui/src/resources/extensions/autoagent/prompts/program.md`
2. Run `grep -c "results.tsv" tui/src/resources/extensions/autoagent/prompts/program.md`
3. Run `grep -c "autoagent/" tui/src/resources/extensions/autoagent/prompts/program.md`
4. **Expected:** Simplicity Criterion present (≥ 1). results.tsv referenced (≥ 1). Git branch naming with autoagent/ prefix (≥ 1).

## Edge Cases

### No .autoagent/ directory at session start

1. Ensure no `.autoagent/` directory exists in cwd
2. The session_start handler should report "No project" status
3. **Expected:** Notification shows no-project state, no crash

### program.md missing at go time

1. Ensure no `.autoagent/program.md` exists AND bundled prompts/program.md is removed
2. Run `/autoagent go`
3. **Expected:** Warning notification displayed, command does not crash

### Incomplete .autoagent/ directory

1. Create `.autoagent/` with only pipeline.py (no prepare.py, no results.tsv)
2. session_start should report incomplete project
3. **Expected:** Notification shows which files are missing

## Failure Signals

- `tsc --noEmit` exits non-zero — type regression in the extension rewrite
- Any of the 5 old Python artifacts still exist on disk — deletion incomplete
- Any of the 5 old extension modules still exist — cleanup incomplete
- More than 2 `case` statements in the command handler — old commands not removed
- system.md missing MODE A/B or the "not a general assistant" guard — protocol enforcement broken
- program.md missing simplicity criterion or results.tsv format — protocol incomplete

## Requirements Proved By This UAT

- R105 (Dead Code Removal) — tests 1, 2 prove all old artifacts are gone
- R106 (Minimal Command Surface) — test 3 proves only go and stop exist
- R107 (Results Tracking in TSV) — test 10 proves program.md defines the format
- R108 (Simplicity Criterion) — test 10 proves program.md includes the criterion

## Not Proven By This UAT

- R101 (Autoresearch Loop) — go dispatches program.md but end-to-end loop with real LLM is not tested here
- R102 (Conversational Setup) — deferred to S02
- R103 (Multi-Experiment via Git Branches) — deferred to S03
- R104 (Live Dashboard) — deferred to S03

## Notes for Tester

- All tests are artifact-driven — no running TUI or agent session needed
- Tests can be run as shell commands in sequence
- The "edge cases" section describes code paths that exist in index.ts but require a running TUI to exercise interactively — verify by reading the code paths, not by launching the TUI
