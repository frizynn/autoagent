---
id: T01
parent: S02
milestone: M003
provides:
  - pareto.py module with compute_complexity, pareto_dominates, pareto_decision, ParetoResult
  - ArchiveEntry.pareto_evaluation field (backward-compatible)
  - Archive.add() pareto_evaluation parameter
  - 28 unit tests covering all decision branches and edge cases
key_files:
  - src/autoagent/pareto.py
  - tests/test_pareto.py
  - src/autoagent/archive.py
key_decisions:
  - AST node count + weighted branch statements (×2) for complexity — simple, stable, no external deps
  - float('inf') for SyntaxError in compute_complexity — unparseable = maximally complex
  - Only shared keys in METRIC_DIRECTIONS are compared in pareto_dominates — unknown keys ignored
patterns_established:
  - Self-contained pure-function module with frozen result dataclass (mirrors verification.py pattern)
  - METRIC_DIRECTIONS dict for configurable higher/lower-is-better semantics
observability_surfaces:
  - ParetoResult.rationale string explains every decision with metric values
  - pareto_evaluation dict on ArchiveEntry enables structured post-hoc inspection
  - compute_complexity returns inf for unparseable source — visible in stored metrics
duration: 15m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Build pareto module with pure functions and unit tests

**Built self-contained Pareto evaluation module with 3 pure functions, 1 frozen dataclass, and 28 unit tests. Extended ArchiveEntry with backward-compatible pareto_evaluation field.**

## What Happened

Created `src/autoagent/pareto.py` following the `verification.py` pattern — self-contained, no imports from loop.py or archive.py. The module provides:

- `METRIC_DIRECTIONS` dict mapping metric names to "higher"/"lower" direction
- `compute_complexity(source)` — AST-based scoring using `ast.walk()` with weighted branch nodes (if/for/while/try/with/FunctionDef/AsyncFunctionDef count double). Returns `float('inf')` on SyntaxError, `0.0` on empty input.
- `pareto_dominates(a, b)` — standard Pareto dominance check respecting metric directions, comparing only shared keys present in METRIC_DIRECTIONS
- `pareto_decision(...)` — orchestrates: None best → keep (D024), candidate dominates → keep, best dominates → discard, incomparable → prefer simpler (D042), equal complexity → discard (conservative)
- `ParetoResult` frozen dataclass with decision, rationale, and both metric dicts

Extended `ArchiveEntry` with `pareto_evaluation: dict[str, Any] | None = None` field + `from_dict` deserialization via `d.get()`. Added `pareto_evaluation` parameter to `Archive.add()`.

## Verification

- `pytest tests/test_pareto.py -v` — 28 tests passed (complexity scoring, dominance logic, all decision branches, edge cases)
- `pytest tests/test_archive.py -v` — 32 tests passed with new field
- `pytest tests/ -v` — full suite 331 tests passed, zero regressions
- `from autoagent.pareto import pareto_decision, compute_complexity, ParetoResult` — imports cleanly
- Diagnostic check: `pareto_decision({'primary_score': 0.9}, None, 'x=1', None)` returns keep with "first" in rationale

Slice-level verification status:
- ✅ `pytest tests/test_pareto.py -v` — 28 passed
- ⬜ `pytest tests/test_loop.py -v` — not yet wired (T02)
- ✅ `pytest tests/test_archive.py -v` — 32 passed
- ✅ `pytest tests/ -v` — 331 passed
- ✅ Diagnostic import check — passed

## Diagnostics

- Import `from autoagent.pareto import pareto_decision` and call with synthetic metrics to test any decision path
- `METRIC_DIRECTIONS` is importable for inspecting which metrics are higher/lower-is-better
- `ParetoResult.rationale` always explains the decision with metric values — grep archive JSON for `pareto_evaluation.rationale`

## Deviations

- Added 2 extra tests beyond the 13 specified (partial keys, unknown keys, best-simpler-wins, result-carries-metrics, whitespace-only) — total 28 for better coverage

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/pareto.py` — new module with 3 pure functions + ParetoResult frozen dataclass
- `tests/test_pareto.py` — 28 unit tests covering all decision branches and edge cases
- `src/autoagent/archive.py` — added pareto_evaluation field to ArchiveEntry + from_dict + Archive.add()
- `.gsd/milestones/M003/slices/S02/S02-PLAN.md` — added Observability / Diagnostics section + diagnostic verification check
- `.gsd/milestones/M003/slices/S02/tasks/T01-PLAN.md` — added Observability Impact section
