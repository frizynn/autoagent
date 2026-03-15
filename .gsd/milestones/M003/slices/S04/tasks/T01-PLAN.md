---
estimated_steps: 5
estimated_files: 2
---

# T01: Build SandboxRunner with Docker isolation and unit tests

**Slice:** S04 — Sandbox Isolation & Final Assembly
**Milestone:** M003

## Description

Build `sandbox.py` as a self-contained module following the `verification.py` pattern. `SandboxRunner` wraps `PipelineRunner.run()` in Docker container execution. The class manages container lifecycle (create → start → exec per example → stop/rm), copies pipeline source via `docker cp` (no bind-mounts), uses `--network=none`, and falls back to direct `PipelineRunner` when Docker is unavailable. All Docker interaction via `subprocess.run()` per D044 — zero Python package dependencies.

## Steps

1. Create `src/autoagent/sandbox.py` with `SandboxResult` frozen dataclass (sandbox_used: bool, container_id: str | None, network_policy: str, fallback_reason: str | None, cost_usd: float = 0.0)
2. Implement `SandboxRunner` class:
   - `__init__(self, fallback_runner: PipelineRunner | None = None, image: str = "python:3.11-slim")` — stores config, creates fallback runner if not provided
   - `available()` static method — `shutil.which("docker")` + `subprocess.run(["docker", "info"])` with timeout
   - `run()` matching `PipelineRunner.run()` signature — when Docker available: create container, copy pipeline source via `docker cp`, run via `docker exec` with JSON stdin/stdout, parse result back to `PipelineResult`. When unavailable: delegate to fallback `PipelineRunner` with warning log.
   - Container lifecycle: `_create_container()`, `_start_container()`, `_exec_in_container()`, `_cleanup_container()`. Container created once per `run()` call (one iteration = one container, all examples go through it per D045).
   - A thin runner harness script (string constant in sandbox.py) that the container executes: loads pipeline, receives input via stdin JSON, writes PipelineResult JSON to stdout.
3. Handle serialization boundary: `PipelineResult` → JSON for stdout, reconstruct on host side. Handle `ErrorInfo` and `MetricsSnapshot` fields. For `PrimitivesContext`: container-side harness creates a mock context (real LLM integration deferred per research).
4. Error handling: Docker command failures → return `PipelineResult(success=False, error=ErrorInfo(...))`. Container timeout → same. Cleanup containers in finally block.
5. Create `tests/test_sandbox.py`: mock all `subprocess.run` calls for Docker commands. Test cases: available (docker present + daemon running), unavailable (no binary), unavailable (binary but daemon not running), run with mocked Docker (verify docker create/cp/exec/rm sequence), fallback to PipelineRunner when unavailable, serialization round-trip (PipelineResult → JSON → PipelineResult), error handling (docker exec failure), container reuse (multiple examples in one run call — verify single create, multiple exec).

## Must-Haves

- [ ] `SandboxRunner.run()` matches `PipelineRunner.run()` signature exactly
- [ ] `SandboxRunner.available()` checks both docker binary and daemon
- [ ] Pipeline source copied via `docker cp`, not bind-mounted
- [ ] `--network=none` on container creation
- [ ] Fallback to `PipelineRunner` when Docker unavailable, with warning log
- [ ] `SandboxResult` frozen dataclass with sandbox metadata
- [ ] Container reuse per iteration (one create, multiple exec for examples)
- [ ] All Docker interaction via `subprocess.run()` — zero package deps

## Verification

- `pytest tests/test_sandbox.py -v` — all tests pass
- `python3 -c "from autoagent.sandbox import SandboxRunner, SandboxResult"` — imports clean

## Inputs

- `src/autoagent/pipeline.py` — `PipelineRunner.run()` signature to match
- `src/autoagent/verification.py` — pattern to follow (available(), frozen result dataclass, subprocess interaction)
- `src/autoagent/types.py` — `PipelineResult`, `ErrorInfo`, `MetricsSnapshot` for serialization

## Observability Impact

- **New log signals:** INFO on sandbox container create/start/exec/cleanup lifecycle; WARNING when Docker unavailable and falling back to direct runner.
- **Inspection surface:** `SandboxResult` frozen dataclass exposes `sandbox_used`, `container_id`, `network_policy`, `fallback_reason` — downstream archive entries will consume this.
- **Failure visibility:** Docker command failures produce `PipelineResult(success=False, error=ErrorInfo(type="SandboxError", ...))`. Container timeout returns same pattern. `SandboxResult.fallback_reason` distinguishes "no docker binary" from "daemon not running".
- **How a future agent inspects:** Read `SandboxResult` fields from archive entries; grep logs for `autoagent.sandbox` logger; check `fallback_reason` for degradation cause.

## Expected Output

- `src/autoagent/sandbox.py` — complete SandboxRunner module with SandboxResult dataclass
- `tests/test_sandbox.py` — comprehensive unit tests with mocked Docker subprocess
