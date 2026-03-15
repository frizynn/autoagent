---
id: S02
parent: M003
milestone: M003
provides:
  - pareto.py module with compute_complexity, pareto_dominates, pareto_decision, ParetoResult
  - ArchiveEntry.pareto_evaluation field (backward-compatible)
  - Loop integration replacing score-only keep/discard with Pareto dominance
  - Resume logic reconstructing best_metrics from archive entries
  - 28 unit tests for Pareto module, all existing tests unchanged
requires:
  - slice: M001/S05
    provides: loop.py keep/discard decision point, archive.add() interface
affects:
  - M003/S04
key_files:
  - src/autoagent/pareto.py
  - src/autoagent/loop.py
  - src/autoagent/archive.py
  - tests/test_pareto.py
key_decisions:
  - AST node count + weighted branch statements (×2) for complexity — simple, stable, no external deps (D049)
  - Pareto degrades to score-only when metrics are None/zero — MockLLM path works without modification (D050)
  - Only shared keys in METRIC_DIRECTIONS are compared — unknown metrics ignored gracefully
patterns_established:
  - Self-contained pure-function module with frozen result dataclass (mirrors verification.py)
  - METRIC_DIRECTIONS dict for configurable higher/lower-is-better semantics
  - Pareto decision as single authority — no fallback to score comparison
observability_surfaces:
  - ParetoResult.rationale explains every decision with metric values
  - pareto_evaluation dict on ArchiveEntry enables structured post-hoc inspection
  - compute_complexity returns inf for unparseable source — visible in stored metrics
drill_down_paths:
  - .gsd/milestones/M003/slices/S02/tasks/T01-SUMMARY.md
  - .gsd/milestones/M003/slices/S02/tasks/T02-SUMMARY.md
duration: 30m
verification_result: passed
completed_at: 2026-03-14
---

# S02: Pareto Evaluation with Simplicity Criterion

**Keep/discard decisions now use Pareto dominance across (primary_score, latency, cost, complexity) with simplicity tiebreaker for incomparable pipelines. Single-score comparison eliminated.**

## What Happened

T01 built the standalone `pareto.py` module following the `verification.py` pattern — self-contained, no imports from loop or archive. Three pure functions: `compute_complexity()` uses `ast.walk()` with weighted branch nodes (if/for/while/try/with/FunctionDef/AsyncFunctionDef count double), `pareto_dominates()` checks standard Pareto dominance respecting metric directions (higher/lower-is-better), and `pareto_decision()` orchestrates the full decision: first iteration always kept (D024), dominance check, then simplicity tiebreaker for incomparable cases (D042). `ParetoResult` frozen dataclass carries decision, rationale, and both metric dicts.

T02 wired it into `loop.py`: replaced the score-only keep/discard block with `pareto_decision()`, added `best_metrics` tracking alongside `best_score` (kept for state compatibility), updated resume logic to reconstruct best metrics from archive entries. Key insight: MockLLM-based tests produce None metrics → candidate_metrics gets 0.0 defaults → Pareto naturally degrades to score-only comparison. All 17 loop tests passed without modification.

`ArchiveEntry` gained `pareto_evaluation: dict | None = None` field with backward-compatible deserialization.

## Verification

- `pytest tests/test_pareto.py -v` — 28 passed (complexity scoring, dominance logic, all decision branches, edge cases)
- `pytest tests/test_loop.py -v` — 17 passed unchanged
- `pytest tests/test_archive.py -v` — 32 passed with new field
- `pytest tests/ -v` — 331 passed, zero regressions
- Diagnostic: `pareto_decision({'primary_score': 0.9}, None, 'x=1', None)` returns keep with "first" in rationale

## Requirements Advanced

- R010 (Multi-Metric Pareto Evaluation) — fully implemented: Pareto dominance across 4-metric vector replaces single-score comparison
- R020 (Simplicity Criterion) — fully implemented: AST-based complexity scoring, simplicity tiebreaker for incomparable pipelines

## Requirements Validated

- R010 — Pareto dominance check across (primary_score, latency_ms, cost_usd, complexity) with direction-aware comparison. Pipelines that improve one metric at the expense of others are rejected. 28 unit tests + loop integration. Contract-level proof.
- R020 — AST-based complexity scoring via compute_complexity(). Incomparable pipelines resolved by preferring simpler code. Equal complexity → conservative discard. Unparseable source → float('inf') complexity → always loses tiebreaker. 28 unit tests prove all branches.

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

- 28 tests instead of planned ~13 — added coverage for partial keys, unknown keys, best-simpler-wins, result-carries-metrics, whitespace-only input

## Known Limitations

- Complexity scoring is AST node count with weighted branches — doesn't measure semantic complexity (e.g., deeply nested vs flat code of same node count)
- When all metrics are None/zero (MockLLM), Pareto degrades to score-only — this is intentional for test compatibility but means Pareto only adds value with real evaluations
- No Pareto-specific tests in test_loop.py — loop tests exercise the integration path but with MockLLM metrics (0.0 defaults), so the Pareto logic effectively becomes score-only in those tests

## Follow-ups

- none — S04 will exercise Pareto alongside other gates in final integration

## Files Created/Modified

- `src/autoagent/pareto.py` — new module: compute_complexity, pareto_dominates, pareto_decision, ParetoResult, METRIC_DIRECTIONS
- `tests/test_pareto.py` — 28 unit tests covering all decision branches
- `src/autoagent/archive.py` — added pareto_evaluation field to ArchiveEntry + from_dict + Archive.add()
- `src/autoagent/loop.py` — replaced score-only keep/discard with Pareto decision, best_metrics tracking, resume reconstruction

## Forward Intelligence

### What the next slice should know
- `pareto_decision()` is the single decision authority in the loop — it receives candidate_metrics and best_metrics dicts, returns ParetoResult with decision and rationale
- `METRIC_DIRECTIONS` in `pareto.py` defines which metrics are higher/lower-is-better — new metrics need an entry here
- Archive entries now carry `pareto_evaluation` dict with decision, rationale, candidate_metrics, best_metrics

### What's fragile
- `best_metrics` reconstruction on resume depends on archive entry structure — if `evaluation_result` format changes, resume reconstruction needs updating

### Authoritative diagnostics
- `pareto_evaluation.rationale` in archive JSON — always explains the decision with metric values, grep-friendly
- `compute_complexity()` is importable standalone — call with any source string to debug complexity scores

### What assumptions changed
- Assumed loop tests would need modification for Pareto integration — they didn't, because None metrics degrade gracefully to score-only
