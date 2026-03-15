---
id: T01
parent: S03
milestone: M003
provides:
  - LeakageChecker class with exact-match blocking and fuzzy n-gram warnings
  - LeakageResult frozen dataclass
  - Comprehensive unit tests (21 tests)
key_files:
  - src/autoagent/leakage.py
  - tests/test_leakage.py
key_decisions:
  - Per-example counting for exact_matches (break after first match per example, not per-target)
  - Combined (3,4)-grams for fuzzy detection rather than separate passes
  - Regex fallback uses non-greedy matching with DOTALL for triple-quote support
patterns_established:
  - Self-contained checker module with frozen result dataclass (matches verification.py pattern)
observability_surfaces:
  - INFO log on every check outcome (blocked status, match counts, warning counts)
  - WARNING log on AST parse fallback with SyntaxError details
  - DEBUG log on per-example match details and Jaccard scores
duration: 15m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Implement LeakageChecker module with unit tests

**Built self-contained `leakage.py` with two-tier detection: AST-based exact-match blocking and word-level n-gram fuzzy warnings. All 21 unit tests pass.**

## What Happened

Created `src/autoagent/leakage.py` following the `verification.py` self-contained module pattern. `LeakageResult` is a frozen dataclass with `blocked`, `exact_matches`, `fuzzy_warnings`, and `cost_usd` fields. `LeakageChecker` takes a `fuzzy_threshold` (default 0.3) and exposes `check(benchmark, pipeline_source) -> LeakageResult`.

Exact-match path: `ast.parse()` extracts all `ast.Constant` string nodes from pipeline source. Each benchmark example's input/expected is serialized via `json.dumps(sort_keys=True)` and `str()`. Short examples (both representations < 10 chars) are skipped. On `SyntaxError`, falls back to regex extraction of quoted strings.

Fuzzy path: tokenizes pipeline source and each example's text via `re.findall(r'\w+', lower())`, extracts combined (3,4)-grams, computes Jaccard similarity. Warnings appended per-example when overlap exceeds threshold. Never blocks — advisory only per D046.

Tests cover all 8 specified paths: exact match blocking, clean pass, multiple matches, short example skip, non-string data serialization, fuzzy overlap warnings, AST fallback, and empty benchmark.

## Verification

- `python3 -m pytest tests/test_leakage.py -v` — **21/21 passed**
- `python3 -m pytest tests/ -v` — **352/352 passed** (zero regressions)
- `grep` confirms no imports from `loop`, `archive`, `cli`, or `state` modules
- `LeakageResult` frozen — confirmed via `pytest.raises(AttributeError)` on mutation

### Slice-level verification status (T01 of 2):
- ✅ `python3 -m pytest tests/test_leakage.py -v` — 21 passed
- ⬜ `python3 -m pytest tests/test_loop_leakage.py -v` — file not yet created (T02)
- ✅ `python3 -m pytest tests/ -v` — 352 passed, zero regressions

## Diagnostics

- Check `LeakageResult` fields directly for programmatic inspection
- Enable DEBUG logging on `autoagent.leakage` to see per-example match details and Jaccard scores
- WARNING-level log emitted when AST parse fails and regex fallback activates

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/leakage.py` — New module: `LeakageResult` frozen dataclass + `LeakageChecker` class with exact-match and fuzzy detection
- `tests/test_leakage.py` — 21 unit tests covering all detection paths and edge cases
- `.gsd/milestones/M003/slices/S03/S03-PLAN.md` — Added Observability / Diagnostics section
- `.gsd/milestones/M003/slices/S03/tasks/T01-PLAN.md` — Added Observability Impact section
