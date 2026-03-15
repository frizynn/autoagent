---
id: S04
parent: M003
milestone: M003
provides:
  - SandboxRunner class with Docker container isolation (--network=none, docker cp, container reuse)
  - SandboxResult frozen dataclass with sandbox metadata
  - Graceful fallback to PipelineRunner when Docker unavailable
  - sandbox_execution field on ArchiveEntry for archive-visible sandbox metadata
  - sandbox_runner parameter on OptimizationLoop wiring SandboxRunner into Evaluator
  - Capstone integration test proving all four safety gates work together
requires:
  - slice: S01
    provides: TLAVerifier with verify() and available()
  - slice: S02
    provides: pareto_decision() with Pareto dominance and simplicity tiebreaker
  - slice: S03
    provides: LeakageChecker with check() and LeakageResult
affects: []
key_files:
  - src/autoagent/sandbox.py
  - src/autoagent/archive.py
  - src/autoagent/loop.py
  - tests/test_sandbox.py
  - tests/test_loop_sandbox.py
  - tests/test_final_assembly.py
key_decisions:
  - Container-side harness is a string constant in sandbox.py, copied via docker cp — avoids package install in container
  - One container per run() call; examples handled by harness, not multiple host-side exec calls
  - _diagnose_unavailability() distinguishes "no binary" from "daemon not running" for fallback_reason
  - Sandbox metadata captured at loop level (sandbox_used, network_policy, fallback_reason) rather than per-iteration container IDs
  - Capstone test uses 5 iterations (not 4) because Pareto needs a baseline "keep" before it can discard a regression
patterns_established:
  - SandboxRunner follows verification.py pattern: available() static method, frozen result dataclass, subprocess interaction
  - last_sandbox_result property for downstream archive consumption
  - _sandbox_execution_dict() helper method on OptimizationLoop centralizes sandbox metadata for all archive.add() call sites
observability_surfaces:
  - INFO logs on container create/start/exec/cleanup lifecycle (autoagent.sandbox logger)
  - WARNING log when Docker unavailable, falling back to direct runner
  - SandboxResult.fallback_reason distinguishes failure modes (None / "docker binary not found on PATH" / "docker daemon not running or not accessible")
  - PipelineResult.error with SandboxError/SandboxExecError/SandboxSerializationError types
  - sandbox_execution dict in archive JSON entries (sandbox_used, network_policy, fallback_reason)
drill_down_paths:
  - .gsd/milestones/M003/slices/S04/tasks/T01-SUMMARY.md
  - .gsd/milestones/M003/slices/S04/tasks/T02-SUMMARY.md
duration: ~40min
verification_result: passed
completed_at: 2026-03-14
---

# S04: Sandbox Isolation & Final Assembly

**Docker container isolation for pipeline execution with graceful fallback, plus capstone integration test proving all four M003 safety gates work together in one loop run.**

## What Happened

**T01** built `SandboxRunner` following the `verification.py` pattern. The runner wraps pipeline execution in Docker containers with `--network=none`, transferring pipeline source via `docker cp` (not bind mounts). A string-constant harness script gets copied into the container and executed via `docker exec -i` with JSON stdin/stdout for the serialization boundary. `available()` checks both Docker binary on PATH and daemon health. When Docker is unavailable, the runner falls back to `PipelineRunner` directly with a WARNING log and populated `SandboxResult.fallback_reason`. 18 unit tests cover all paths: availability checks, Docker lifecycle, fallback, serialization round-trip, container reuse, and error handling.

**T02** wired the sandbox into the optimization loop and archive. `ArchiveEntry` gained a `sandbox_execution: dict | None` field (same backward-compatible pattern as `tla_verification` and `leakage_check`). `OptimizationLoop.__init__()` accepts `sandbox_runner`, checks availability at startup, and replaces the evaluator's runner when Docker is present. A `_sandbox_execution_dict()` helper centralizes metadata for all four `archive.add()` call sites. The capstone `test_final_assembly.py` runs 5 iterations where each safety gate is distinctly exercised: iter 1 passes all gates (baseline), iter 2 fails TLA+, iter 3 is blocked by leakage, iter 4 is Pareto-discarded, iter 5 passes all gates with a simpler pipeline. All gate results verified in archive entries.

## Verification

- `pytest tests/test_sandbox.py -v` — 18/18 passed
- `pytest tests/test_loop_sandbox.py -v` — 4/4 passed
- `pytest tests/test_final_assembly.py -v` — 2/2 passed
- `pytest tests/ -q` — 381 passed, zero regressions (baseline 375 + 6 new)
- Failure-path check: `SandboxResult.fallback_reason` populated when Docker unavailable; `PipelineResult.error` populated with structured `ErrorInfo` on container failure

## Requirements Validated

- R021 (Sandbox Isolation for Pipeline Execution) — SandboxRunner executes pipeline code inside Docker container with `--network=none` and `docker cp` source transfer. Graceful fallback when Docker unavailable (D043). Container-side harness avoids package install. 18 unit tests + 4 loop integration tests + 2 capstone tests. Contract-level proof.

## Requirements Advanced

- None (R021 fully validated in this slice)

## New Requirements Surfaced

- None

## Requirements Invalidated or Re-scoped

- None

## Deviations

- Capstone test uses 5 iterations instead of the planned 4. Pareto's "no current best → keep" rule means the first evaluated iteration is always kept as baseline, so a separate iteration was needed before a regression could be Pareto-discarded.

## Known Limitations

- Docker subprocess calls are mocked in all tests — no integration test with a real Docker daemon. This is by design (contract-level proof per slice plan).
- Network policy is `--network=none` only. Configurable provider domain allowlisting (mentioned in roadmap) is not implemented — would require `--network=` with custom iptables rules.

## Follow-ups

- None — this is the final M003 slice.

## Files Created/Modified

- `src/autoagent/sandbox.py` — SandboxRunner, SandboxResult, container harness, serialization helpers
- `src/autoagent/archive.py` — added `sandbox_execution` field to ArchiveEntry and Archive.add()
- `src/autoagent/loop.py` — added sandbox_runner parameter, Docker availability check, fallback logic, sandbox_execution in all archive calls
- `tests/test_sandbox.py` — 18 unit tests
- `tests/test_loop_sandbox.py` — 4 loop integration tests
- `tests/test_final_assembly.py` — 2 capstone integration tests (5-iteration all-gates scenario)

## Forward Intelligence

### What the next slice should know
- M003 is complete. All four safety gates (TLA+, Pareto, leakage, sandbox) are wired into OptimizationLoop and produce archive-visible results.
- The loop's `__init__()` now accepts `tla_verifier`, `leakage_checker`, and `sandbox_runner` — all optional, all with graceful degradation.
- 381 tests passing across 22 test files.

### What's fragile
- Container-side harness (`_RUNNER_HARNESS` string constant in sandbox.py) must stay in sync with PipelineResult serialization format — any changes to PipelineResult fields require updating the harness.

### Authoritative diagnostics
- `autoagent.sandbox` logger for container lifecycle events
- `SandboxResult.fallback_reason` for why fallback was used
- `sandbox_execution` dict in archive JSON for post-run inspection

### What assumptions changed
- Planned 4-iteration capstone test became 5 iterations — Pareto needs a kept baseline before it can discard a regression.
