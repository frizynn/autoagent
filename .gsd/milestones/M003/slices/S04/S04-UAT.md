# S04: Sandbox Isolation & Final Assembly — UAT

**Milestone:** M003
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: All Docker interactions are subprocess calls mocked in tests. Contract-level proof validates the isolation pattern, serialization boundary, and graceful degradation without requiring a running Docker daemon.

## Preconditions

- Python 3.11+ with project installed in development mode (`.venv/bin/python -m pytest` works)
- All 381 tests passing (`pytest tests/ -q`)
- No Docker daemon required (all tests use mocked subprocess)

## Smoke Test

Run `pytest tests/test_sandbox.py tests/test_loop_sandbox.py tests/test_final_assembly.py -v` — all 24 tests pass.

## Test Cases

### 1. SandboxRunner availability detection

1. Run `pytest tests/test_sandbox.py::TestAvailable -v`
2. **Expected:** 4 tests pass — available when Docker binary + daemon present, unavailable when no binary, unavailable when daemon not running, unavailable on timeout.

### 2. Docker container lifecycle

1. Run `pytest tests/test_sandbox.py::TestRunWithDocker -v`
2. **Expected:** 3 tests pass — full lifecycle (create → start → cp → exec → cleanup), exec failure handling, create failure handling. Container ID logged at each step.

### 3. Graceful fallback to PipelineRunner

1. Run `pytest tests/test_sandbox.py::TestFallback -v`
2. **Expected:** 2 tests pass — fallback when no Docker binary (fallback_reason = "docker binary not found on PATH"), fallback when daemon not running (fallback_reason = "docker daemon not running or not accessible"). WARNING logged.

### 4. Serialization round-trip across container boundary

1. Run `pytest tests/test_sandbox.py::TestSerialization -v`
2. **Expected:** 3 tests pass — PipelineResult with success/metrics, PipelineResult with ErrorInfo, PipelineResult with no metrics/no error. All reconstruct correctly from JSON.

### 5. Container reuse within a single run

1. Run `pytest tests/test_sandbox.py::TestContainerReuse -v`
2. **Expected:** 2 tests pass — single `docker create` per `run()` call (not per example), cleanup always called even on exception.

### 6. Sandbox wired into OptimizationLoop

1. Run `pytest tests/test_loop_sandbox.py -v`
2. **Expected:** 4 tests pass — sandbox runner replaces evaluator's runner when available, fallback when unavailable, no metadata when no runner provided, sandbox_execution persisted in JSON archive.

### 7. Capstone: all four safety gates active

1. Run `pytest tests/test_final_assembly.py::TestFinalAssembly::test_four_gates_all_active -v`
2. **Expected:** Test passes. 5 iterations exercising all gates:
   - Iteration 1: V1 pipeline passes TLA+, leakage, sandbox → keep (baseline)
   - Iteration 2: TLA+ verification fails → discard (rationale mentions TLA+)
   - Iteration 3: Leakage blocks → discard (rationale mentions leakage)
   - Iteration 4: Passes TLA+/leakage but Pareto discards (regression) → discard (rationale mentions Pareto)
   - Iteration 5: Simpler pipeline passes all gates → keep

### 8. Archive entries carry all gate results

1. Run `pytest tests/test_final_assembly.py::TestFinalAssembly::test_archive_json_has_all_gate_fields -v`
2. **Expected:** Test passes. JSON archive entries contain `tla_verification`, `leakage_check`, and `sandbox_execution` fields. `sandbox_execution` includes `sandbox_used`, `network_policy`.

## Edge Cases

### Docker binary exists but daemon is down

1. `SandboxRunner.available()` returns `False`
2. `SandboxRunner.run()` delegates to `PipelineRunner`
3. `SandboxResult.fallback_reason` = "docker daemon not running or not accessible"
4. **Expected:** Pipeline executes successfully via fallback, WARNING logged

### Container creation fails mid-run

1. `docker create` raises subprocess error
2. **Expected:** `PipelineResult.error.type` = "SandboxError", cleanup still attempted, no container leak

### Container exec returns non-zero exit code

1. `docker exec` returns exit code 1 with stderr
2. **Expected:** `PipelineResult.error.type` = "SandboxExecError", error message includes stderr content

### Unparseable container output

1. Container stdout is not valid JSON
2. **Expected:** `PipelineResult.error.type` = "SandboxSerializationError"

### No sandbox_runner provided to loop

1. `OptimizationLoop(sandbox_runner=None)`
2. **Expected:** Loop runs normally, `sandbox_execution` is None in all archive entries, no sandbox-related logs

## Failure Signals

- Any of the 381 tests failing (regression)
- `sandbox_execution` missing from archive entries when sandbox_runner is provided
- Capstone test not exercising all four gate types across iterations
- `SandboxResult.fallback_reason` not populated when Docker is unavailable
- Container cleanup not called on error paths (resource leak)

## Requirements Proved By This UAT

- R021 (Sandbox Isolation for Pipeline Execution) — SandboxRunner wraps pipeline execution in Docker container with `--network=none`, `docker cp` source transfer, graceful fallback, and archive-visible metadata. Contract-level proof via mocked subprocess.

## Not Proven By This UAT

- Real Docker daemon execution (contract-level proof only — no integration test with actual containers)
- Network policy with selective provider domain allowlisting (only `--network=none` implemented)
- Performance characteristics of container startup/reuse under load

## Notes for Tester

- All Docker interactions are mocked — no Docker installation needed to run these tests.
- The capstone test (test_four_gates_all_active) is the single most important test — it proves all four M003 safety gates work together in one loop run.
- Container-side harness is a string constant — any changes to PipelineResult serialization format must update `_RUNNER_HARNESS` in sandbox.py.
