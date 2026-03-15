# S04: Sandbox Isolation & Final Assembly — Research

**Date:** 2026-03-14

## Summary

S04 has two distinct jobs: (1) build `SandboxRunner` — a Docker-based isolation layer that wraps pipeline execution, and (2) final assembly — wire all four safety gates together and prove they work in concert. The codebase is clean and the prior three slices established clear patterns: self-contained module with frozen result dataclass, optional parameter on `OptimizationLoop`, gate logic in `run()`.

The sandbox is architecturally different from the other gates. TLA+, Pareto, and leakage are pre-evaluation gates that inspect code or data. The sandbox wraps the *execution itself* — it replaces `PipelineRunner.run()` with Docker-contained execution. The cleanest integration: `SandboxRunner` wraps `PipelineRunner` and presents the same interface, so `Evaluator` can accept either runner. The `Evaluator.__init__` already accepts `runner: PipelineRunner | None = None` — we can pass a `SandboxRunner` that duck-types `PipelineRunner.run()`.

The final assembly integration test is the milestone's capstone: all four gates active in one loop run, each exercised and producing archive-visible results. This requires a carefully constructed test where the loop runs multiple iterations with different outcomes (TLA+ fail, leakage block, Pareto discard, sandbox execution pass). All four results must appear in archive entries.

## Recommendation

**Two tasks:** T01 builds `sandbox.py` with `SandboxRunner` class + unit tests. T02 wires sandbox into the evaluator/loop and builds the final integrated test proving all four gates active together.

For the sandbox itself: Docker execution via `subprocess.run()` (consistent with TLC pattern per D044). Pipeline source is *copied* into the container as a file, not bind-mounted (research note: bind-mounts can leak parent directories). The container gets: pipeline.py, a thin runner harness script, and receives input/primitives config via stdin JSON. Results come back via stdout JSON. Container reuse per iteration (D045): start one container, run all examples through it via `docker exec`.

Graceful degradation: `SandboxRunner.available()` checks for `docker` on PATH and daemon running (`docker info`). When unavailable, falls back to direct `PipelineRunner` with a warning log.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Container isolation | Docker via `subprocess.run()` | D044: proven isolation, well-understood network policy. System-level tool via subprocess — not a Python package dependency. |
| Pipeline execution harness | `PipelineRunner` (existing) | Duck-type its `.run()` interface. SandboxRunner delegates to PipelineRunner inside the container, or falls back to it directly when Docker unavailable. |
| Network policy | Docker `--network` flag | `--network=none` blocks all network. For real LLM calls: custom network with DNS filtering. For MVP/tests: `--network=none` is sufficient since MockLLM doesn't need network. |

## Existing Code and Patterns

