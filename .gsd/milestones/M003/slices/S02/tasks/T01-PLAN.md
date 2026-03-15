---
estimated_steps: 5
estimated_files: 3
---

# T01: Build pareto module with pure functions and unit tests

**Slice:** S02 — Pareto Evaluation with Simplicity Criterion
**Milestone:** M003

## Description

Build `src/autoagent/pareto.py` as a self-contained module with three pure functions and one frozen dataclass. Add the `pareto_evaluation` field to `ArchiveEntry`. Write comprehensive unit tests covering all decision branches and edge cases.

## Steps

1. Create `src/autoagent/pareto.py` with:
   - `METRIC_DIRECTIONS` dict: `primary_score` → "higher", `latency_ms`/`cost_usd`/`complexity` → "lower"
   - `compute_complexity(source: str) -> float` using `ast.walk()` — count AST nodes + weighted branch statements (if/for/while/try/with/FunctionDef/AsyncFunctionDef). Handle `SyntaxError` gracefully (return `float('inf')` — unparseable code is maximally complex).
   - `pareto_dominates(a: dict, b: dict) -> bool` — True if `a` ≥ `b` on all metrics AND strictly better on ≥1, respecting metric directions. Only compares keys present in both dicts.
   - `pareto_decision(candidate_metrics: dict, current_best_metrics: dict | None, candidate_source: str, best_source: str | None) -> ParetoResult` — None best → keep (D024); candidate dominates → keep; best dominates → discard; incomparable → prefer simpler (D042), ties → discard (conservative).
   - `ParetoResult` frozen dataclass: `decision: str`, `rationale: str`, `candidate_metrics: dict`, `best_metrics: dict | None`
2. Add `pareto_evaluation: dict[str, Any] | None = None` to `ArchiveEntry` fields and `from_dict` (using `d.get()`)
3. Add `pareto_evaluation` parameter to `Archive.add()` method signature, pass through to `ArchiveEntry`
4. Create `tests/test_pareto.py` with tests:
   - `test_compute_complexity_simple` — known source → expected node range
   - `test_compute_complexity_syntax_error` — invalid source → inf
   - `test_compute_complexity_empty` — empty string → 0 or minimal
   - `test_pareto_dominates_clear_winner` — better on all metrics
   - `test_pareto_dominates_mixed` — better on some, worse on others → False
   - `test_pareto_dominates_equal` — identical metrics → False (not strictly better)
   - `test_pareto_dominates_direction` — lower latency IS better
   - `test_decision_candidate_dominates` → keep
   - `test_decision_best_dominates` → discard
   - `test_decision_incomparable_simpler_wins` → keep simpler
   - `test_decision_incomparable_equal_complexity` → discard (conservative)
   - `test_decision_no_current_best` → keep (D024)
   - `test_decision_none_metrics_degrades_to_score` — when metrics have only `primary_score`, behaves like score-only
5. Run `python3 -m pytest tests/test_pareto.py tests/test_archive.py -v` and fix until green

## Must-Haves

- [ ] `pareto_dominates` handles asymmetric metric directions correctly
- [ ] `compute_complexity` is stable (same source → same score) and handles SyntaxError
- [ ] `pareto_decision` with None best always returns keep (D024)
- [ ] Incomparable case uses simplicity tiebreaker (D042)
- [ ] `ParetoResult` is frozen dataclass with decision + rationale
- [ ] `ArchiveEntry.pareto_evaluation` field is backward-compatible (optional, default None)
- [ ] Module imports nothing from loop.py (self-contained like verification.py)

## Verification

- `python3 -m pytest tests/test_pareto.py -v` — all pareto unit tests pass
- `python3 -m pytest tests/test_archive.py -v` — archive tests pass with new field
- `from autoagent.pareto import pareto_decision, compute_complexity, ParetoResult` imports cleanly

## Inputs

- `src/autoagent/verification.py` — pattern to follow (self-contained module, frozen result dataclass)
- `src/autoagent/archive.py` — ArchiveEntry to extend with pareto_evaluation field
- `src/autoagent/types.py` — MetricsSnapshot field names for metric vector
- S02-RESEARCH.md — metric directions, tiebreaker rules, D042/D024 decisions

## Expected Output

- `src/autoagent/pareto.py` — complete module with 3 pure functions + 1 frozen dataclass
- `tests/test_pareto.py` — 13+ unit tests covering all decision branches
- `src/autoagent/archive.py` — updated with `pareto_evaluation` field on ArchiveEntry + Archive.add()

## Observability Impact

- **New signal:** `ParetoResult.rationale` string in every archive entry explains *why* a pipeline was kept/discarded with metric vectors — queryable via `archive.get(N).pareto_evaluation`
- **Failure state:** `compute_complexity` returns `float('inf')` for unparseable source, visible in the `candidate_metrics.complexity` field of stored `ParetoResult`
- **Inspection:** `METRIC_DIRECTIONS` dict is module-level, importable for debugging which metrics are higher/lower-is-better
- **Agent diagnostics:** A future agent can `from autoagent.pareto import pareto_decision` and test any metric pair to understand decision logic without running the full loop
