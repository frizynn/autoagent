# Project

## What This Is

AutoAgent is an autonomous optimization system that iteratively discovers better agentic architectures for a user-specified goal. It takes a goal like "improve RAG effectiveness" or "minimize pipeline latency" and runs an infinite loop: a meta-agent reads the full archive of past attempts, proposes a modification to `pipeline.py` (the only mutable file), evaluates it against a benchmark, and keeps or discards the change based on metrics and constraints. Built as a PI-based CLI inspired by GSD-2's fully autonomous approach.

Currently: empty scaffold — `pyproject.toml`, smoke test, README.

## Core Value

The autonomous optimization loop — fire-and-forget overnight, wake up to genuine improvements with a clean archive of what was tried, why, and what worked.

## Current State

Pre-alpha scaffold. Package structure exists (`src/autoagent/`), dev tooling configured (ruff, mypy, pytest), CI on GitHub Actions. No functional code yet.

## Architecture / Key Patterns

- **Python 3.11+**, hatchling build system
- **PI SDK** for CLI harness (GSD-2 style)
- **Single mutable file** (`pipeline.py`) — all mutations constrained to one file per autoresearch pattern
- **Disk-based state** (`.autoagent/` directory) — crash-recoverable, no in-memory state
- **Instrumented primitives** (LLM, Retriever, Tool, Agent) with auto-measurement
- **Provider-agnostic** — meta-agent powered by user's coding agent subscription, pipelines call separate LLM/retrieval APIs

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [ ] M001: Core Loop & Infrastructure — Pipeline execution, CLI, archive, the optimization loop, budget, crash recovery
- [ ] M002: Search Intelligence — Structural search, parameter optimization, exploration/exploitation, cold-start, archive compression
- [ ] M003: Safety & Verification — TLA+ verification, data leakage guardrail, Pareto evaluation, reward hacking defense, sandbox
- [ ] M004: Interview & Polish — GSD-2 depth interview, benchmark generation, search space definition, overnight reporting
