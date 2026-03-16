# M006: Autoresearch Pivot

**Gathered:** 2026-03-15
**Status:** Ready for planning

## Project Description

M006 completes the pivot from a Python optimization framework to the autoresearch model. The entire old codebase (OptimizationLoop, MetaAgent, Evaluator, Archive, 502 tests, etc.) is deleted. In its place: the LLM itself runs the optimization loop by following `program.md` — reading code, editing `pipeline.py`, running `prepare.py eval`, keeping or reverting via git. The standalone TUI provides conversational setup, minimal commands, and a dashboard that tracks progress by reading `results.tsv` from disk.

## Why This Milestone

The old framework was fully built but never ran a real optimization — 502 tests against MockLLM proved nothing. The autoresearch model (already partially implemented in recent commits) is simpler and more powerful: the LLM's own intelligence — web search, code understanding, reasoning — IS the search strategy. No framework can match that. M006 finishes the job.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Launch `autoagent` in any repo, describe what they want to optimize, and get a working prepare.py + baseline pipeline.py through conversation
- Run `/autoagent go` and walk away — the LLM iterates forever, editing pipeline.py, evaluating, keeping improvements
- See experiment progress in a dashboard overlay (Ctrl+Alt+A) — iterations, scores, keeps/discards
- Run multiple experiments on separate git branches in the same repo
- Come back to a clean git history showing exactly what was tried and what worked

### Entry point / environment

- Entry point: `autoagent` CLI (standalone TUI)
- Environment: local dev (terminal), any repo
- Live dependencies involved: LLM provider (via Pi SDK), git

## Completion Class

- Contract complete means: old framework deleted, program.md protocol in place, TUI dispatches agent loop
- Integration complete means: `/autoagent go` runs a real optimization loop end-to-end with actual LLM calls
- Operational complete means: user launches autoagent, sets up a project through conversation, runs experiments on git branches, sees results in dashboard

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- Old Python framework completely removed — no src/autoagent/, no tests/, no pyproject.toml
- `/autoagent go` starts the LLM following program.md and iterating on pipeline.py with real evaluations
- Conversational setup produces a working prepare.py + pipeline.py from a natural language description
- Multiple experiments on separate git branches with independent results.tsv logs
- Dashboard overlay shows experiment progress by reading results.tsv

## Risks and Unknowns

- **Dashboard tracking without JSONL** — Old dashboard read JSONL events from a subprocess. New model has the LLM doing tool calls directly. Dashboard must watch results.tsv on disk instead. File-watching timing and stale reads are the risk.
- **Evaluator generation quality** — Helping the user write a good prepare.py through conversation is the hardest UX problem. Bad evaluator = worthless optimization.
- **Git branch management** — Creating branches, switching between experiments, not losing uncommitted work. Edge cases around dirty working tree.

## Existing Codebase / Prior Art

- `tui/` — Standalone Pi SDK TUI (loader, cli, onboarding, extension) — survives and is improved
- `tui/src/resources/extensions/autoagent/` — Extension with dashboard, interview, subprocess manager — needs significant rework
- `tui/src/resources/extensions/autoagent/prompts/program.md` — Autoresearch protocol — survives as the core
- `tui/src/resources/extensions/autoagent/prompts/system.md` — System prompt — survives, may be updated
- `tui/src/resources/extensions/autoagent/templates/pipeline.py` — Baseline template — survives
- `src/autoagent/` — Entire Python framework — DELETED
- `tests/` — All 502 tests — DELETED
- `.pi/extensions/autoagent/` — Old Pi extension — DELETED
- `pyproject.toml` — Python build config — DELETED

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions.

## Relevant Requirements

- R101 — Autoresearch loop (primary)
- R102 — Conversational setup
- R103 — Multi-experiment via git branches
- R104 — Live dashboard for agent loop
- R105 — Dead code removal
- R106 — Minimal command surface
- R107 — Results tracking in TSV
- R108 — Simplicity criterion

## Scope

### In Scope

- Delete entire Python framework (src/autoagent/, tests/, pyproject.toml, .pi/extensions/)
- Wire `/autoagent go` to dispatch program.md protocol to LLM
- Conversational project setup (prepare.py + pipeline.py generation)
- Git branch per experiment with keep/discard via git operations
- Dashboard overlay reading results.tsv
- Minimal command surface (go, stop)
- Updated system prompt and session_start header

### Out of Scope / Non-Goals

- Python optimization framework (R109 — explicitly deleted)
- Rigid interview forms (R110 — replaced by conversation)
- TLA+ verification, leakage detection, Pareto evaluation (deleted with framework)
- Sandbox isolation (deleted with framework)
- The old JSONL subprocess streaming model

## Technical Constraints

- Pi SDK TypeScript for TUI — already working
- Git must be available (for branch-per-experiment)
- LLM provider must be configured (onboarding handles this)
- program.md is the single source of truth for loop behavior

## Integration Points

- **Pi SDK** — Agent session, extension API, model registry, auth
- **Git** — Branch per experiment, commit/revert for keep/discard
- **LLM provider** — Via Pi SDK's model registry (already wired)
- **File system** — results.tsv, pipeline.py, prepare.py, program.md

## Open Questions

- **Dashboard file watching** — Poll results.tsv or use fs.watch? Polling is simpler and more portable. Probably 2-second poll interval.
- **Experiment switching UX** — Git checkout or a TUI selector? Probably git checkout is fine — the dashboard can show which branch you're on.
