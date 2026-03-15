# M003: Safety & Verification

**Vision:** Every iteration in the optimization loop passes through four safety gates — TLA+ verification, data leakage detection, multi-metric Pareto evaluation, and sandbox isolation — so the user can trust overnight runs produce honest, safe results.

## Success Criteria

- A pipeline with a known TLA+ invariant violation is caught and rejected before evaluation
- A benchmark with known train/test contamination is detected and the iteration is blocked
- A pipeline that improves primary score but degrades latency or cost is rejected by Pareto evaluation
- A pipeline that attempts host filesystem access outside sandbox is blocked by Docker isolation
- When Java/TLC or Docker are unavailable, the system warns and continues without those gates (graceful degradation)
- All safety gate results are visible in the archive for post-run inspection

## Key Risks / Unknowns

- **TLA+ spec generation quality** — LLMs generating syntactically and semantically correct TLA+ is harder than generating Python. The genefication loop mitigates but could burn tokens on bad specs. This is the milestone's primary uncertainty.
- **Pareto dimensionality** — With too many metrics, nothing dominates anything. Must fix a small metric vector (3-4 dimensions) to keep the check meaningful.
- **Leakage false positives** — Aggressive fuzzy matching could flag legitimate shared vocabulary. Need precise thresholds.
- **Sandbox startup latency** — Docker cold-start per iteration could bottleneck the loop. Must reuse containers.

## Proof Strategy

- TLA+ spec generation quality → retire in S01 by generating and TLC-verifying specs from real pipeline code, with genefication recovering from bad specs
- Pareto dimensionality → retire in S02 by implementing a fixed 4-metric vector with tested tiebreaking on incomparable cases
- Leakage false positives → retire in S03 by separating exact-match blocking from fuzzy-match warnings
- Sandbox startup latency → retire in S04 by reusing one container per iteration across all benchmark examples

## Verification Classes

- Contract verification: pytest tests with MockLLM, mock TLC subprocess, mock Docker — each gate tested in isolation and wired into the loop
- Integration verification: TLC subprocess (Java) and Docker subprocess exercised via integration tests when available, skipped gracefully when not
- Operational verification: graceful degradation when Java/Docker missing, budget tracking for safety layer costs
- UAT / human verification: none — all gates produce machine-verifiable results

## Milestone Definition of Done

This milestone is complete only when all are true:

- All four safety gates (TLA+, Pareto, leakage, sandbox) are implemented and wired into the optimization loop
- Each gate has unit tests proving its contract (detect/reject known bad inputs)
- Graceful degradation works — system runs without Java/Docker, logging warnings
- Safety gate costs (LLM calls for spec generation, leakage analysis) are tracked against budget_usd
- Archive entries include verification results (TLA+ pass/fail, leakage status, Pareto decision rationale)
- Final integrated acceptance: all four gates active in one `autoagent run` invocation, each exercised
- All prior tests (267) continue passing — zero regressions

## Requirement Coverage

- Covers: R014 (TLA+ Verification), R010 (Pareto Evaluation), R020 (Simplicity Criterion), R009 (Data Leakage), R021 (Sandbox Isolation)
- Partially covers: none
- Leaves for later: R007, R011, R012, R013, R018, R023, R024 (all mapped to M004 or deferred for live validation)
- Orphan risks: none

## Slices

- [x] **S01: TLA+ Verification Gate** `risk:high` `depends:[]`
  > After this: `autoagent run` generates a TLA+ spec for each proposed pipeline, runs TLC model checker, and rejects proposals that fail verification — proven with mock TLC subprocess and unit tests. When Java/TLC is unavailable, the gate is skipped with a warning.
- [ ] **S02: Pareto Evaluation with Simplicity Criterion** `risk:medium` `depends:[]`
  > After this: the keep/discard decision uses Pareto dominance across (primary_score, latency, cost, complexity) instead of single-score comparison. Pipelines that game one metric at the expense of others are rejected. Incomparable pipelines resolved by preferring simpler code.
- [ ] **S03: Data Leakage Detection** `risk:medium` `depends:[]`
  > After this: every evaluation is preceded by a leakage check — exact train/test example overlap blocks the iteration, fuzzy n-gram overlap generates a warning. Proven with synthetic contaminated benchmarks in tests.
- [ ] **S04: Sandbox Isolation & Final Assembly** `risk:medium` `depends:[S01,S02,S03]`
  > After this: pipeline code executes inside a Docker container with restricted filesystem and filtered network access. When Docker is unavailable, execution falls back to direct mode with a warning. Final integrated verification: all four safety gates active in one loop run, each exercised and producing archive-visible results.

## Boundary Map

### S01 → downstream

Produces:
- `verification.py` — `TLAVerifier` class with `verify(source: str) -> VerificationResult` and `VerificationResult` frozen dataclass (passed: bool, violations: list[str], spec_text: str, attempts: int, cost_usd: float)
- `ArchiveEntry` gains optional `tla_verification: dict | None` field (backward-compatible)
- Loop gate: TLA+ check after `propose()`, before evaluation — failed verification → discard with rationale
- Graceful degradation: `TLAVerifier.available() -> bool` class method checks for Java/TLC

Consumes:
- `meta_agent.py` `MetaAgent` — configured LLM for spec generation
- `loop.py` — insertion point after proposal validation
- `archive.py` `ArchiveEntry` — new optional field

### S02 → downstream

Produces:
- `pareto.py` — `pareto_dominates(a, b, metrics) -> bool`, `pareto_decision(candidate, current_best) -> ParetoResult` pure functions, `ParetoResult` frozen dataclass (decision: str, rationale: str), `compute_complexity(source: str) -> float` function
- Loop integration: Pareto check replaces `score >= best_score` at keep/discard decision point

Consumes:
- `types.py` `MetricsSnapshot` — metric vector for Pareto comparison
- `evaluation.py` `EvaluationResult` — primary_score + metrics
- `loop.py` — keep/discard decision point (~L334)

### S03 → downstream

Produces:
- `leakage.py` — `LeakageChecker` class with `check(benchmark, pipeline_source) -> LeakageResult`, `LeakageResult` frozen dataclass (blocked: bool, exact_matches: int, fuzzy_warnings: list[str], cost_usd: float)
- Loop gate: leakage check before evaluation — blocked → discard with rationale
- `ArchiveEntry` gains optional `leakage_check: dict | None` field

Consumes:
- `benchmark.py` `Benchmark` — examples with input/expected
- `loop.py` — insertion point before evaluation

### S04 → none (final slice)

Produces:
- `sandbox.py` — `SandboxRunner` class wrapping `PipelineRunner.run()` in Docker container, `SandboxRunner.available() -> bool`
- Network policy: allow outbound HTTPS to configured provider domains
- Container reuse per iteration (one container runs all examples)
- Graceful degradation: falls back to direct `PipelineRunner` when Docker unavailable
- Final integration: all four gates wired and exercised together

Consumes:
- `pipeline.py` `PipelineRunner` — execution target to wrap
- `evaluation.py` `Evaluator._run_with_timeout()` — sandbox replaces direct execution
- S01 `TLAVerifier`, S02 `pareto_decision`, S03 `LeakageChecker` — all gates active for integration test
