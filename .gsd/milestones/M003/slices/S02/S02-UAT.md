# S02: Pareto Evaluation with Simplicity Criterion — UAT

**Milestone:** M003
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: All functions are pure with deterministic outputs — testable via pytest and direct invocation without live LLM or runtime services

## Preconditions

- Python 3.11+ with `.venv` activated
- Package installed in dev mode (`pip install -e .`)
- All 331 tests passing (`python3 -m pytest tests/ -v`)

## Smoke Test

```bash
.venv/bin/python -c "
from autoagent.pareto import pareto_decision
r = pareto_decision({'primary_score': 0.9}, None, 'x=1', None)
assert r.decision == 'keep' and 'first' in r.rationale.lower()
print('Smoke test passed:', r.rationale)
"
```

## Test Cases

### 1. Candidate dominates current best — kept

1. Call `pareto_decision({'primary_score': 0.9, 'latency_ms': 100, 'cost_usd': 0.01}, {'primary_score': 0.7, 'latency_ms': 200, 'cost_usd': 0.02}, 'x=1', 'x=1; y=2; z=3')`
2. **Expected:** `decision == "keep"`, rationale mentions "dominates"

### 2. Current best dominates candidate — discarded

1. Call `pareto_decision({'primary_score': 0.5, 'latency_ms': 300, 'cost_usd': 0.05}, {'primary_score': 0.9, 'latency_ms': 100, 'cost_usd': 0.01}, 'x=1', 'x=1')`
2. **Expected:** `decision == "discard"`, rationale mentions "dominated"

### 3. Incomparable — simpler candidate wins

1. Call `pareto_decision({'primary_score': 0.9, 'latency_ms': 300}, {'primary_score': 0.7, 'latency_ms': 100}, 'x=1', 'def f():\n  for i in range(10):\n    if i > 5:\n      return i')`
2. Candidate source `'x=1'` is simpler than the multi-line best source
3. **Expected:** `decision == "keep"`, rationale mentions "simpler"

### 4. Incomparable — simpler best wins (candidate discarded)

1. Call `pareto_decision({'primary_score': 0.9, 'latency_ms': 300}, {'primary_score': 0.7, 'latency_ms': 100}, 'def f():\n  for i in range(10):\n    if i > 5:\n      return i', 'x=1')`
2. Best source `'x=1'` is simpler
3. **Expected:** `decision == "discard"`, rationale mentions "simpler"

### 5. Incomparable with equal complexity — conservative discard

1. Call `pareto_decision({'primary_score': 0.9, 'latency_ms': 300}, {'primary_score': 0.7, 'latency_ms': 100}, 'x=1', 'y=2')`
2. Both sources have equal complexity
3. **Expected:** `decision == "discard"`, rationale mentions "equal complexity" or "conservative"

### 6. First iteration (no best) — always kept

1. Call `pareto_decision({'primary_score': 0.5}, None, 'x=1', None)`
2. **Expected:** `decision == "keep"`, rationale mentions "first" (D024)

### 7. None metrics degrade to score-only comparison

1. Call `pareto_decision({'primary_score': 0.9}, {'primary_score': 0.7}, 'x=1', 'y=2')` — no latency/cost metrics
2. **Expected:** `decision == "keep"` because higher primary_score dominates on the only metric present

### 8. Complexity scoring stability

1. Call `compute_complexity('def f():\n  if True:\n    for x in y:\n      pass')`
2. Call again with same input
3. **Expected:** Both return identical float values; branches (if, for, def) weighted ×2

### 9. Unparseable source gets infinite complexity

1. Call `compute_complexity('def +++broken')`
2. **Expected:** Returns `float('inf')`

### 10. Archive entry carries pareto_evaluation

1. Create a temp Archive, call `archive.add(...)` with `pareto_evaluation={'decision': 'keep', 'rationale': 'test'}`
2. Read back the entry with `archive.get()`
3. **Expected:** `entry.pareto_evaluation == {'decision': 'keep', 'rationale': 'test'}`

### 11. Full test suite passes

1. Run `.venv/bin/python -m pytest tests/ -v`
2. **Expected:** 331 passed, 0 failed, 0 errors

## Edge Cases

### Empty source string

1. Call `compute_complexity('')`
2. **Expected:** Returns `0.0`

### Whitespace-only source

1. Call `compute_complexity('   \n\n  ')`
2. **Expected:** Returns `0.0`

### Metric directions respected

1. Call `pareto_dominates({'latency_ms': 50}, {'latency_ms': 100})`
2. latency_ms is lower-is-better, so 50 < 100 is better
3. **Expected:** Returns `True`

### No shared keys between candidates

1. Call `pareto_dominates({'unknown_a': 1}, {'unknown_b': 2})`
2. **Expected:** Returns `False` (no comparable dimensions)

## Failure Signals

- Any test in `test_pareto.py` failing — Pareto logic regression
- Any test in `test_loop.py` failing — integration regression (decision wiring)
- `pareto_evaluation` missing from archive entries — field not being passed through
- `ImportError` on `from autoagent.pareto import ...` — module not installed
- `ParetoResult.rationale` empty — decision path not setting explanation

## Requirements Proved By This UAT

- R010 — Pareto dominance across 4-metric vector with direction-aware comparison, rejecting pipelines that game one metric (cases 1-5, 7)
- R020 — Simplicity tiebreaker for incomparable pipelines using AST complexity (cases 3-5, 8-9)

## Not Proven By This UAT

- Live Pareto evaluation with real LLM metrics (MockLLM produces 0.0 metrics, so integration tests exercise score-only degradation path)
- Pareto interaction with other safety gates (TLA+, leakage, sandbox) — proven in S04

## Notes for Tester

- All test cases can be run via `python3 -m pytest tests/test_pareto.py -v` — the 28 unit tests cover every case listed above
- The diagnostic one-liner in the smoke test is the quickest way to confirm the module works
- Loop integration is tested indirectly through existing MockLLM tests — Pareto degrades to score-only with zero metrics, so loop tests don't need explicit Pareto assertions
