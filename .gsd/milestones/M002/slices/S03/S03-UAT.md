# S03: Strategy Selection & Parameter Optimization — UAT

**Milestone:** M002
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: All strategy logic is pure functions testable with synthetic data — no runtime services, no LLM calls, no external state needed

## Preconditions

- Python 3.11+ venv active with autoagent installed in editable mode
- All 250 tests passing (`pytest tests/ -v`)

## Smoke Test

Run `pytest tests/test_strategy.py tests/test_meta_agent.py tests/test_loop_strategy.py -v` — all 69 tests pass confirming stagnation detection, prompt integration, and loop wiring.

## Test Cases

### 1. Graduated signal escalation on plateau

1. In Python REPL, create 12 `ArchiveEntry` objects (newest-first) all with `primary_score: 0.75` except one early entry with `primary_score: 0.80`, all `mutation_type="parametric"`
2. Call `analyze_strategy(entries, plateau_threshold=5)`
3. **Expected:** Signal text contains "plateaued", "structural ratio: 0%", and suggests structural changes. Signal length is 200-500 chars.

### 2. Improving sequence produces no signal

1. Create 10 entries with monotonically increasing scores (0.70, 0.71, ..., 0.79), newest-first (0.79 at index 0)
2. Call `analyze_strategy(entries)`
3. **Expected:** Empty string returned — no guidance needed when improving

### 3. Improving with high structural ratio suggests parameter tuning

1. Create 5+ entries with increasing scores, all `mutation_type="structural"`
2. Call `analyze_strategy(entries)`
3. **Expected:** Signal mentions "structural ratio" > 70% and suggests "tuning parameters within the current topology"

### 4. classify_mutation distinguishes structural from parametric

1. Call `classify_mutation('+def new_pipeline_stage():\n+    result = primitives.LLM()')` 
2. Call `classify_mutation('+temperature = 0.9\n-temperature = 0.7')`
3. **Expected:** First returns "structural", second returns "parametric"

### 5. Strategy signals appear in _build_prompt() output

1. Create a `MetaAgent` with `MockLLM`
2. Call `_build_prompt(goal="test", current_pipeline="pass", strategy_signals="Consider structural changes")`
3. **Expected:** Returned prompt string contains `## Strategy Guidance` section with the signal text

### 6. Strategy signals absent when empty

1. Call `_build_prompt()` with `strategy_signals=""`
2. **Expected:** Prompt does NOT contain `## Strategy Guidance` section

### 7. Loop wires strategy detector and mutation_type

1. Run `pytest tests/test_loop_strategy.py::TestLoopStrategyDetector::test_loop_calls_strategy_detector -v`
2. Run `pytest tests/test_loop_strategy.py::TestLoopStrategyDetector::test_loop_sets_mutation_type_on_archive_entry -v`
3. **Expected:** Both pass — confirming loop calls `analyze_strategy()` before `propose()` and tags entries with `mutation_type`

### 8. Backward-compatible ArchiveEntry deserialization

1. Create an `ArchiveEntry` dict without `mutation_type` key
2. Call `ArchiveEntry.from_dict(data)`
3. **Expected:** Returns valid `ArchiveEntry` with `mutation_type=None` — no error

## Edge Cases

### Empty or single-entry archive

1. Call `analyze_strategy([])` and `analyze_strategy([single_entry])`
2. **Expected:** Both return empty string — insufficient data for analysis

### Window larger than entry count

1. Call `analyze_strategy(entries_of_len_3, window=10)`
2. **Expected:** Uses all 3 entries without error, returns appropriate signal or empty

### Strategy detector failure in loop

1. Run `pytest tests/test_loop_strategy.py::TestLoopStrategyDetector::test_loop_strategy_detector_failure_graceful -v`
2. **Expected:** Pass — loop continues with empty signals when detector raises, logs WARNING

### Mixed mutation types during extended plateau

1. Create 15 entries at plateau with roughly 50/50 structural/parametric mix, plateau_threshold=5
2. Call `analyze_strategy(entries, plateau_threshold=5)`
3. **Expected:** Signal mentions "fundamentally different approach" for extended mixed-type plateau

## Failure Signals

- Any of the 250 tests failing — especially regressions in `test_loop.py` or `test_loop_summarizer.py` (mock signature changes)
- `analyze_strategy()` returning signal text without diagnostic numbers (plateau length, variance, structural ratio)
- `_build_prompt()` output missing `## Strategy Guidance` section when non-empty signals provided
- `ArchiveEntry.from_dict()` failing on dicts without `mutation_type` key
- Loop not setting `mutation_type` on archive entries after evaluation

## Requirements Proved By This UAT

- R012 — Parameter optimization as distinct mutation mode (test cases 3, 4)
- R013 — Autonomous strategy via graduated prompt signals (test cases 1, 2, 5, 6)
- R024 — Exploration/exploitation balance via stagnation detection (test cases 1, 3, edge case mixed plateau)

## Not Proven By This UAT

- End-to-end integration with real LLM and real pipelines (proven in S04)
- That the meta-agent actually changes behavior based on strategy signals (depends on LLM response quality)
- Optimal tuning of plateau_threshold and window parameters for real workloads

## Notes for Tester

All test cases can be verified via pytest — the numbered steps above describe the logical scenario, but each has corresponding automated tests. The REPL-based cases are for exploratory inspection of signal quality. `analyze_strategy()` and `classify_mutation()` are pure functions — no setup, no teardown, no external dependencies.
