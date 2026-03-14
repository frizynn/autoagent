# M003: Safety & Verification — Context

**Gathered:** 2026-03-14
**Status:** Ready for planning (after M002)

## Project Description

M003 adds the safety rails that make autoagent trustworthy for unattended overnight runs. TLA+ verification catches broken coordination protocols before burning eval tokens. Data leakage detection ensures benchmarks are honest. Multi-metric Pareto evaluation prevents reward hacking. Sandbox isolation protects the host from model-generated code. Without M003, the system works but you can't fully trust its results or safety.

## Why This Milestone

The user's top concerns are reward hacking and data leakage — waking up to "improvements" that are actually gaming metrics or contaminated benchmarks. TLA+ verification is unique to autoagent (no other architecture search system does this) and catches an entire class of bugs before evaluation. Sandbox isolation is table stakes for executing untrusted code overnight.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Trust that every iteration was checked for data leakage before benchmarking
- See TLA+ verification results in the archive — which pipelines passed model-checking, which had violations
- Trust that improvements are real — Pareto evaluation rejects changes that game one metric at expense of others
- Sleep peacefully knowing pipeline code runs in a sandbox

### Entry point / environment

- Entry point: `autoagent run` (same CLI, new safety layers integrated)
- Environment: local dev (terminal), sandbox environment for pipeline execution
- Live dependencies involved: TLC (TLA+ model checker), LLM APIs

## Completion Class

- Contract complete means: TLA+ specs compile and verify, leakage checks detect known contamination patterns, Pareto rejection works
- Integration complete means: safety layers are wired into the optimization loop — TLA+ gate before eval, leakage check before scoring, Pareto check before keep/discard
- Operational complete means: sandbox isolates pipeline execution from host

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- A pipeline with a known concurrency bug (deadlock, race) is caught by TLA+ verification and rejected before evaluation
- A benchmark with known data leakage is detected and the iteration is blocked
- A pipeline that improves accuracy but doubles latency is rejected by Pareto evaluation
- Pipeline code that attempts filesystem access outside sandbox is blocked

## Risks and Unknowns

- **TLA+ spec generation quality** — Can an LLM reliably generate correct TLA+ specs from Python pipeline code? The genefication pattern (iterate until TLC passes) mitigates this, but initial spec quality affects iteration count.
- **TLA+ for sequential pipelines** — Useful properties to check for non-concurrent code (termination, no infinite loops) are less natural in TLA+ than concurrency properties. May need to define a standard property set.
- **Data leakage detection completeness** — Mechanical checks catch obvious contamination (train examples in test set) but subtle leakage (feature leakage, temporal leakage) may need LLM-assisted analysis.
- **Sandbox overhead** — Isolation adds latency to every evaluation. Must not make the loop impractically slow.

## Existing Codebase / Prior Art

- M001/M002 deliverables: full optimization loop with intelligent search
- TLA+ tools (TLC model checker) — runs via Java subprocess
- Genefication pattern — LLM drafts TLA+ spec, TLC verifies, iterate on violations
- AWS TLA+ paper — formal methods at scale, practical application
- ADAS safety warning — "executing untrusted model-generated code"

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions.

## Relevant Requirements

- R009 — Data leakage guardrail (every step)
- R010 — Multi-metric Pareto evaluation
- R014 — TLA+ verification for all pipelines
- R020 — Simplicity criterion
- R021 — Sandbox isolation
- R022 — Fixed evaluation time budget (reinforced by sandbox timeout)

## Scope

### In Scope

- TLA+ spec generation from pipeline code (all pipelines, not just concurrent)
- TLC model-checking gate before evaluation
- Genefication loop (LLM drafts → TLC verifies → iterate)
- Data leakage detection (mechanical + LLM-assisted)
- Multi-metric Pareto evaluation and reward hacking defense
- Simplicity criterion (reject complexity-for-marginal-gain)
- Sandbox isolation for pipeline execution

### Out of Scope / Non-Goals

- Formal verification of the meta-agent itself (only pipelines are verified)
- Full security audit of sandbox (defense in depth, not perfect isolation)

## Technical Constraints

- TLC requires Java runtime — must be available or installable
- TLA+ specs must be generated fast enough to not bottleneck the loop
- Sandbox must support LLM API calls from within (pipeline needs network access to providers)
- Leakage checks must work with arbitrary user-provided benchmark formats

## Integration Points

- **TLC** — Java subprocess for model-checking TLA+ specs
- **M001/M002 optimization loop** — safety layers insert as gates in the propose→verify→eval→keep pipeline
- **M001 archive** — verification results stored alongside metrics and diffs
- **LLM APIs** — for spec generation (genefication) and leakage analysis

## Open Questions

- **Sandbox technology** — Docker containers? Python subprocess with restricted permissions? Firecracker? Trade-off between isolation strength and setup complexity. Leaning Docker for pragmatism.
- **TLA+ property vocabulary** — What standard properties does every pipeline spec check? Termination, no deadlock, eventually-produces-output, bounded resource usage? Need to define the standard set.
- **Leakage check granularity** — Check at data level (train/test overlap), feature level (information flow), or both? Starting with data-level is tractable; feature-level leakage is harder.
