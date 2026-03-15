---
estimated_steps: 4
estimated_files: 2
---

# T02: End-to-end structural verification and milestone audit

**Slice:** S03 — Report, Status, Stop, and Final Assembly
**Milestone:** M005

## Description

Run the full test suite, audit the extension file structure for completeness, and verify each M005 success criterion is structurally met. Write S03-UAT.md documenting results. No code changes — pure verification and documentation.

## Steps

1. **Run pytest full suite** — `pytest tests/ -q` must pass 479+ tests with no failures or regressions.

2. **Audit extension structure** — Verify all 7 expected files exist in `.pi/extensions/autoagent/` with correct exports. Check import consistency: every import resolves to an existing file, no circular dependencies, all type references valid.

3. **Verify M005 success criteria** — Walk through each criterion from the roadmap:
   - `/autoagent new` → interview overlay (S02 delivered)
   - `/autoagent run` → live dashboard (S01 delivered)
   - `/autoagent report` → report overlay (T01 delivered)
   - `Ctrl+Alt+A` → toggles dashboard (S01 delivered)
   - `/autoagent stop` → kills subprocess (S01 delivered)
   - Footer widget → shows state (S01 delivered)
   - `getArgumentCompletions` → tab completion (T01 delivered)
   Mark each as structurally present or missing. Note that visual/interactive UAT requires a live pi session.

4. **Write S03-UAT.md** — Document all verification results with pass/fail per criterion. Note deferred items (visual UAT).

## Must-Haves

- [ ] pytest passes 479+ tests
- [ ] All 7 extension files present and import-consistent
- [ ] Each M005 success criterion mapped to delivered code
- [ ] S03-UAT.md written with structured verification results

## Verification

- `pytest tests/ -q` output shows 479+ passed, 0 failed
- `ls .pi/extensions/autoagent/` shows 7 files
- S03-UAT.md exists with pass/fail for each milestone criterion

## Inputs

- `.pi/extensions/autoagent/` — All extension files from S01, S02, T01
- `tests/` — Full pytest suite
- `.gsd/milestones/M005/M005-ROADMAP.md` — Milestone success criteria

## Observability Impact

This task is pure verification — no runtime code changes. The observability signal it produces is the S03-UAT.md document itself, which serves as a structured audit trail for future agents. A future agent inspecting this milestone can read S03-UAT.md to know: which success criteria passed structural verification, which are deferred to visual UAT, and what the test suite state was at milestone completion. If any criterion failed, the UAT doc explains why and what's missing.

## Expected Output

- `.gsd/milestones/M005/slices/S03/S03-UAT.md` — Verification results document
