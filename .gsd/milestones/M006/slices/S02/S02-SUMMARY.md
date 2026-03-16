---
id: S02
parent: M006
milestone: M006
provides:
  - system.md MODE A with prepare.py output contract, skeleton, pipeline.py contract, baseline validation, completion criteria
  - index.ts go command guard requiring pipeline.py and prepare.py before dispatch
  - verify-s02.sh verification script for all slice criteria
requires:
  - slice: S01
    provides: system.md MODE A/B framework, index.ts go/stop commands, program.md protocol
affects:
  - S03
key_files:
  - tui/src/resources/extensions/autoagent/prompts/system.md
  - tui/src/resources/extensions/autoagent/index.ts
  - .gsd/milestones/M006/slices/S02/verify-s02.sh
key_decisions:
  - D083: system.md MODE A skeleton includes ~25 lines of Python covering test_cases, eval(), check(), and __main__ with argparse — minimal but complete
  - D084: go guard checks pipeline.py and prepare.py existence before dispatching, reuses autoagentDir variable
patterns_established:
  - verify-s02.sh uses `&& r=0 || r=1` pattern for grep checks under set -euo pipefail
observability_surfaces:
  - go guard emits "Project not ready" notification via ctx.ui.notify when pipeline.py or prepare.py is missing
  - verify-s02.sh runnable at any time to check all slice invariants (12 checks)
drill_down_paths:
  - .gsd/milestones/M006/slices/S02/tasks/T01-SUMMARY.md
duration: 15min
verification_result: passed
completed_at: 2026-03-15
---

# S02: Conversational Setup + Minimal UX

**Enriched system.md MODE A with full prepare.py/pipeline.py contracts and skeleton, added baseline validation step, and guarded go command against missing project files.**

## What Happened

system.md MODE A was rewritten from 6 vague steps to 6 concrete steps:

- Step 2 (prepare.py) now includes exact output format (`score: X.XXXX`, `total_examples: N`, etc.) and a ~25-line Python skeleton showing test_cases list, eval(), check(), and `__main__` with argparse
- Step 3 (pipeline.py) specifies `run(input_data, context) -> dict` returning `{"output": ...}`
- Old step 4 "Copy program.md" removed — go command handles this via bundled fallback (D080)
- Step 5 "Validate baseline" instructs the LLM to run eval and verify score is 0.1–0.9
- Step 6 adds explicit completion criteria: files exist AND baseline scores reasonably

In index.ts, a guard at the top of the go handler checks for `pipeline.py` and `prepare.py` existence before dispatching. If either is missing, shows a "Project not ready" notification and returns early.

## Verification

- `bash .gsd/milestones/M006/slices/S02/verify-s02.sh` — 12/12 PASS
- `tsc --noEmit` — zero errors
- system.md MODE A skeleton is ~25 lines of Python, not bloated
- "Copy program.md" step confirmed absent
- go guard confirmed present in index.ts

## Requirements Advanced

- R102 (Conversational Setup) — system.md now contains the full contracts and skeleton needed for the LLM to guide a user through project setup via conversation
- R106 (Minimal Command Surface) — go command now contextually refuses to dispatch when project files are missing, providing setup guidance instead

## Requirements Validated

- none — R102 and R106 require live runtime testing (real LLM conversation) to be fully validated

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

none

## Known Limitations

- The skeleton in system.md is a starting point — real conversations may reveal edge cases where the LLM produces prepare.py files that don't match the contract
- Baseline validation (score 0.1–0.9) is advisory, not enforced by code — the LLM must follow the instruction
- No programmatic check that prepare.py output actually matches the `score: X.XXXX` format — that's a runtime concern for the experiment loop

## Follow-ups

- none — S03 handles the remaining gaps (multi-experiment branches, dashboard, real stop command)

## Files Created/Modified

- `tui/src/resources/extensions/autoagent/prompts/system.md` — MODE A rewritten with prepare.py contract/skeleton, pipeline.py contract, baseline validation, completion criteria; "Copy program.md" step removed
- `tui/src/resources/extensions/autoagent/index.ts` — go command guarded with pipeline.py/prepare.py existence check before dispatch
- `.gsd/milestones/M006/slices/S02/verify-s02.sh` — 12-check verification script for all slice criteria

## Forward Intelligence

### What the next slice should know
- system.md MODE A is now detailed enough to guide real setup conversations — S03 doesn't need to touch it
- The go command guard creates `autoagentDir` early, which is reused for subsequent file reads — any new file checks in S03 can use the same variable

### What's fragile
- system.md content is verified by grep patterns in verify-s02.sh — changing the exact phrasing (e.g., "Setup is done when ALL") will break verification. Update the script if you change the wording.

### Authoritative diagnostics
- `bash .gsd/milestones/M006/slices/S02/verify-s02.sh` — comprehensive check of all content contracts and guard logic

### What assumptions changed
- Previous attempts wrote files to the main repo working tree instead of the GSD worktree at `.gsd/worktrees/M006`, causing auto-mode to never see the artifacts
