---
id: M003
provides:
  - TLAVerifier with genefication loop for TLA+ spec generation and TLC model-checking
  - Pareto evaluation with 4-metric dominance (primary_score, latency, cost, complexity) and simplicity tiebreaker
  - LeakageChecker with two-tier detection (exact-match blocking + fuzzy n-gram warnings)
  - SandboxRunner with Docker container isolation (--network=none, docker cp, container reuse)
  - Four safety gates wired into OptimizationLoop in sequence: TLA+ → leakage → evaluation (with sandbox) → Pareto keep/discard
  - Archive-visible results for all gates (tla_verification, leakage_check, sandbox_execution, pareto_evaluation fields)
  - Graceful degradation when Java/TLC or Docker unavailable
key_decisions:
  - D042 — Simplicity as Pareto dimension, not separate gate
  - D043 — Graceful degradation for missing system tools (TLC, Docker)
  - D044 — Docker for sandbox, not subprocess restrictions
  - D045 — Container reuse per iteration, not per example
  - D046 — Exact match blocks, fuzzy match warns for leakage
  - D047 — TLA+ complexity threshold skip for trivial pipelines
  - D048 — Genefication iteration cap (max 3 attempts)
  - D049 — AST-based complexity scoring with weighted branch nodes
  - D050 — Pareto degrades to score-only when metrics are None/zero
  - D051 — Container-side harness as string constant, copied via docker cp
  - D052 — Sandbox metadata captured at loop level
patterns_established:
  - Self-contained checker/runner modules with frozen result dataclasses (verification.py, leakage.py, pareto.py, sandbox.py)
  - available() static method pattern for graceful degradation (TLAVerifier, SandboxRunner)
  - Optional gate parameters on OptimizationLoop with consistent discard-on-failure behavior
  - ArchiveEntry field addition pattern (optional field with None default, backward-compatible from_dict via .get())
  - Mock checker/verifier/runner test patterns for predetermined result sequences
observability_surfaces:
  - tla_verification dict in archive JSON — passed, violations, attempts, cost_usd, skipped, skip_reason
  - leakage_check dict in archive JSON — blocked, exact_matches, fuzzy_warnings, cost_usd
  - pareto_evaluation dict in archive JSON — decision, rationale, candidate_metrics, best_metrics
  - sandbox_execution dict in archive JSON — sandbox_used, network_policy, fallback_reason
  - autoagent.verification, autoagent.leakage, autoagent.sandbox loggers for gate lifecycle events
  - WARNING logs when Java or Docker unavailable (graceful degradation)
requirement_outcomes:
  - id: R014
    from_status: active
    to_status: validated
    proof: TLAVerifier generates TLA+ specs via LLM, model-checks via TLC subprocess with genefication retry (max 3 attempts), complexity threshold skip, graceful degradation. 29 unit + 7 integration tests. Contract-level proof in S01.
  - id: R010
    from_status: active
    to_status: validated
    proof: Pareto dominance across 4-metric vector with direction-aware comparison, simplicity tiebreaker for incomparable cases. Replaces score-only comparison in loop. 28 unit tests + loop integration. Contract-level proof in S02.
  - id: R020
    from_status: active
    to_status: validated
    proof: AST-based compute_complexity() with weighted branch nodes. Incomparable Pareto candidates resolved by preferring simpler source. 28 unit tests prove all branches. Contract-level proof in S02.
  - id: R009
    from_status: active
    to_status: validated
    proof: Two-tier detection — AST-based exact-match blocking + word-level n-gram fuzzy warnings. Gate wired after TLA+, before evaluation. 21 unit + 5 integration tests. Contract-level proof in S03.
  - id: R021
    from_status: active
    to_status: validated
    proof: SandboxRunner executes pipeline code inside Docker container with --network=none and docker cp. Graceful fallback when Docker unavailable. 18 unit + 4 integration + 2 capstone tests. Contract-level proof in S04.
duration: 4 slices, 8 tasks
verification_result: passed
completed_at: 2026-03-14
---

# M003: Safety & Verification

**Four safety gates — TLA+ verification, Pareto evaluation, data leakage detection, and Docker sandbox isolation — wired into the optimization loop with graceful degradation, archive-visible results, and a capstone integration test proving all gates work together.**

## What Happened

S01 (high risk) built the TLA+ verification gate. `TLAVerifier` uses an LLM to generate TLA+ specs from pipeline source code, runs TLC via subprocess to model-check them, and blocks proposals that fail verification before they reach evaluation. A genefication loop retries up to 3 times on bad specs (D048). Trivial pipelines (<10 LOC, no control flow) skip verification entirely (D047). When Java/TLC is unavailable, the gate degrades gracefully with a warning (D043). Cost is tracked per verification attempt.

S02 replaced the loop's single-score keep/discard decision with Pareto dominance across four dimensions: primary_score, latency_ms, cost_usd, and complexity. `compute_complexity()` uses AST node counting with weighted branch statements. Incomparable pipelines are resolved by preferring simpler code (D042). The Pareto module degrades to score-only comparison when metrics are None/zero (D050), so all existing MockLLM-based tests continued passing without modification.

S03 added two-tier data leakage detection. `LeakageChecker` extracts string literals from pipeline source via AST, matches them against serialized benchmark examples. Exact matches block the iteration; fuzzy n-gram overlap (Jaccard > 0.3) generates warnings but doesn't block (D046). The gate sits between TLA+ verification and evaluation in the loop sequence.