- `src/autoagent/evaluation.py` `Evaluator.__init__` — accepts `runner: PipelineRunner | None = None`. Sandbox integration: pass `SandboxRunner` instance here. `_run_with_timeout()` calls `self.runner.run(pipeline_path, input_data, ctx, ...)` — SandboxRunner must match this signature.
- `src/autoagent/pipeline.py` `PipelineRunner.run()` — signature: `run(pipeline_path, input_data, primitives_context, *, timeout=None) -> PipelineResult`. SandboxRunner wraps this: serialize inputs → `docker exec` → deserialize `PipelineResult`.
- `src/autoagent/verification.py` `TLAVerifier` — **Pattern to follow.** Self-contained module, `available()` static method checking for external tool, frozen result dataclass. SandboxRunner mirrors this.
- `src/autoagent/loop.py` — Gates sequence: TLA+ → leakage → evaluation. Sandbox wraps the evaluation step itself (via `Evaluator`'s runner), so it doesn't add another gate to the loop — it's injected at `Evaluator` construction time. The loop only needs to know about sandbox for: (a) availability warning at startup, (b) archive recording of sandbox status.
- `src/autoagent/archive.py` `ArchiveEntry` — Already has `tla_verification`, `leakage_check`, `pareto_evaluation` optional fields. Add `sandbox_execution: dict | None = None` for sandbox metadata (used/skipped, container_id, network_policy).
- `tests/test_loop_verification.py` and `tests/test_loop_leakage.py` — **Test patterns.** Mock the external tool, test gate behavior in loop context. For sandbox: mock `subprocess.run` for Docker commands, verify fallback behavior.

## Constraints

- **Zero Python package dependencies** — Docker interaction via `subprocess.run()` only. No `docker` PyPI package.
- **Container reuse per iteration** (D045) — One `docker create` + `docker start` per iteration. All benchmark examples run via `docker exec` on the same container. Fresh container per iteration (sufficient isolation per D045).
- **Pipeline source copied, not mounted** (M003-RESEARCH) — `docker cp` the pipeline source into the container. No bind-mounts to avoid leaking host filesystem.
- **Serialization boundary** — Pipeline input/output must cross the container boundary. Input via stdin JSON, output via stdout JSON. `PrimitivesContext` can't be serialized (contains live objects) — the container-side harness creates its own `PrimitivesContext` with `MockLLM`/`MockRetriever`. Real LLM calls from inside the container would need network access + API keys passed as env vars.
- **PipelineResult reconstruction** — Container outputs JSON, sandbox deserializes back to `PipelineResult`. Must handle all fields including `ErrorInfo` and `MetricsSnapshot`.
- **Existing test count: 357** — Zero regressions allowed. New tests add on top.
- **`compile()+exec()` pipeline loading** (D014) — The container-side harness uses the same loading mechanism. Pipeline source is copied in, not imported.

## Common Pitfalls

- **Serialization mismatch** — `PipelineResult.output` is `Any` — could be complex objects that don't serialize to JSON. Mitigation: for sandbox mode, output is stringified or JSON-serialized. Document that sandbox-mode pipelines should return JSON-serializable output. For MVP/tests with MockLLM, output is always a string.
- **Docker not running vs not installed** — `shutil.which("docker")` finds the binary but daemon might not be running. `docker info` subprocess checks daemon status. Both must pass for `available()` to return True.
- **Container cleanup on crash** — If the loop crashes mid-iteration, orphaned containers linger. Mitigation: use `--rm` flag on `docker run`, or name containers deterministically and clean up in `__del__`/context manager.
- **Test complexity for final assembly** — Integration test with all four gates needs careful setup: MockTLAVerifier, MockLeakageChecker, SandboxRunner (or mock), and a multi-iteration scenario. Keep the test focused: 3-4 iterations, each exercising a different gate.
- **Timeout layering** — ThreadPoolExecutor timeout (D018) wraps the runner call. Inside the container, there's no per-example timeout enforcement (the container just runs). The existing ThreadPoolExecutor timeout in `_run_with_timeout` still works as the outer timeout — it kills the `docker exec` subprocess if it hangs. Belt-and-suspenders: also pass `--timeout` to `docker exec` if available (Docker 26.1+).

## Open Risks

- **PrimitivesContext serialization** — The biggest design tension. PrimitivesContext contains live `LLMProtocol` objects that can't be serialized. For sandbox execution, either: (a) the container creates its own MockLLM context (loses real LLM metrics), or (b) we serialize the LLM config (model name, API key, provider) and reconstruct inside the container. For M003 scope, (a) is sufficient — real LLM integration is M004. This means sandbox-mode evaluations with MockLLM produce identical results to non-sandbox mode.
- **Docker image management** — What base image? Need Python + the autoagent package (or at least `pipeline.py` loader logic). For MVP: use `python:3.11-slim` base image with a minimal runner script copied in. No need to build/publish a custom image.
- **Network policy for real LLM calls** — D044 says "allow outbound HTTPS to configured provider domains." Docker custom networks with iptables rules are complex. For M003 scope: `--network=none` for tests, document that production use needs `--network=host` or custom bridge. Defer fine-grained network policy to post-M003.
- **Test execution environment** — Tests can't rely on Docker being installed in CI. All Docker subprocess calls must be mocked. Real Docker integration test (if written) must be marked with `pytest.mark.skipif` for missing Docker.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Docker sandbox | `joelhooks/joelclaw@docker-sandbox` | available (62 installs) |
| Sandbox security | `useai-pro/openclaw-skills-security@sandbox-guard` | available (86 installs) |
| Process isolation | `illusion47586/isol8@isol8` | available (24 installs) |

Note: The sandbox-guard skill (86 installs) could inform security patterns. The docker-sandbox skill (62 installs) could inform container lifecycle management. Neither is essential — the implementation is straightforward subprocess work following the existing TLC/verification.py pattern.

## Sources

- Codebase: `evaluation.py` (Evaluator/runner interface), `pipeline.py` (PipelineRunner.run signature), `verification.py` (available() pattern), `loop.py` (gate sequence), `archive.py` (ArchiveEntry fields)
- Decisions: D044 (Docker not subprocess restrictions), D045 (container reuse per iteration), D043 (graceful degradation), D014 (compile+exec for pipeline loading)
- M003-RESEARCH: sandbox section covering startup latency, file isolation, network policy
- Prior slice summaries: S01 (TLAVerifier pattern), S02 (Pareto integration), S03 (LeakageChecker pattern, gate sequence)
