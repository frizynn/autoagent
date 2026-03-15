# S02: Pareto Evaluation with Simplicity Criterion — Research

**Date:** 2026-03-14

## Summary

S02 replaces the single-score `score >= best_score` keep/discard decision (loop.py L396-399) with Pareto dominance across a 4-metric vector: (primary_score, latency, cost, complexity). The data is already flowing — `EvaluationResult` carries `primary_score` and `MetricsSnapshot` with `latency_ms`, `cost_usd`, `tokens_in`, `tokens_out`. The missing piece is a complexity metric (`ast`-based, stdlib) and the Pareto comparison logic (~40 lines of pure functions). D042 resolves the R010/R020 tension: simplicity is a dimension in the Pareto vector, not a separate gate. Incomparable pipelines (neither dominates) use simpler-code tiebreaker per D042.

The integration point is clean — lines 394-403 of `loop.py` are a self-contained 6-line if/else block. The Pareto module produces a `ParetoResult` with `decision` ("keep"/"discard") and `rationale` string. The rationale gets stored in the archive alongside existing fields. No new fields on `ArchiveEntry` are strictly needed — the existing `rationale` field already captures the decision reason — but adding an optional `pareto_evaluation: dict | None` field (same pattern as `tla_verification`) enables structured archive inspection.

This is the lowest-risk slice in M003. Zero external dependencies (pure Python + stdlib `ast`), pure functions with no side effects, well-defined input/output contract, and comprehensive testability via synthetic metric vectors.

## Recommendation

Build `pareto.py` as a standalone module with three pure functions and one frozen dataclass:

1. `compute_complexity(source: str) -> float` — AST-based complexity score (node count + cyclomatic complexity indicators). Higher = more complex. Normalized to a 0-1 range isn't necessary since Pareto comparison only needs consistent ordering.
2. `pareto_dominates(a: dict, b: dict) -> bool` — True if `a` is at least as good as `b` on all metrics AND strictly better on at least one. Handles metric direction (higher-is-better for primary_score, lower-is-better for latency/cost/complexity).
3. `pareto_decision(candidate_metrics: dict, current_best_metrics: dict, candidate_source: str, best_source: str) -> ParetoResult` — Orchestrates the decision: if candidate dominates → keep, if best dominates → discard, if incomparable → prefer simpler (R020), if equal complexity → keep current (conservative per D042).
4. `ParetoResult(frozen=True)` — `decision: str`, `rationale: str`, `candidate_metrics: dict`, `best_metrics: dict`.

Wire into `loop.py` by replacing the `if best_score is None or score >= best_score` block with a call to `pareto_decision`. First iteration (best_score is None) always keeps — same as D024.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Pareto dominance | Implement from scratch (~20 lines) | Too simple for a dependency. Standard algorithm: A dominates B iff A ≥ B on all metrics and A > B on at least one. |
| Code complexity measurement | Python `ast` (stdlib) | Zero-dependency. Count AST nodes, branches (if/for/while/try), function defs. No need for radon/lizard. |
| Metric direction handling | Convention in code | Define which metrics are "higher is better" vs "lower is better" via a simple dict. |

## Existing Code and Patterns

- `loop.py` L394-403 — **The replacement target.** Current logic: `score = eval_result.primary_score; if best_score is None or score >= best_score: decision = "keep"`. Replace with Pareto decision. The `best_score` variable also needs to become a `best_metrics` dict or similar to carry the full vector.
- `loop.py` L153-169 — **Resume reconstruction.** Currently reconstructs `best_score` from archive's best kept entry. Must also reconstruct `best_metrics` and `best_source` for Pareto comparison after resume.
- `types.py` `MetricsSnapshot` — **Already carries latency_ms, cost_usd, tokens_in, tokens_out.** The Pareto vector extracts from this plus `primary_score` from `EvaluationResult`. No changes needed to `MetricsSnapshot`.
- `evaluation.py` `EvaluationResult` — **Source of metrics.** `primary_score` (float) and `metrics` (MetricsSnapshot | None). When `metrics` is None (failed eval), Pareto defaults to worst-case values.
- `archive.py` `ArchiveEntry` — **S01 added `tla_verification: dict | None`.** Follow same pattern for `pareto_evaluation: dict | None`. `from_dict` uses `d.get()` for backward compat.
- `verification.py` — **Pattern to follow.** Self-contained module, frozen result dataclass, pure functions, no imports from loop.py. Pareto module should mirror this isolation.
- `strategy.py` `classify_mutation()` — **Pure function pattern.** No side effects, no I/O, testable with synthetic inputs. `pareto_dominates()` and `compute_complexity()` should follow this exact pattern.
- `loop.py` L320-370 — **TLA+ gate pattern.** Shows how a gate integrates: compute result → accumulate cost → handle failure (discard + archive + restore + continue) → handle success (proceed). Pareto gate is simpler — no cost to accumulate, no early discard before evaluation, just a different keep/discard decision.

## Constraints

