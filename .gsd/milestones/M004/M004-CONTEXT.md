# M004: Interview & Polish — Context

**Gathered:** 2026-03-14
**Status:** Ready for planning (after M003)

## Project Description

M004 completes the user experience. The GSD-2-depth interview phase captures everything the system needs before the first optimization cycle: goal, metrics, constraints, search space, benchmark validation. Automatic benchmark generation handles the cold case where the user has no evaluation data. Overnight reporting delivers the "wake up surprised" experience — a clear summary of what improved, what was tried, and what to do next.

## Why This Milestone

M001-M003 build a powerful but raw system. Without the interview, users must manually configure everything. Without benchmark generation, users without existing eval data can't use the system. Without reporting, the "fire-and-forget" experience is incomplete — you come back to raw archive data instead of a clear story.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Run `autoagent new` and be guided through a deep interview that probes their goal, investigates their codebase, and builds a complete optimization spec
- Start optimization with no existing benchmark — the system creates one and validates it for leakage
- Wake up to a clear report: what improved, best architecture found, metric trends, notable failures, recommendations
- Experience the full flow: interview → setup → overnight optimization → morning report

### Entry point / environment

- Entry point: `autoagent new` (interview), `autoagent run` (optimization), `autoagent report` (results)
- Environment: local dev (terminal)
- Live dependencies involved: LLM APIs, user's codebase, user's data

## Completion Class

- Contract complete means: interview produces valid optimization spec, benchmark generator creates scored datasets, reports summarize optimization runs
- Integration complete means: full flow works end-to-end: `autoagent new` → interview → benchmark → `autoagent run` → iterations → report
- Operational complete means: the "wake up surprised" experience works in practice — real overnight run with morning report

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- Full cold-start flow: user provides only a vague goal and some data, interview refines it, benchmark is generated, optimization runs 20+ iterations, morning report shows genuine improvement
- Interview catches a specification gap that would have led to wasted optimization (e.g., missing constraint, ambiguous metric)
- Report correctly summarizes an overnight run with clear before/after comparison

## Risks and Unknowns

- **Interview quality** — GSD-2's interview works because the domain (software development) is well-understood. Optimization goals are more varied — "improve RAG effectiveness" vs "minimize pipeline latency" vs "maximize code generation accuracy" require different interview strategies.
- **Benchmark generation quality** — Automatically generating meaningful evaluation data from a vague goal is hard. The generated benchmark must actually measure what the user cares about.
- **Report narrative** — Turning 100 iterations of metrics into a compelling "here's what happened" story requires good summarization and trend detection.

## Existing Codebase / Prior Art

- M001-M003 deliverables: complete optimization system with safety rails
- GSD-2 interview phase — probes gray areas, investigates codebase, challenges vagueness
- autoresearch `results.tsv` — simple tabular logging of experiments

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions.

## Relevant Requirements

- R007 — GSD-2 depth interview phase (primary)
- R023 — Automatic benchmark generation
- R009 — Data leakage guardrail (benchmark generation must pass leakage checks)
- R019 — Fire-and-forget operation (completed by morning report)

## Scope

### In Scope

- Interview orchestrator with GSD-2-depth interrogation
- Benchmark discovery and generation (when user provides none)
- Search space definition from interview
- Overnight reporting (what improved, metrics, best architecture, recommendations)
- Full end-to-end polish of the user experience

### Out of Scope / Non-Goals

- Real-time monitoring dashboard (user said fire-and-forget, not live dashboard)
- Web UI (CLI only)
- Multi-user support

## Technical Constraints

- Interview must work within PI's agent session model
- Generated benchmarks must be compatible with M001's evaluation framework
- Reports must be readable in terminal (markdown or structured text)

## Integration Points

- **M001-M003** — Full optimization system
- **User's codebase** — Interview investigates existing code
- **User's data** — Benchmark generation uses available data
- **LLM APIs** — Interview and benchmark generation use LLM calls

## Open Questions

- **Interview → spec format** — What does the interview produce? A structured config file? A context document? Leaning toward a structured spec (YAML/TOML) that the optimization loop consumes, plus a context.md for the meta-agent.
- **Benchmark generation strategies** — For different goal types (accuracy, latency, cost), what does generated evaluation data look like? This likely needs domain-specific strategies.
- **Report delivery** — Terminal output? Generated markdown file? Both? Leaning toward a generated markdown file + terminal summary.
