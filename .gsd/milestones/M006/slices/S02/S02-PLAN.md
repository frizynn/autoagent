# S02: Conversational Setup + Minimal UX

**Goal:** Launch autoagent with no project, describe what to optimize, LLM writes prepare.py + baseline pipeline.py through conversation. `go` refuses to dispatch without required files.
**Demo:** `go` command with no `.autoagent/` → error with setup prompt. system.md MODE A contains prepare.py contract, skeleton, pipeline.py contract, baseline validation step. tsc passes.

## Must-Haves

- system.md MODE A includes prepare.py output contract (exact `score: X.XXXX` format)
- system.md MODE A includes prepare.py skeleton (test_cases, eval function, `__main__` entry point)
- system.md MODE A includes pipeline.py contract (`run(input_data, context)` → dict with `"output"` key)
- system.md MODE A includes baseline validation step (run eval, verify score is 0.1–0.9)
- system.md MODE A removes "Copy program.md" step (go command handles this via bundled fallback)
- system.md MODE A includes explicit completion criteria (setup done when files exist and baseline scores reasonably)
- `go` command checks for `.autoagent/pipeline.py` and `.autoagent/prepare.py` before dispatching
- `go` command shows conversational setup prompt when files are missing

## Proof Level

- This slice proves: contract (system.md content correctness) + integration (go guard behavior)
- Real runtime required: no (content verification + tsc)
- Human/UAT required: yes (conversational setup quality — can only be validated by running real setup conversations)

## Verification

- `tsc --noEmit` passes with zero errors from the tui directory
- system.md contains `score: X.XXXX` format string (prepare.py output contract)
- system.md contains `def eval(` or equivalent skeleton entry point
- system.md contains `run(input_data, context)` (pipeline.py contract)
- system.md contains baseline validation instruction (score between 0.1 and 0.9)
- system.md does NOT contain "Copy program.md" or "Copy `program.md`" step
- system.md contains explicit setup completion criteria
- index.ts `go` case checks for `pipeline.py` and `prepare.py` existence before dispatching
- `bash .gsd/milestones/M006/slices/S02/verify-s02.sh` passes (scripted checks for all above)

## Integration Closure

- Upstream surfaces consumed: `index.ts` (go command, session_start, before_agent_start from S01), `system.md` (MODE A/B from S01), `program.md` (output format contract — read only)
- New wiring introduced in this slice: go guard (existence check before dispatch), enriched MODE A prompt
- What remains before the milestone is truly usable end-to-end: S03 (multi-experiment git branches, dashboard overlay, real stop command)

## Tasks

- [x] **T01: Enrich system.md MODE A and guard go command** `est:45m`
  - Why: system.md MODE A is too vague for the LLM to produce correct prepare.py files — it doesn't know the output format, the expected structure, or how to validate the result. The go command dispatches even with no project files. Both gaps must close together since they define the same user flow (no project → setup → go).
  - Files: `tui/src/resources/extensions/autoagent/prompts/system.md`, `tui/src/resources/extensions/autoagent/index.ts`, `.gsd/milestones/M006/slices/S02/verify-s02.sh`
  - Do: (1) Rewrite system.md MODE A to include prepare.py output contract with exact format, a concise skeleton (~25 lines), pipeline.py contract, baseline validation step, and explicit completion criteria. Remove "Copy program.md" step. (2) Add existence check in index.ts go command for `.autoagent/pipeline.py` and `.autoagent/prepare.py` — if missing, show setup prompt via notify and return without dispatching. (3) Write verify-s02.sh with grep/content checks for all verification criteria. (4) Run tsc --noEmit.
  - Verify: `bash .gsd/milestones/M006/slices/S02/verify-s02.sh` passes, `tsc --noEmit` zero errors
  - Done when: all verification checks pass, system.md MODE A is complete enough to guide an LLM through setup, go refuses dispatch without project files

## Observability / Diagnostics

- **go guard rejection**: `ctx.ui.notify()` with "Project not ready" message — visible in TUI notification area when user runs `/autoagent go` without required files
- **session_start status**: existing notification already surfaces missing file state (from S01)
- **Verification script**: `verify-s02.sh` checks all content contracts and guard logic — runnable at any time to confirm slice invariants hold
- **Failure visibility**: go command returns early without dispatching when files missing — no silent failure, explicit user-facing message
- **No secrets or credentials** in this slice — nothing to redact

## Files Likely Touched

- `tui/src/resources/extensions/autoagent/prompts/system.md`
- `tui/src/resources/extensions/autoagent/index.ts`
- `.gsd/milestones/M006/slices/S02/verify-s02.sh`