- **Zero Python package dependencies** — `ast` module is stdlib. No radon, lizard, or mccabe. Complexity metric must be built from `ast.NodeVisitor` or `ast.walk()`.
- **Frozen dataclass pattern** — `ParetoResult` must be `@dataclass(frozen=True)` per existing convention.
- **Metric direction asymmetry** — `primary_score` is higher-is-better; `latency_ms`, `cost_usd`, and `complexity` are lower-is-better. `pareto_dominates` must handle both directions correctly.
- **None metrics handling** — `EvaluationResult.metrics` can be `None` (failed evaluations already get discarded before reaching the Pareto check, but defensive handling is needed).
- **First iteration always kept** — D024: when there's no current best, any successful evaluation is kept. Pareto logic must preserve this invariant.
- **Resume reconstruction** — Currently reconstructs `best_score` from archive. Must also reconstruct best metrics vector and best pipeline source for Pareto comparison. Source is available via the archive's pipeline snapshot file.
- **Archive backward compatibility** — New `pareto_evaluation` field on `ArchiveEntry` must be optional with default `None`, using `d.get()` in `from_dict`.
- **303 existing tests must pass** — Zero regressions. Many tests mock or set `best_score` directly; changing the keep/discard logic must not break these.
- **`best_score` is used by resume logic and state** — Can't simply delete `best_score` — it's used in `state.best_iteration_id` reconstruction (L160-169). Pareto replaces the *decision logic* but `best_score` as a tracking variable may need to coexist for compatibility.

## Common Pitfalls

- **Breaking existing tests by changing the keep/discard interface** — Many tests in `test_loop.py` set up scenarios expecting the simple `score >= best_score` behavior. The Pareto decision must produce the same outcome as the old logic when metrics are absent (None) — effectively degrades to score-only comparison. This keeps existing tests passing without modification.
- **Complexity metric instability** — If `compute_complexity` gives wildly different scores for semantically equivalent code (e.g., list comprehension vs for loop), it creates noisy Pareto decisions. Mitigation: use AST node count as the primary signal — it's stable across style variations and correlates with actual code complexity.
- **All-None metrics making Pareto useless** — If `MockLLM` produces zero-cost metrics (0 latency, 0 cost, 0 tokens), every pipeline has identical non-score metrics and Pareto degrades to score-only. This is actually fine — it means existing tests naturally work. Real runs with real LLM calls will have meaningful metric variation.
- **Incomparable case being too common** — In practice, improving primary_score often increases latency/cost (more LLM calls, more complex prompts). This means most comparisons may be "incomparable" in Pareto terms, defaulting to the simplicity tiebreaker. This is actually the desired behavior per R020 — complexity is the tiebreaker the user wants.
- **Forgetting to update resume logic** — If `best_score` is replaced but resume doesn't reconstruct the equivalent state, crash recovery breaks. Must test resume with Pareto state.

## Open Risks

- **Complexity metric granularity** — AST node count may not distinguish meaningfully between pipelines that differ by a few lines. A pipeline with 50 nodes vs 52 nodes is effectively identical in complexity. The Pareto check handles this naturally (neither dominates on complexity → incomparable → tiebreaker uses raw comparison which may flip on noise). Acceptable for now — can refine the metric later (D042 marked revisable).
- **Interaction with archive summarizer** — `ArchiveSummarizer` reads archive entries to produce summaries. Adding `pareto_evaluation` dict to entries increases entry size slightly. Should not be a problem — summarizer works from the evaluation_result dict, not the full entry.
- **Cost metric double-counting** — The `cost_usd` in `MetricsSnapshot` is the pipeline evaluation cost. The TLA+ verification cost is tracked separately. Pareto should use evaluation cost only (what the pipeline costs to run), not total iteration cost. This is already correct since `eval_result.metrics.cost_usd` is evaluation-only.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Pareto evaluation | None found | Too domain-specific, trivial to implement |
| Code complexity (Python ast) | `boshu2/agentops@complexity` (238 installs) | available — but overkill for ~30 lines of ast.walk() |
| Code complexity | `nkootstra/skills@code-complexity-audit` (28 installs) | available — audit-focused, not runtime metric |

No skills are worth installing for this slice. The implementation is pure stdlib Python with no external dependencies.

## Sources

- Codebase analysis: `src/autoagent/loop.py` (keep/discard logic L394-403, resume L153-169), `evaluation.py` (EvaluationResult, MetricsSnapshot aggregation), `types.py` (MetricsSnapshot fields), `archive.py` (ArchiveEntry, tla_verification pattern), `verification.py` (gate integration pattern), `strategy.py` (pure function pattern)
- Architecture decisions: D042 (simplicity as Pareto dimension), D024 (first iteration always kept), D006 (multi-metric vector), D020 (dict storage for results)
- Requirements: R010 (multi-metric Pareto evaluation), R020 (simplicity criterion)
- S01 summary: gate integration pattern, ArchiveEntry field addition, frozen dataclass convention
- Domain knowledge: Pareto dominance is standard multi-objective optimization — A dominates B iff A ≥ B on all objectives and A > B on at least one
