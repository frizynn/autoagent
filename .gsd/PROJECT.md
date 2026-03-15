# Project

## What This Is

AutoAgent is an autonomous optimization system that iteratively discovers better agentic architectures for a user-specified goal. It takes a goal like "improve RAG effectiveness" or "minimize pipeline latency" and runs an infinite loop: a meta-agent reads the full archive of past attempts, proposes a modification to `pipeline.py` (the only mutable file), evaluates it against a benchmark, and keeps or discards the change based on metrics and constraints. Built as a Python CLI inspired by GSD-2's fully autonomous approach.

## Core Value

The autonomous optimization loop — fire-and-forget overnight, wake up to genuine improvements with a clean archive of what was tried, why, and what worked.

## Current State

M001 and M002 complete. M003 complete — all four safety gates implemented and proven: S01 (TLA+ Verification Gate), S02 (Pareto Evaluation with Simplicity Criterion), S03 (Data Leakage Detection), S04 (Sandbox Isolation & Final Assembly). The optimization loop now has four safety gates: TLA+ verification rejects proposals that fail model checking, Pareto dominance across (primary_score, latency, cost, complexity) rejects reward-hacking, leakage detection blocks train/test contamination before evaluation, and sandbox isolation executes pipeline code inside Docker containers with graceful fallback. All four gates produce archive-visible results. 381 tests passing. 17 requirements validated (R001-R006, R008-R010, R014-R017, R019-R022).

Next: M004 (Interview & Polish).

## Architecture / Key Patterns

- **Python 3.11+**, hatchling build system
- **Standard Python CLI** via argparse (GSD-2 style commands: init, run, status)
- **Single mutable file** (`pipeline.py`) — all mutations constrained to one file per autoresearch pattern
- **Disk-based state** (`.autoagent/` directory) — crash-recoverable, no in-memory state
- **Instrumented primitives** (LLM, Retriever, Tool, Agent) with auto-measurement via MetricsCollector
- **Provider-agnostic** — Protocol-based contracts; MockLLM/OpenAILLM prove the pattern
- **Dynamic module loading** via compile()+exec() — guarantees fresh loads, no bytecode cache
- **Never-raise runner** — PipelineRunner returns structured PipelineResult on all paths
- **Budget auto-pause** — hard ceiling with pre-iteration cost estimation
- **Archive-based recovery** — resume reconstructs best_score and restores pipeline.py from archive

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [x] M001: Core Loop & Infrastructure — Pipeline execution, CLI, archive, the optimization loop, budget, crash recovery
- [x] M002: Search Intelligence — Structural search, parameter optimization, exploration/exploitation, cold-start, archive compression
- [x] M003: Safety & Verification — TLA+ verification, data leakage guardrail, Pareto evaluation, reward hacking defense, sandbox
- [ ] M004: Interview & Polish — GSD-2 depth interview, benchmark generation, search space definition, overnight reporting
