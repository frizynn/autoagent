# M001: Core Loop & Infrastructure — Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

## Project Description

AutoAgent is an autonomous optimization system that runs an infinite propose→evaluate→keep/discard loop to discover better agentic architectures. M001 builds the foundation: the pipeline execution engine, CLI, archive, the core optimization loop, budget management, and crash recovery. By the end of M001, `autoagent run` works end-to-end.

## Why This Milestone

Everything else depends on a working loop. Without the ability to execute a pipeline, measure it, archive the result, and propose a mutation, there's nothing to optimize. M001 proves the core mechanism works before investing in search intelligence (M002), safety (M003), or polish (M004).

## User-Visible Outcome

### When this milestone is complete, the user can:

- Run `autoagent init` to scaffold a project with pipeline.py, benchmark config, and .autoagent/ state directory
- Run `autoagent run --goal "improve accuracy" --budget 5.00` and walk away
- Come back to find multiple iterations in the archive with metrics, diffs, and keep/discard decisions
- Kill the process at any point and restart without losing progress

### Entry point / environment

- Entry point: `autoagent` CLI (PI-based)
- Environment: local dev (terminal)
- Live dependencies involved: LLM API providers (OpenAI, Anthropic, etc.), user's benchmark data

## Completion Class

- Contract complete means: pipeline execution captures metrics, archive stores iterations, loop proposes and evaluates mutations, budget pauses the loop
- Integration complete means: the full init→run→archive→iterate cycle works with real LLM calls against a real benchmark
- Operational complete means: crash recovery works (kill mid-iteration, restart, resume)

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- `autoagent run` completes ≥3 autonomous iterations with real LLM calls, producing archive entries with metrics and diffs
- Kill the process mid-iteration, restart, and it resumes from disk state without re-running completed iterations
- Budget ceiling triggers auto-pause before the configured limit is exceeded

## Risks and Unknowns

- **Pipeline execution model** — Loading arbitrary Python, executing it safely, capturing structured metrics. The single-file constraint helps but we still need reliable execution and measurement.
- **Meta-agent mutation quality** — Even basic mutations need to produce valid, runnable Python that uses the instrumented primitives. M001 needs basic mutation capability (M002 makes it intelligent).
- **PI SDK integration** — Building a CLI on PI that works like GSD-2. Need to understand PI's extension/command model.
- **Provider-agnostic primitives** — Supporting multiple LLM/retrieval providers without the primitives becoming a framework.

## Existing Codebase / Prior Art

- `src/autoagent/__init__.py` — Empty package, version only
- `pyproject.toml` — Python 3.11+, hatchling, dev deps (ruff, mypy, pytest)
- `tests/test_smoke.py` — Package import test only
- No functional code exists yet

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions — it is an append-only register; read it during planning, append to it during execution.

## Relevant Requirements

- R001 — Autonomous optimization loop (primary)
- R002 — Single-file mutation constraint
- R003 — Instrumented primitives with auto-measurement
- R004 — Monotonic archive
- R005 — Crash-recoverable disk state
- R006 — PI-based CLI
- R008 — Benchmark-driven evaluation
- R017 — Hard budget ceiling with auto-pause
- R018 — Provider-agnostic primitives
- R019 — Fire-and-forget operation
- R022 — Fixed evaluation time budget

## Scope

### In Scope

- Pipeline execution engine with instrumented primitives
- CLI commands: `init`, `run`, `status`
- Disk-based state in `.autoagent/`
- Benchmark loading and multi-metric evaluation
- Monotonic archive with metrics, diffs, rationale
- Basic meta-agent loop (propose→evaluate→keep/discard)
- Hard budget ceiling with auto-pause
- Crash recovery from disk state
- Provider-agnostic primitive interfaces

### Out of Scope / Non-Goals

- Intelligent search strategies (M002)
- TLA+ verification (M003)
- Data leakage detection (M003)
- Multi-metric Pareto evaluation (M003 — M001 collects metrics, M003 enforces Pareto)
- Deep interview phase (M004)
- Benchmark generation (M004)
- Cold-start pipeline generation (M002)
- Sandbox isolation (M003)

## Technical Constraints

- Python 3.11+ (already set in pyproject.toml)
- Must work with user's existing coding agent subscription (Claude Code Max, Codex) as the meta-agent LLM
- Pipeline primitives must be provider-agnostic
- All state on disk — no databases, no in-memory-only state
- Single mutable file constraint for pipeline mutations

## Integration Points

- **LLM APIs** (OpenAI, Anthropic, etc.) — Pipeline primitives call these for inference
- **PI SDK** — CLI harness, agent session management
- **Git** — Archive stores diffs; crash recovery may use git state
- **User's benchmark data** — Loaded from disk, scored by user-provided or convention-based scoring function

## Open Questions

- **PI extension model** — How exactly does a PI-based CLI extension work? Need to investigate PI SDK docs during S02 research.
- **Primitive abstraction depth** — How thin should the LLM/Retriever/Tool/Agent primitives be? Thin wrappers that add instrumentation, or richer abstractions? Leaning thin — avoid becoming a framework (R030).
- **Archive format** — JSON per iteration? SQLite? Directory of files? Leaning directory-of-files for crash recovery and human readability.
- **Meta-agent invocation** — Does the meta-agent run as a PI agent session (like GSD-2 dispatches tasks), or as a direct LLM API call? PI session gives richer tool access but adds complexity.
