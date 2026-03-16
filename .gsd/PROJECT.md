# Project

## What This Is

AutoAgent is an autonomous optimization agent. You launch it in any repo, describe what you want to improve, and it loops forever — editing `pipeline.py`, running `prepare.py eval`, keeping improvements, discarding failures, logging everything to `results.tsv`. Each experiment lives on its own git branch. The LLM itself is the optimizer — no framework in between.

Built as a standalone TUI powered by the Pi SDK. One command to start (`/autoagent go`), one to stop (`/autoagent stop`). Everything else is contextual.

## Core Value

The autonomous optimization loop — describe what you want to improve, walk away, come back to genuine improvements with a clean git history of what was tried and what worked.

## Current State

M001-M005 built a Python optimization framework (OptimizationLoop, MetaAgent, Evaluator, Archive, etc.) with 502 tests against MockLLM. The system never performed a real optimization. Recent commits pivoted toward the autoresearch model: the LLM itself runs the loop via `program.md` protocol. A standalone TUI (`tui/`) exists with onboarding, model selection, and extension loading. M006 completes the pivot — deletes the old framework entirely and wires the autoresearch model end-to-end.

## Architecture / Key Patterns

- **Standalone TUI** via Pi SDK — TypeScript, interactive agent session
- **LLM-as-optimizer** — the agent follows `program.md` protocol directly, no Python intermediary
- **Single mutable file** (`pipeline.py`) — all mutations constrained to one file
- **Fixed evaluator** (`prepare.py`) — scoring function the agent cannot modify
- **Git branches as archive** — `autoagent/<name>` per experiment, keep = advance, discard = revert
- **TSV experiment log** (`results.tsv`) — commit hash, score, status, description
- **Conversational setup** — no rigid interview, LLM helps write prepare.py + baseline through conversation
- **Minimal commands** — `/autoagent go` and `/autoagent stop`, everything else contextual

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [x] M001: Core Loop & Infrastructure — Pipeline execution, CLI, archive, the optimization loop, budget, crash recovery
- [x] M002: Search Intelligence — Structural search, parameter optimization, exploration/exploitation, cold-start, archive compression
- [x] M003: Safety & Verification — TLA+ verification, data leakage guardrail, Pareto evaluation, reward hacking defense, sandbox
- [x] M004: Interview & Polish — GSD-2 depth interview, benchmark generation, search space definition, overnight reporting
- [x] M005: Pi TUI Extension — Interactive dashboard, live loop monitoring, interview overlay, reporting overlay via pi extension
- [ ] M006: Autoresearch Pivot — Delete old framework, wire LLM-as-optimizer end-to-end, conversational setup, multi-experiment, dashboard
