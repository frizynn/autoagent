---
estimated_steps: 5
estimated_files: 4
---

# T02: Wire sandbox into evaluator/loop and build final assembly integration test

**Slice:** S04 — Sandbox Isolation & Final Assembly
**Milestone:** M003

## Description

Wire `SandboxRunner` into the optimization loop and build the milestone capstone: a final integration test proving all four safety gates (TLA+, Pareto, leakage, sandbox) work together in one loop run. Each gate is exercised across different iterations, and all results are visible in archive entries.

## Steps

1. Add `sandbox_execution: dict | None = None` field to `ArchiveEntry` in `archive.py`. Update `from_dict()` with `.get("sandbox_execution")`. Update `Archive.add()` to accept and persist it. Same backward-compatible pattern as `tla_verification`.
2. Update `OptimizationLoop.__init__()` in `loop.py`: accept optional `sandbox_runner: SandboxRunner | None = None`. When provided and `available()`: pass it as `runner` to `Evaluator`. When provided but not available: log WARNING, use default `PipelineRunner`. Store sandbox status for archive recording.
3. Update loop's archive recording: include `sandbox_execution` dict in `Archive.add()` calls (sandbox_used, container_id, network_policy, or fallback_reason).
4. Create `tests/test_loop_sandbox.py`: test sandbox runner passed to evaluator, fallback when unavailable, sandbox metadata in archive entries. Follow `test_loop_verification.py` and `test_loop_leakage.py` patterns. Use MockSandboxRunner that duck-types the interface.
5. Create `tests/test_final_assembly.py` — the capstone integration test:
   - Construct a multi-iteration loop scenario with all four gates active
   - Iteration 1: TLA+ verification fails → discarded (MockTLAVerifier returns failure)
   - Iteration 2: Leakage check blocks → discarded (MockLeakageChecker returns blocked)
   - Iteration 3: Passes TLA+/leakage, but Pareto discards (score regresses)
   - Iteration 4: Passes all gates, sandbox-wrapped evaluation succeeds → kept
   - Assert: archive has 4 entries, each with the relevant gate result populated
   - Assert: entry 1 has tla_verification.passed=False, entry 2 has leakage_check.blocked=True, entry 3 has pareto_evaluation with discard, entry 4 has sandbox_execution.sandbox_used and is kept
   - Run full test suite to confirm zero regressions

## Must-Haves

- [ ] `sandbox_execution` field on `ArchiveEntry` (backward-compatible)
- [ ] Loop accepts `sandbox_runner` parameter and passes to `Evaluator`
- [ ] Startup WARNING when Docker unavailable
- [ ] Archive entries carry sandbox metadata
- [ ] Final assembly test: 4 iterations, each gate exercised, all results in archive
- [ ] Zero regressions from 357 baseline

## Verification

- `pytest tests/test_loop_sandbox.py tests/test_final_assembly.py -v` — all pass
- `pytest tests/ -v` — all pass, total ≥ 357

## Observability Impact

- Signals added: INFO log when sandbox runner active, WARNING when Docker unavailable at startup
- How a future agent inspects this: `sandbox_execution` dict in archive JSON, grep for `autoagent.loop` or `autoagent.sandbox` in logs
- Failure state exposed: `sandbox_execution.fallback_reason` in archive entries when Docker unavailable

## Inputs

- `src/autoagent/sandbox.py` — SandboxRunner from T01
- `src/autoagent/archive.py` — ArchiveEntry field addition pattern (from S01/S03)
- `src/autoagent/loop.py` — tla_verifier/leakage_checker parameter pattern to mirror
- `tests/test_loop_verification.py` — MockTLAVerifier pattern
- `tests/test_loop_leakage.py` — MockLeakageChecker pattern

## Expected Output

- `src/autoagent/archive.py` — updated with sandbox_execution field
- `src/autoagent/loop.py` — updated with sandbox_runner parameter and wiring
- `tests/test_loop_sandbox.py` — sandbox loop integration tests
- `tests/test_final_assembly.py` — capstone 4-gate integration test
