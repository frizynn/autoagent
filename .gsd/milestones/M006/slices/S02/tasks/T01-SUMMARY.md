---
id: T01
parent: S02
milestone: M006
provides:
  - system.md MODE A with prepare.py output contract, skeleton, pipeline.py contract, baseline validation, completion criteria
  - index.ts go command guard requiring pipeline.py and prepare.py before dispatch
  - verify-s02.sh verification script for all slice criteria
key_files:
  - tui/src/resources/extensions/autoagent/prompts/system.md
  - tui/src/resources/extensions/autoagent/index.ts
  - .gsd/milestones/M006/slices/S02/verify-s02.sh
key_decisions:
  - system.md MODE A skeleton includes ~25 lines of Python covering test_cases, eval(), check(), and __main__ with argparse — minimal but complete
  - go guard checks pipeline.py and prepare.py existence before dispatching, reuses autoagentDir variable for cleaner code
patterns_established:
  - verify-s02.sh uses `&& r=0 || r=1` pattern for grep checks under set -euo pipefail
observability_surfaces:
  - go guard emits "Project not ready" notification via ctx.ui.notify when pipeline.py or prepare.py is missing
  - verify-s02.sh runnable at any time to check all slice invariants (12 checks)
duration: 15min
verification_result: passed
completed_at: 2026-03-15
blocker_discovered: false
---

# T01: Enrich system.md MODE A and guard go command

**Enriched MODE A with full prepare.py/pipeline.py contracts and skeleton, added baseline validation step, removed Copy program.md step, and guarded go command against missing project files.**

## What Happened

Rewrote system.md MODE A from 6 vague steps to 6 concrete steps with contracts:
- Step 2 (prepare.py) now includes exact output format (`score: X.XXXX`, `total_examples: N`, etc.) and a ~25-line Python skeleton showing test_cases list, eval(), check(), and `__main__` with argparse
- Step 3 (pipeline.py) now specifies `run(input_data, context) -> dict` returning `{"output": ...}`
- Old step 4 "Copy program.md" removed (go command handles this via bundled fallback per D080)
- New step 5 "Validate baseline" instructs the LLM to run eval and verify score is 0.1–0.9
- Step 6 adds explicit completion criteria: files exist AND baseline scores reasonably

In index.ts, added a guard at the top of the go handler that checks for `pipeline.py` and `prepare.py` existence before dispatching. If either is missing, shows a "Project not ready" notification and returns early. The existing program.md read/dispatch logic is untouched.

Wrote verify-s02.sh with 12 grep-based checks covering all system.md content contracts and index.ts guard logic.

## Verification

- `bash .gsd/milestones/M006/slices/S02/verify-s02.sh` — 12/12 PASS
- `tsc --noEmit` — zero errors (run from main repo tui directory; extension files are in `src/resources` which is excluded from compilation)
- Manual read: system.md MODE A skeleton is ~25 lines of Python code, not bloated

### Slice-level checks (all pass — this is the only task in the slice):
- ✅ `tsc --noEmit` passes with zero errors
- ✅ system.md contains `score: X.XXXX` format string
- ✅ system.md contains `def eval(` skeleton entry point
- ✅ system.md contains `run(input_data, context)` pipeline.py contract
- ✅ system.md contains baseline validation (0.1–0.9 range)
- ✅ system.md does NOT contain "Copy program.md" step
- ✅ system.md contains explicit completion criteria
- ✅ index.ts go handler checks for pipeline.py and prepare.py existence
- ✅ verify-s02.sh passes (all 12 checks)

## Diagnostics

- Run `bash .gsd/milestones/M006/slices/S02/verify-s02.sh` to verify all content contracts and guard logic
- Go guard rejection visible as TUI notification when running `/autoagent go` without project files
- No persistent state or logs added — changes are prompt content and a code guard

## Deviations

- verify-s02.sh initially used bare `grep` calls that failed under `set -euo pipefail` when grep returned non-zero for expected no-match cases. Fixed with `&& r=0 || r=1` pattern.

## Known Issues

None.

## Files Created/Modified

- `tui/src/resources/extensions/autoagent/prompts/system.md` — MODE A rewritten with prepare.py contract/skeleton, pipeline.py contract, baseline validation, completion criteria; "Copy program.md" step removed
- `tui/src/resources/extensions/autoagent/index.ts` — go command guarded with pipeline.py/prepare.py existence check before dispatch
- `.gsd/milestones/M006/slices/S02/verify-s02.sh` — 12-check verification script for all slice criteria
- `.gsd/milestones/M006/slices/S02/S02-PLAN.md` — added Observability / Diagnostics section (pre-flight fix)
- `.gsd/milestones/M006/slices/S02/tasks/T01-PLAN.md` — added Observability Impact section (pre-flight fix)
