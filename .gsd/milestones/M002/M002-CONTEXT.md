# M002: Search Intelligence — Context

**Gathered:** 2026-03-14
**Status:** Ready for planning (after M001)

## Project Description

M002 makes the meta-agent actually intelligent. M001 proves the loop works; M002 makes it produce genuinely novel and improving architectures. This is where structural search (topology mutations), parameter optimization (DSPy/Optuna-style), exploration/exploitation balance, cold-start generation, and archive compression live. This milestone is the make-or-break — user's #1 risk concern is search intelligence.

## Why This Milestone

A loop that proposes random mutations isn't useful. The archive must inform increasingly smart proposals. The meta-agent must know when to explore new topologies vs. tune the current best. Without this, the user wakes up to 100 iterations of noise instead of genuine improvement.

## User-Visible Outcome

### When this milestone is complete, the user can:

- See the meta-agent propose topology changes (not just parameter tweaks) — swap RAG→CAG, add rerankers, introduce parallel agents
- Observe convergence: metrics trend improving over 20+ iterations, with structural breakthroughs visible in the archive
- Start from nothing: provide only a goal + benchmark data, and autoagent generates the first pipeline and begins optimizing
- See intelligent archive summarization: the meta-agent references patterns from past failures and builds on past successes

### Entry point / environment

- Entry point: `autoagent run` CLI (same as M001, but smarter)
- Environment: local dev (terminal)
- Live dependencies involved: LLM APIs, user's benchmark data

## Completion Class

- Contract complete means: structural mutations produce valid pipelines, parameter optimization measurably improves metrics, archive compression fits context window
- Integration complete means: the full search stack runs end-to-end over 20+ iterations with visible improvement trends
- Operational complete means: cold-start works, exploration/exploitation switching is visible in archive

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- Cold-start: given only a goal and benchmark, autoagent generates initial pipeline and improves it over 10+ iterations
- Structural search: at least one topology change (not just parameter tweak) that improves metrics is discovered autonomously
- Archive at 50+ iterations still produces coherent, context-window-fitting summaries that inform proposals

## Risks and Unknowns

- **Search intelligence quality** — Can the meta-agent propose genuinely novel architectures, or will it shuffle the same patterns? This is the core product risk.
- **Exploration/exploitation** — How to detect stagnation and switch modes without oscillating? Academic problem with no clean solution.
- **Archive compression fidelity** — Compressing 200 iterations into a summary that preserves the right signals is hard. Lossy compression could throw away the insight that would have led to the breakthrough.
- **DSPy integration** — DSPy's MIPROv2 optimizer expects specific module structures. Bridging autoagent's pipeline model to DSPy's may be non-trivial.

## Existing Codebase / Prior Art

- M001 deliverables: pipeline execution engine, primitives, archive, basic meta-agent loop
- ADAS (Meta Agent Search) — meta-agent programs new agents in code based on previous discoveries
- DSPy MIPROv2 — optimizer for prompt tuning with teacher models
- Optuna — Bayesian hyperparameter optimization
- autoresearch — "if you run out of ideas, think harder — read papers, try combining previous near-misses, try more radical architectural changes"

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions.

## Relevant Requirements

- R011 — Structural search (primary)
- R012 — Parameter optimization
- R013 — Autonomous search strategy
- R015 — Cold-start pipeline generation
- R016 — Archive compression for scale
- R024 — Exploration/exploitation balance

## Scope

### In Scope

- Structural search strategies (topology mutations, component swaps)
- Parameter optimization (prompt tuning, hyperparameter search)
- Exploration/exploitation balance mechanisms
- Cold-start pipeline generation from goal + benchmark
- Archive compression and intelligent summarization
- Meta-agent prompting that references archive patterns

### Out of Scope / Non-Goals

- TLA+ verification of proposed pipelines (M003)
- Data leakage checks (M003)
- Reward hacking defense (M003)
- Interview phase (M004)

## Technical Constraints

- Must build on M001's pipeline execution engine and archive format
- Archive compression must be lossless enough to preserve breakthrough signals
- Cold-start pipelines must use instrumented primitives (R003)
- Provider-agnostic — search strategies can't assume specific LLM providers

## Integration Points

- **M001 Archive** — reads and writes iterations, summaries
- **M001 Primitives** — generated pipelines must use these
- **DSPy** (potential) — for parameter optimization
- **Optuna** (potential) — for Bayesian hyperparameter search

## Open Questions

- **DSPy vs. custom parameter optimization** — Is DSPy's MIPROv2 the right tool, or should we build lighter-weight prompt tuning? DSPy adds a heavy dependency. Leaning toward DSPy-inspired but not DSPy-dependent.
- **Structural mutation grammar** — How does the meta-agent know what topology changes are valid? Does it have a vocabulary of components, or does it free-form generate code? ADAS uses free-form code generation.
- **Stagnation detection** — What signals indicate the search is stuck? Plateau in primary metric? High variance with no improvement? Need to define this precisely.
