# S03: Data Leakage Detection — UAT

**Milestone:** M003
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: All detection logic is deterministic (string matching, Jaccard overlap). No runtime services, no UI. Tests exercise all paths with synthetic data.

## Preconditions

- Python 3.11+ with project installed: `.venv/bin/python -m pytest` works
- All 357 tests passing: `.venv/bin/python -m pytest tests/ -v`

## Smoke Test

Run `python3 -m pytest tests/test_leakage.py tests/test_loop_leakage.py -v` — all 26 tests pass.

## Test Cases

### 1. Exact match blocks iteration

1. Create a `BenchmarkExample` with `input="The quick brown fox jumps over the lazy dog"`, `expected="fox"`
2. Create pipeline source containing the string literal `"The quick brown fox jumps over the lazy dog"`
3. Call `LeakageChecker().check(benchmark, source)`
4. **Expected:** `result.blocked == True`, `result.exact_matches >= 1`

### 2. Fuzzy overlap warns but does not block

1. Create a `BenchmarkExample` with a paragraph of text (>30 words)
2. Create pipeline source that shares >30% of (3,4)-grams with the example text but has no exact string match
3. Call `LeakageChecker(fuzzy_threshold=0.3).check(benchmark, source)`
4. **Expected:** `result.blocked == False`, `len(result.fuzzy_warnings) >= 1`, each warning contains "n-gram overlap"

### 3. Clean pipeline passes without issues

1. Create a benchmark with typical examples
2. Create pipeline source with no shared string literals and low n-gram overlap
3. Call `LeakageChecker().check(benchmark, source)`
4. **Expected:** `result.blocked == False`, `result.exact_matches == 0`, `result.fuzzy_warnings == []`

### 4. Leakage gate wired into loop — blocked iteration discarded

1. Create an `OptimizationLoop` with a `leakage_checker` that returns `LeakageResult(blocked=True, exact_matches=1, ...)`
2. Run one iteration
3. **Expected:** Iteration discarded without running evaluation. Archive entry contains `leakage_check` dict with `blocked: True`. Pipeline source restored to previous version.

### 5. Leakage gate wired into loop — warning iteration proceeds

1. Create an `OptimizationLoop` with a `leakage_checker` that returns `LeakageResult(blocked=False, fuzzy_warnings=["overlap"])`
2. Run one iteration
3. **Expected:** Iteration proceeds to evaluation. Archive entry contains `leakage_check` dict with `blocked: False`.

### 6. No checker configured — gate skipped

1. Create an `OptimizationLoop` without passing `leakage_checker`
2. Run one iteration
3. **Expected:** Iteration proceeds normally. Archive entry has `leakage_check: None` or field absent.

### 7. Archive persistence — leakage results visible in JSON

1. Run a loop iteration with leakage checker configured
2. Read the archive JSON file from disk
3. **Expected:** JSON entry contains `leakage_check` key with `blocked`, `exact_matches`, `fuzzy_warnings`, `cost_usd` fields

## Edge Cases

### Short examples skipped

1. Create a `BenchmarkExample` with `input="hi"`, `expected="ok"` (both < 10 chars)
2. Create pipeline source containing `"hi"` and `"ok"` as string literals
3. Call `LeakageChecker().check(benchmark, source)`
4. **Expected:** `result.blocked == False` — short examples are not flagged

### AST parse failure falls back to regex

1. Create pipeline source with invalid Python syntax (e.g., `def broken(:\n  x = "leaked string"`)
2. Create a benchmark with an example matching `"leaked string"`
3. Call `LeakageChecker().check(benchmark, source)`
4. **Expected:** `result.blocked == True` — regex fallback extracts the string. A WARNING is logged about AST parse failure.

### Non-string data serialized correctly

1. Create a `BenchmarkExample` with `input={"key": "value"}` (dict) and `expected=[1, 2, 3]` (list)
2. Create pipeline source containing `'{"key": "value"}'` as a string literal
3. Call `LeakageChecker().check(benchmark, source)`
4. **Expected:** `result.blocked == True` — dict/list inputs are serialized via `json.dumps(sort_keys=True)` for matching

### Empty benchmark passes

1. Create a `Benchmark` with `examples=[]`
2. Call `LeakageChecker().check(benchmark, source)`
3. **Expected:** `result.blocked == False`, `result.exact_matches == 0`, `result.fuzzy_warnings == []`

### Cost tracking forward-compatible

1. Call `LeakageChecker().check(benchmark, source)` for any case
2. **Expected:** `result.cost_usd == 0.0`

## Failure Signals

- Any of the 26 leakage tests failing
- `ModuleNotFoundError` on `from autoagent.leakage import LeakageChecker`
- Archive entries missing `leakage_check` field when checker is configured
- Blocked iteration proceeding to evaluation (metric results present when they shouldn't be)
- Regression in existing 331 tests (pre-S03 baseline)

## Requirements Proved By This UAT

- R009 (Data Leakage Guardrail) — every evaluation preceded by leakage check, exact overlap blocks, fuzzy overlap warns, results persisted in archive

## Not Proven By This UAT

- Real-world false positive rates on production benchmarks (would require live evaluation with diverse benchmark datasets)
- LLM-based semantic leakage detection (cost_usd reserved but unused)
- End-to-end integration with all four safety gates simultaneously (S04)

## Notes for Tester

- All test cases are already automated in `tests/test_leakage.py` and `tests/test_loop_leakage.py`. The UAT cases above map 1:1 to existing tests — run the test suite to validate.
- The fuzzy threshold (0.3) is configurable via `LeakageChecker(fuzzy_threshold=...)`. If testing with domain-specific text, adjust if warnings seem too aggressive.
- Enable DEBUG logging (`logging.getLogger('autoagent.leakage').setLevel(logging.DEBUG)`) to see per-example Jaccard scores during manual investigation.
