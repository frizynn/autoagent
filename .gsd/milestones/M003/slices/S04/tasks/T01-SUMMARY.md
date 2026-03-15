---
id: T01
parent: S04
milestone: M003
provides:
  - SandboxRunner class with Docker container isolation
  - SandboxResult frozen dataclass with sandbox metadata
  - Serialization round-trip for PipelineResult across container boundary
key_files:
  - src/autoagent/sandbox.py
  - tests/test_sandbox.py
key_decisions:
  - Container-side harness is a string constant in sandbox.py, copied via docker cp — avoids package install in container
  - One container per run() call; examples handled by harness, not multiple host-side exec calls
  - _diagnose_unavailability() distinguishes "no binary" from "daemon not running" for fallback_reason
patterns_established:
  - SandboxRunner follows verification.py pattern: available() static method, frozen result dataclass, subprocess interaction
  - last_sandbox_result property for downstream archive consumption
observability_surfaces:
  - INFO logs on container create/start/exec/cleanup lifecycle (autoagent.sandbox logger)
  - WARNING log when Docker unavailable, falling back to direct runner
  - SandboxResult.fallback_reason distinguishes failure modes
  - PipelineResult.error with SandboxError/SandboxExecError/SandboxSerializationError types
duration: 15m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Build SandboxRunner with Docker isolation and unit tests

**Built SandboxRunner with Docker container isolation, --network=none, docker cp source transfer, graceful fallback, and 18 unit tests covering all paths.**

## What Happened

Created `sandbox.py` following the `verification.py` pattern. `SandboxRunner` wraps pipeline execution in Docker containers:

- `available()` static method checks both `shutil.which("docker")` and `docker info` daemon health
- `run()` matches `PipelineRunner.run()` signature exactly (pipeline_path, input_data, primitives_context, timeout)
- Container lifecycle: `_create_container()` with `--network=none` → `_start_container()` → `_copy_to_container()` (pipeline + harness via `docker cp`) → `_exec_in_container()` (JSON stdin/stdout) → `_cleanup_container()` in finally block
- Fallback path: when Docker unavailable, delegates to `PipelineRunner` with WARNING log and populated `SandboxResult.fallback_reason`
- Serialization boundary: `PipelineResult` → JSON dict → reconstruct with proper `ErrorInfo` and `MetricsSnapshot` handling

The container-side runner harness is a string constant (`_RUNNER_HARNESS`) that gets written to a temp file, copied into the container, and executed via `docker exec -i` with JSON piped to stdin.

## Verification

- `pytest tests/test_sandbox.py -v` — 18/18 passed
- `python -c "from autoagent.sandbox import SandboxRunner, SandboxResult"` — imports clean
- `pytest tests/ -v` — 375 passed, zero regressions (357 baseline + 18 new)

Slice-level checks (T01 is intermediate — partial expected):
- ✅ `pytest tests/test_sandbox.py -v` — all pass
- ⏳ `pytest tests/test_loop_sandbox.py -v` — T02 deliverable
- ⏳ `pytest tests/test_final_assembly.py -v` — T02 deliverable
- ✅ `pytest tests/ -v` — 375 passed, zero regressions
- ✅ Failure-path check: fallback_reason and error info verified in tests

## Diagnostics

- Grep `autoagent.sandbox` logger for container lifecycle events
- Check `SandboxResult.fallback_reason` for why fallback was used (None = sandbox succeeded, "docker binary not found on PATH" = no docker, "docker daemon not running or not accessible" = daemon down)
- `PipelineResult.error.type` values: `SandboxError` (container lifecycle failure), `SandboxExecError` (docker exec non-zero), `SandboxSerializationError` (unparseable container output)
- `runner.last_sandbox_result` property exposes metadata for archive integration in T02

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/sandbox.py` — SandboxRunner, SandboxResult, runner harness, serialization helpers
- `tests/test_sandbox.py` — 18 unit tests covering available, Docker lifecycle, fallback, serialization, container reuse, error handling
- `.gsd/milestones/M003/slices/S04/S04-PLAN.md` — added failure-path verification check per pre-flight
- `.gsd/milestones/M003/slices/S04/tasks/T01-PLAN.md` — added Observability Impact section per pre-flight
