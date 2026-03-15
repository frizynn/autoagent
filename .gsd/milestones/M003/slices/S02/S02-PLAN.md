# S02: Pareto Evaluation with Simplicity Criterion

**Goal:** Replace single-score keep/discard with Pareto dominance across (primary_score, latency, cost, complexity). Incomparable pipelines resolved by preferring simpler code (R020).
**Demo:** A pipeline that improves primary_score but degrades latency or cost is rejected by the Pareto check. A pipeline that ties on all metrics but is more complex is discarded. Existing tests pass unchanged.

## Must-Haves

- `pareto_dominates(a, b)` correctly handles metric direction asymmetry (higher-is-better vs lower-is-better)
- `compute_complexity(source)` produces stable AST-based complexity scores
- `pareto_decision()` returns keep/discard with rationale string
- Incomparable pipelines resolved by simplicity tiebreaker (D042)
- First iteration always kept (D024 preserved)
- When metrics are None/zero (MockLLM), behavior degrades to score-only — existing tests pass without modification
- Loop integration replaces L396-399 keep/discard block
- Resume reconstructs best metrics + best source for Pareto comparison
- `ArchiveEntry` gains optional `pareto_evaluation: dict | None` field (backward-compatible)
- All existing tests pass (303+)

## Proof Level

- This slice proves: contract + integration
- Real runtime required: no (pure functions + loop integration tested via existing MockLLM infrastructure)
- Human/UAT required: no

## Verification

- `python3 -m pytest tests/test_pareto.py -v` — unit tests for all pure functions (dominance, complexity, decision, edge cases)
- `python3 -m pytest tests/test_loop.py -v` — all existing loop tests pass unchanged
- `python3 -m pytest tests/test_archive.py -v` — archive tests pass with new field
- `python3 -m pytest tests/ -v` — full suite, zero regressions
- `python3 -c "from autoagent.pareto import pareto_decision; r = pareto_decision({'primary_score': 0.9}, None, 'x=1', None); assert r.decision == 'keep' and 'first' in r.rationale.lower()"` — diagnostic: first-iteration keep path produces inspectable rationale

## Integration Closure

- Upstream surfaces consumed: `types.py` MetricsSnapshot, `evaluation.py` EvaluationResult, `archive.py` ArchiveEntry
- New wiring introduced: Pareto decision replaces score comparison in `loop.py` L396-403; resume logic reconstructs best metrics vector
- What remains before the milestone is truly usable end-to-end: S03 (leakage detection), S04 (sandbox + final assembly)

## Tasks

- [x] **T01: Build pareto module with pure functions and unit tests** `est:45m`
  - Why: The standalone module is the foundation — all pure functions, zero dependencies beyond stdlib `ast`, fully testable in isolation before touching the loop
  - Files: `src/autoagent/pareto.py`, `tests/test_pareto.py`
  - Do: Implement `compute_complexity()` using `ast.walk()` (count nodes + branch statements), `pareto_dominates()` with metric direction dict, `pareto_decision()` orchestrating dominance check + simplicity tiebreaker, `ParetoResult` frozen dataclass. Add `pareto_evaluation: dict | None = None` field to `ArchiveEntry` + `from_dict`. Test cases: clear dominance (keep), clear dominated (discard), incomparable resolved by simplicity, equal complexity → keep current (conservative), first iteration (no best) always keep, None metrics degrade to score-only, complexity scoring stability across code styles.
  - Verify: `python3 -m pytest tests/test_pareto.py -v && python3 -m pytest tests/test_archive.py -v`
  - Done when: All pareto unit tests pass, archive tests pass with new field, module has no imports from loop.py

- [x] **T02: Wire Pareto decision into optimization loop and verify integration** `est:45m`
  - Why: The module exists but the loop still uses score-only comparison — this task replaces the decision logic and proves the integration works end-to-end including resume
  - Files: `src/autoagent/loop.py`, `tests/test_loop.py`
  - Do: Replace L396-403 keep/discard block with `pareto_decision()` call. Track `best_metrics` dict alongside `best_score` (keep `best_score` for compatibility — it's used in state). Update resume logic (L160-169) to reconstruct best metrics and best source from archive. Pass `pareto_evaluation` dict to `archive.add()`. Ensure MockLLM-based tests produce None/zero metrics → Pareto degrades to score-only → no test changes needed.
  - Verify: `python3 -m pytest tests/test_loop.py -v && python3 -m pytest tests/ -v`
  - Done when: All existing loop tests pass unchanged, full test suite green, Pareto rationale appears in archive entries

## Observability / Diagnostics

- `ParetoResult.rationale` provides human/agent-readable explanation for every keep/discard decision — stored in archive entries for post-hoc inspection
- `compute_complexity` returns `float('inf')` on `SyntaxError` — observable signal that source was unparseable
- `pareto_evaluation` dict on `ArchiveEntry` enables structured querying of Pareto decisions from archive (grep for `"decision": "keep"` or `"discard"` with rationale)
- Logging: `pareto.py` logs at INFO level for each decision with metric vectors and rationale
- Failure visibility: unparseable source → `inf` complexity → candidate always loses complexity tiebreaker → visible in rationale string
- Redaction: no secrets involved — all inputs are source code and numeric metrics

## Files Likely Touched

- `src/autoagent/pareto.py` (new)
- `src/autoagent/archive.py`
- `src/autoagent/loop.py`
- `tests/test_pareto.py` (new)
- `tests/test_loop.py`
- `tests/test_archive.py`
