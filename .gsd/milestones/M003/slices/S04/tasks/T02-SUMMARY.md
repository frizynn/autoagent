---
id: T02
parent: S04
milestone: M003
provides:
  - sandbox_execution field on ArchiveEntry for archive-visible sandbox metadata
  - sandbox_runner parameter on OptimizationLoop wiring SandboxRunner into Evaluator
  - capstone final assembly integration test proving all four safety gates work together
key_files:
  - src/autoagent/archive.py
  - src/autoagent/loop.py
  - tests/test_loop_sandbox.py
  - tests/test_final_assembly.py
key_decisions:
  - Sandbox metadata captured at loop level (sandbox_used, network_policy, fallback_reason) rather than per-iteration container IDs — container lifecycle is internal to SandboxRunner
  - Loop __init__ replaces evaluator.runner when sandbox is available rather than wrapping evaluator — simpler, same effect
  - Capstone test uses 5 iterations (not 4) because Pareto needs a baseline "keep" before it can discard a regression
patterns_established:
  - _sandbox_execution_dict() helper method on OptimizationLoop centralizes sandbox metadata for all archive.add() call sites
observability_surfaces:
  - sandbox_execution dict in archive JSON entries (sandbox_used, network_policy, fallback_reason)
  - INFO log when sandbox runner active, WARNING when Docker unavailable at startup
duration: ~25min
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T02: Wire sandbox into evaluator/loop and build final assembly integration test

**Wired SandboxRunner into OptimizationLoop with Docker availability check and fallback, added sandbox_execution to archive entries, and built capstone 5-iteration integration test exercising all four safety gates.**

## What Happened

1. Added `sandbox_execution: dict | None = None` field to `ArchiveEntry` in archive.py with backward-compatible `from_dict()` and `add()` updates — same pattern as `tla_verification` and `leakage_check`.

2. Updated `OptimizationLoop.__init__()` to accept `sandbox_runner: SandboxRunner | None`. When provided and `available()`: replaces the evaluator's runner with the sandbox runner and logs INFO. When provided but unavailable: logs WARNING with diagnosis, keeps default PipelineRunner.

3. Added `_sandbox_execution_dict()` helper on the loop that builds the sandbox metadata dict, called from all four `archive.add()` sites (failed proposal, TLA+ discard, leakage discard, and main evaluation path).

4. Created `tests/test_loop_sandbox.py` with 4 tests: sandbox runner wired to evaluator, fallback when unavailable, no metadata when no runner, JSON persistence.

5. Created `tests/test_final_assembly.py` — capstone integration test with 5 iterations:
   - Iter 1: V1 pipeline passes all gates → keep (establishes Pareto baseline)
   - Iter 2: TLA+ fails → discard
   - Iter 3: Leakage blocks → discard
   - Iter 4: Regressed pipeline passes TLA+/leakage but Pareto discards (worse score + higher complexity)
   - Iter 5: Simpler V1b pipeline passes all gates → keep

## Verification

- `pytest tests/test_loop_sandbox.py tests/test_final_assembly.py -v` — 6/6 passed
- `pytest tests/ -q` — 381 passed, 0 failures (baseline was 375, +6 new)
- All slice-level verification checks pass:
  - `test_loop_sandbox.py` — sandbox in loop context, fallback behavior ✓
  - `test_final_assembly.py` — all four gates active, each exercised, archive entries carry all gate results ✓
  - Full suite zero regressions ✓

## Diagnostics

- `sandbox_execution` dict in archive JSON: `sandbox_used`, `container_id`, `network_policy`, `fallback_reason`
- Grep `autoagent.loop` logs for "Sandbox runner active" (INFO) or "Docker unavailable" (WARNING)
- When no sandbox_runner provided to loop, `sandbox_execution` is None in archive entries (backward compatible)

## Deviations

- Capstone test uses 5 iterations instead of 4 as originally planned. Pareto's "no current best → keep" rule means the first evaluated iteration is always kept, so a baseline keep is needed before a regression can be Pareto-discarded. The test still exercises all four gates across distinct iterations.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/archive.py` — added `sandbox_execution` field to ArchiveEntry and Archive.add()
- `src/autoagent/loop.py` — added sandbox_runner parameter, Docker availability check, fallback logic, sandbox_execution in all archive calls
- `tests/test_loop_sandbox.py` — 4 sandbox loop integration tests
- `tests/test_final_assembly.py` — capstone 5-iteration integration test with all four gates