S04 built `SandboxRunner` wrapping pipeline execution in Docker containers with `--network=none` and source transfer via `docker cp`. A string-constant harness script (D051) handles JSON serialization at the container boundary. When Docker is unavailable, execution falls back to `PipelineRunner` directly. The capstone `test_final_assembly.py` runs a 5-iteration loop where each gate is distinctly exercised: iter 1 passes all gates (baseline), iter 2 fails TLA+, iter 3 is blocked by leakage, iter 4 is Pareto-discarded, iter 5 passes with a simpler pipeline. All gate results verified in archive entries.

All four modules follow the same pattern: self-contained module with frozen result dataclass, optional parameter on `OptimizationLoop`, consistent discard-on-failure behavior, and an optional field on `ArchiveEntry` with backward-compatible deserialization.

## Cross-Slice Verification

| Success Criterion | Status | Evidence |
|---|---|---|
| TLA+ invariant violation caught and rejected before evaluation | ✅ | S01: test_verification.py (29 tests) + test_loop_verification.py (7 tests) — MockTLC returns violations, proposal discarded |
| Benchmark with known train/test contamination detected and blocked | ✅ | S03: test_leakage.py (21 tests) + test_loop_leakage.py (5 tests) — exact match blocks iteration |
| Pipeline improving score but degrading latency/cost rejected by Pareto | ✅ | S02: test_pareto.py (28 tests) — pareto_dominates returns False for single-metric gaming |
| Pipeline attempting host filesystem access blocked by Docker isolation | ✅ | S04: test_sandbox.py (18 tests) — --network=none, docker cp, no bind mounts |
| Graceful degradation when Java/Docker unavailable | ✅ | S01: TLAVerifier.available() → skip with warning; S04: SandboxRunner.available() → fallback to PipelineRunner |
| Safety gate results visible in archive | ✅ | All four gates produce archive-visible dicts: tla_verification, leakage_check, pareto_evaluation, sandbox_execution |
| All four gates active in one run, each exercised | ✅ | test_final_assembly.py: 5-iteration capstone test with all gates wired and individually triggered |
| Zero regressions | ✅ | 381 tests passing (267 baseline → 381), all prior tests unchanged |

## Requirement Changes

- R014 (TLA+ Verification): active → validated — TLAVerifier with genefication loop, TLC subprocess, complexity skip, graceful degradation. 36 tests (S01).
- R010 (Multi-Metric Pareto Evaluation): active → validated — 4-metric Pareto dominance replaces score-only comparison. 28 tests (S02).
- R020 (Simplicity Criterion): active → validated — AST-based complexity scoring, simplicity tiebreaker for incomparable pipelines. 28 tests (S02).
- R009 (Data Leakage Guardrail): active → validated — Two-tier detection (exact block, fuzzy warn), loop gate before evaluation. 26 tests (S03).
- R021 (Sandbox Isolation): active → validated — Docker container isolation with --network=none, graceful fallback. 24 tests (S04).

## Forward Intelligence

### What the next milestone should know
- OptimizationLoop.__init__() now accepts `tla_verifier`, `leakage_checker`, and `sandbox_runner` — all optional, all with graceful degradation. The loop gate sequence is: TLA+ → leakage → evaluation (with sandbox) → Pareto keep/discard.
- ArchiveEntry has grown four optional fields across M003 (tla_verification, leakage_check, pareto_evaluation, sandbox_execution). All use the same backward-compatible pattern: `= None` default, `.get()` in `from_dict()`.
- 381 tests across 22 test files. Test execution takes ~2s with `uv run pytest`.
- All safety gates use contract-level proof (mocked subprocesses) — no integration tests with real Java/TLC or Docker daemon.

### What's fragile
- Container-side harness (`_RUNNER_HARNESS` in sandbox.py) must stay in sync with PipelineResult serialization — any field changes require harness update
- LLMProtocol re-declared in verification.py — if primitives.py protocol changes, the copy must be updated manually
- Fuzzy leakage threshold (0.3 Jaccard) was chosen heuristically — real-world benchmarks may need tuning
- `best_metrics` reconstruction on resume depends on archive entry structure — `evaluation_result` format changes would break resume

### Authoritative diagnostics
- Archive JSON entries carry all four gate result dicts — grep for `tla_verification`, `leakage_check`, `pareto_evaluation`, `sandbox_execution`
- `autoagent.verification`, `autoagent.leakage`, `autoagent.sandbox` loggers — INFO for gate outcomes, WARNING for graceful degradation
- `ParetoResult.rationale` always explains the decision with metric values — grep-friendly in archive entries

### What assumptions changed
- Planned 4-iteration capstone test became 5 — Pareto needs a kept baseline before it can discard a regression (D024: first iteration always kept)
- Assumed loop tests would need modification for Pareto integration — they didn't, because None metrics degrade gracefully to score-only (D050)

## Files Created/Modified

- `src/autoagent/verification.py` — TLAVerifier, VerificationResult, genefication loop, TLC subprocess
- `src/autoagent/pareto.py` — compute_complexity, pareto_dominates, pareto_decision, ParetoResult
- `src/autoagent/leakage.py` — LeakageChecker, LeakageResult, two-tier detection
- `src/autoagent/sandbox.py` — SandboxRunner, SandboxResult, Docker container harness
- `src/autoagent/archive.py` — added tla_verification, pareto_evaluation, leakage_check, sandbox_execution fields
- `src/autoagent/loop.py` — added tla_verifier, leakage_checker, sandbox_runner parameters; gate sequence; Pareto decision
- `tests/test_verification.py` — 29 unit tests
- `tests/test_pareto.py` — 28 unit tests
- `tests/test_leakage.py` — 21 unit tests
- `tests/test_sandbox.py` — 18 unit tests
- `tests/test_loop_verification.py` — 7 integration tests
- `tests/test_loop_leakage.py` — 5 integration tests
- `tests/test_loop_sandbox.py` — 4 integration tests
- `tests/test_final_assembly.py` — 2 capstone integration tests
