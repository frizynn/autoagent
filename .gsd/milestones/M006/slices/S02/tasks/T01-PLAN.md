---
estimated_steps: 6
estimated_files: 3
---

# T01: Enrich system.md MODE A and guard go command

**Slice:** S02 — Conversational Setup + Minimal UX
**Milestone:** M006

## Description

system.md MODE A currently tells the LLM to "write prepare.py" and "write pipeline.py" but gives no specifics about what those files must contain. The LLM has no contract for prepare.py's output format (`score: X.XXXX` etc.), no skeleton to follow, no pipeline.py function signature, and no instruction to validate the baseline scores before declaring setup complete. Additionally, the go command dispatches program.md even when no project files exist.

This task enriches MODE A with the full prepare.py and pipeline.py contracts, adds a baseline validation step, removes the now-unnecessary "Copy program.md" step, and guards the go command against dispatching without required files.

## Steps

1. Rewrite system.md MODE A step-by-step guide:
   - Step 1: Understand the goal (keep existing, refine probing language)
   - Step 2: Write `prepare.py` — add the exact output contract (`score: X.XXXX`, `total_examples: N`, etc.), include a concise skeleton showing test_cases list structure, eval function, and `__main__` entry point with argparse for `eval` subcommand
   - Step 3: Write `pipeline.py` — add the `run(input_data, context)` → `{"output": ...}` contract explicitly
   - Step 4: Initialize `results.tsv` (keep existing)
   - Step 5: **Validate baseline** — new step: instruct the LLM to run `python3 prepare.py eval`, verify score is between 0.1 and 0.9, fix if not
   - Step 6: Tell user to run `/autoagent go` — add explicit completion criteria (all files exist AND baseline scores reasonably)
   - Remove old step 4 "Copy program.md" — go command handles this via bundled fallback (D080)

2. Add MODE A → MODE B transition note: "Once you've created all files and validated the baseline, tell the user to run `/autoagent go`. Do not offer further setup."

3. In index.ts, add existence check in the `go` case handler before dispatching:
   - Check `existsSync(join(projectDir, '.autoagent', 'pipeline.py'))` and `existsSync(join(projectDir, '.autoagent', 'prepare.py'))`
   - If either missing, `ctx.ui.notify()` with a message like "Project not ready — describe what you want to optimize and I'll help set it up." and return early
   - Keep the existing program.md read and dispatch logic unchanged for when files exist

4. Write `verify-s02.sh` — a bash script that greps system.md and index.ts for all required content:
   - system.md: `score: X.XXXX` or `score:` format reference
   - system.md: prepare.py skeleton markers (def eval, test_cases, `__main__`)
   - system.md: pipeline.py contract (`run(input_data, context)`)
   - system.md: baseline validation (0.1, 0.9 or equivalent range check instruction)
   - system.md: no "Copy program.md" or "Copy `program.md`" step
   - system.md: completion criteria
   - index.ts: pipeline.py and prepare.py existence check in go handler
   - Each check prints PASS/FAIL with description, script exits non-zero on any FAIL

5. Run `tsc --noEmit` from the tui directory (or equivalent path) and verify zero errors

6. Run `verify-s02.sh` and verify all checks pass

## Must-Haves

- [ ] system.md MODE A contains prepare.py output contract with exact format strings
- [ ] system.md MODE A contains prepare.py skeleton (test_cases list, eval function, `__main__`)
- [ ] system.md MODE A contains pipeline.py contract (`run(input_data, context)` → `{"output": ...}`)
- [ ] system.md MODE A contains baseline validation step with score range check
- [ ] system.md MODE A does not contain "Copy program.md" step
- [ ] system.md MODE A contains explicit completion criteria
- [ ] index.ts go command guards against missing pipeline.py/prepare.py
- [ ] tsc --noEmit passes with zero errors

## Verification

- `bash .gsd/milestones/M006/slices/S02/verify-s02.sh` — all checks PASS
- `tsc --noEmit` — zero errors
- Manual read of system.md MODE A confirms the skeleton is concise (~25 lines), not bloated

## Observability Impact

- **New signal**: go command emits a user-visible notify when pipeline.py or prepare.py is missing — future agents can verify this by checking the go handler's early-return path in index.ts
- **Inspection**: `verify-s02.sh` serves as a durable diagnostic — run it to check that all content contracts and guard logic remain intact after any changes
- **Failure state**: go guard prevents dispatch when project files are missing; the notification message tells the user what's wrong (no silent failure, no crash)
- **No new logs or persistent state** — this task modifies prompt content and adds a guard check, both observable through file content and TUI notifications

## Inputs

- `tui/src/resources/extensions/autoagent/prompts/system.md` — current MODE A/B definition from S01
- `tui/src/resources/extensions/autoagent/index.ts` — current go/stop command handlers from S01
- `tui/src/resources/extensions/autoagent/prompts/program.md` — output format contract (read-only reference, defines `score: X.XXXX` format)
- S01 summary — forward intelligence on readFileSync pattern, session_start disk state checks, go dispatch mechanism

## Expected Output

- `tui/src/resources/extensions/autoagent/prompts/system.md` — MODE A enriched with prepare.py contract, skeleton, pipeline.py contract, baseline validation, completion criteria; "Copy program.md" step removed
- `tui/src/resources/extensions/autoagent/index.ts` — go command guarded with pipeline.py/prepare.py existence check
- `.gsd/milestones/M006/slices/S02/verify-s02.sh` — verification script for all slice criteria
