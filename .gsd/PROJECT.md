# Project

## What This Is

AutoAgent is an autonomous optimization system that iteratively discovers better agentic architectures for a user-specified goal. It takes a goal like "improve RAG effectiveness" or "minimize pipeline latency" and runs an infinite loop: a meta-agent reads the full archive of past attempts, proposes a modification to `pipeline.py` (the only mutable file), evaluates it against a benchmark, and keeps or discards the change based on metrics and constraints. Built as a Python CLI inspired by GSD-2's fully autonomous approach.

## Core Value

The autonomous optimization loop — fire-and-forget overnight, wake up to genuine improvements with a clean archive of what was tried, why, and what worked.

## Current State

M001 through M004 complete. The full user experience is implemented:
- `autoagent new` runs a multi-turn LLM-driven interview that challenges vague input, collects goal/metrics/constraints/search space/benchmark/budget, and writes `config.json` + `context.md` to `.autoagent/`.
- When no benchmark is provided, `BenchmarkGenerator` auto-generates `{input, expected}` JSON from the goal, validates for leakage and diversity, and writes `benchmark.json`.
- `autoagent run` executes the optimization loop with safety gates (TLA+ → leakage → sandbox evaluation → Pareto keep/discard).
- `autoagent report` generates a structured markdown report with score trajectory, top architectures, cost breakdown, and recommendations.
- Full cold-start flow proven end-to-end with MockLLM: interview → benchmark generation → optimization loop → report.
- 469 tests passing. 19 requirements validated, 5 active (M002 search intelligence scope).

## Architecture / Key Patterns

- **Python 3.11+**, hatchling build system
- **Standard Python CLI** via argparse (GSD-2 style commands: init, run, status, new, report)
- **Single mutable file** (`pipeline.py`) — all mutations constrained to one file per autoresearch pattern
- **Disk-based state** (`.autoagent/` directory) — crash-recoverable, no in-memory state
- **Instrumented primitives** (LLM, Retriever, Tool, Agent) with auto-measurement via MetricsCollector
- **Provider-agnostic** — Protocol-based contracts; MockLLM/OpenAILLM prove the pattern
- **Dynamic module loading** via compile()+exec() — guarantees fresh loads, no bytecode cache
- **Never-raise runner** — PipelineRunner returns structured PipelineResult on all paths
- **Budget auto-pause** — hard ceiling with pre-iteration cost estimation
- **Archive-based recovery** — resume reconstructs best_score and restores pipeline.py from archive
- **Safety gate sequence** — TLA+ → leakage → evaluation (with sandbox) → Pareto keep/discard
- **Graceful degradation** — safety gates skip with warnings when Java/Docker unavailable
- **Multi-turn interview** — LLM-driven with vague-input detection and follow-up probes
- **Automatic benchmark generation** — LLM-generated {input, expected} with leakage + diversity validation
- **Composable report sections** — independently callable functions for targeted inspection

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [x] M001: Core Loop & Infrastructure — Pipeline execution, CLI, archive, the optimization loop, budget, crash recovery
- [x] M002: Search Intelligence — Structural search, parameter optimization, exploration/exploitation, cold-start, archive compression
- [x] M003: Safety & Verification — TLA+ verification, data leakage guardrail, Pareto evaluation, reward hacking defense, sandbox
- [x] M004: Interview & Polish — GSD-2 depth interview, benchmark generation, search space definition, overnight reporting
- [ ] M005: Pi TUI Extension — Interactive dashboard, live loop monitoring, interview overlay, reporting overlay via pi extension

## Known Gaps

- Real LLM provider wiring — `cmd_new` defaults to `MockLLM()`, real provider selection not wired
- Benchmark path resolution inconsistency between `cmd_new` (relative) and `cmd_run` (absolute)
- M002 search intelligence requirements (R011, R012, R013, R024) are active but mapped — await future milestone
