# S04: Sandbox Isolation & Final Assembly

**Goal:** Pipeline code executes inside a Docker container with restricted filesystem/network. When Docker is unavailable, execution falls back to direct mode with a warning. All four safety gates (TLA+, Pareto, leakage, sandbox) are active together and produce archive-visible results.
**Demo:** A single `OptimizationLoop.run()` invocation exercises all four gates across multiple iterations — TLA+ fail discards, leakage block discards, Pareto discard, and sandbox-wrapped evaluation succeeds — with each gate's result visible in archive entries.

## Must-Haves

- `SandboxRunner` class with `run()` matching `PipelineRunner.run()` signature
- `SandboxRunner.available()` static method checking Docker binary + daemon
- Container reuse per iteration: `docker create` + `docker start`, examples via `docker exec` (D045)
- Pipeline source copied into container via `docker cp`, not bind-mounted
- `--network=none` for test isolation
- Graceful degradation: falls back to `PipelineRunner` when Docker unavailable (D043)
- `SandboxResult` frozen dataclass with sandbox metadata
- `sandbox_execution` field on `ArchiveEntry` (backward-compatible)
- Final integration test: all four gates active, each exercised, archive entries inspectable
- All 357 existing tests pass — zero regressions

## Proof Level

- This slice proves: final-assembly
- Real runtime required: no (Docker subprocess mocked; contract-level proof)
- Human/UAT required: no

## Verification

- `pytest tests/test_sandbox.py -v` — all pass (SandboxRunner unit tests: available check, run with Docker, fallback without Docker, container lifecycle, serialization round-trip)
- `pytest tests/test_loop_sandbox.py -v` — all pass (sandbox in loop context, fallback behavior)
- `pytest tests/test_final_assembly.py -v` — all pass (all four gates active, each exercised across iterations, archive entries carry all gate results)
- `pytest tests/ -v` — all pass, zero regressions from 357 baseline
- Failure-path check: `SandboxResult.fallback_reason` populated when Docker unavailable; `PipelineResult.error` populated with structured `ErrorInfo` on container failure — both inspectable in archive entries

## Observability / Diagnostics

- Runtime signals: INFO log on sandbox use/skip, container lifecycle events; WARNING on Docker unavailability
- Inspection surfaces: `sandbox_execution` dict in archive JSON entries (sandbox_used, container_id, network_policy, fallback_reason)
- Failure visibility: SandboxResult carries error info on container failure; archive persists it
- Redaction constraints: none (no secrets in sandbox metadata)

## Integration Closure

- Upstream surfaces consumed: `PipelineRunner.run()` signature, `Evaluator.__init__(runner=)`, `TLAVerifier`, `LeakageChecker`, `pareto_decision()`, `ArchiveEntry` field pattern
- New wiring introduced: `SandboxRunner` passed as `runner` to `Evaluator`; `sandbox_execution` field on `ArchiveEntry`; startup availability warning in loop
- What remains before the milestone is truly usable end-to-end: nothing — this is the final slice

## Tasks

- [x] **T01: Build SandboxRunner with Docker isolation and unit tests** `est:45m`
  - Why: Core sandbox module — mirrors verification.py pattern. Must exist before loop integration.
  - Files: `src/autoagent/sandbox.py`, `tests/test_sandbox.py`
  - Do: Build `SandboxRunner` class with `available()` (checks `docker` on PATH + `docker info` daemon check), `run()` matching `PipelineRunner.run()` signature (docker create → docker cp pipeline source → docker exec with JSON stdin/stdout → parse PipelineResult), container lifecycle management (create/start per iteration, exec per example, stop/rm on cleanup), `--network=none`, `SandboxResult` frozen dataclass. Fallback: when Docker unavailable, delegate to `PipelineRunner` directly with warning. All Docker subprocess calls mocked in tests.
  - Verify: `pytest tests/test_sandbox.py -v` — all pass
  - Done when: `SandboxRunner` passes all unit tests covering: available (both cases), run with mocked Docker, fallback to PipelineRunner, container reuse across examples, serialization round-trip, error handling

- [x] **T02: Wire sandbox into evaluator/loop and build final assembly integration test** `est:45m`
  - Why: Completes the milestone — all four gates wired, exercised, and proven together.
  - Files: `src/autoagent/archive.py`, `src/autoagent/loop.py`, `tests/test_loop_sandbox.py`, `tests/test_final_assembly.py`
  - Do: Add `sandbox_execution: dict | None` to `ArchiveEntry` (same pattern as tla_verification). Wire `SandboxRunner` into loop: accept optional `sandbox_runner` param, pass it as `runner` to `Evaluator`, log availability warning at startup, record sandbox metadata in archive entries. Build `test_loop_sandbox.py` (sandbox in loop context, fallback). Build `test_final_assembly.py` — the capstone: construct a multi-iteration scenario where iteration 1 fails TLA+, iteration 2 is blocked by leakage, iteration 3 is discarded by Pareto, iteration 4 passes all gates with sandbox execution. Verify all four gate results appear in archive entries.
  - Verify: `pytest tests/test_loop_sandbox.py tests/test_final_assembly.py -v` — all pass; `pytest tests/ -v` — zero regressions
  - Done when: All four safety gates exercised in one loop run, each producing archive-visible results. R021 validated. 357+ tests passing.

## Files Likely Touched

- `src/autoagent/sandbox.py` — new
- `src/autoagent/archive.py` — add sandbox_execution field
- `src/autoagent/loop.py` — add sandbox_runner parameter, startup warning, archive recording
- `tests/test_sandbox.py` — new
- `tests/test_loop_sandbox.py` — new
- `tests/test_final_assembly.py` — new
