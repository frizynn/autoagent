# S04: Cold-Start Pipeline Generation — UAT

**Milestone:** M002
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: Cold-start is fully testable via unit/integration tests — the LLM call is mockable, and all paths (success, retry, fallback) are exercised in test fixtures. No live runtime or human-experience testing needed.

## Preconditions

- Python 3.11+ with project installed in dev mode (`.venv/bin/python -m pip install -e .`)
- All 267 tests passing (`pytest -v`)
- S02 component vocabulary available (already merged)

## Smoke Test

Run `pytest tests/test_cli.py::TestColdStart -v` — 4 tests pass confirming cold-start triggers, skips, retries, and passes benchmark description.

## Test Cases

### 1. Benchmark.describe() produces compact description

1. Create a Benchmark with 10 examples and a scorer
2. Call `benchmark.describe(max_examples=3)`
3. **Expected:** Output contains scorer name, "10 examples total", exactly 3 sampled input/expected pairs, and is under 500 tokens

### 2. Benchmark.describe() handles fewer examples than max

1. Create a Benchmark with 2 examples
2. Call `benchmark.describe(max_examples=3)`
3. **Expected:** Output contains exactly 2 sampled pairs (no error, no padding)

### 3. Benchmark.describe() formats dict inputs as JSON

1. Create a Benchmark with examples containing dict inputs
2. Call `benchmark.describe()`
3. **Expected:** Dict values are JSON-serialized in the output, not raw Python repr

### 4. generate_initial() success path

1. Create a MetaAgent with a mock LLM that returns valid pipeline source (with `def run()`)
2. Call `meta_agent.generate_initial(benchmark_description="test benchmark")`
3. **Expected:** Returns `ProposalResult(success=True, proposed_source=<valid source>)` with `cost_usd >= 0`

### 5. generate_initial() failure on invalid code

1. Create a MetaAgent with a mock LLM that returns syntax-error code
2. Call `meta_agent.generate_initial(benchmark_description="test")`
3. **Expected:** Returns `ProposalResult(success=False, error=<message>)`

### 6. generate_initial() failure on missing run()

1. Create a MetaAgent with a mock LLM that returns valid Python but no `run()` function
2. Call `meta_agent.generate_initial(benchmark_description="test")`
3. **Expected:** Returns `ProposalResult(success=False, error=<message about run>)`

### 7. Cold-start prompt includes vocabulary and benchmark

1. Create a MetaAgent and call `_build_cold_start_prompt(benchmark_description="my benchmark")`
2. **Expected:** Prompt contains "Component Vocabulary" section (from S02), "my benchmark" text, and an example pipeline section

### 8. generate_initial() tracks cost

1. Create a MetaAgent with a MetricsCollector, mock LLM returns valid pipeline
2. Call `generate_initial()` and check `result.cost_usd`
3. **Expected:** `cost_usd` reflects the delta from collector snapshots (same pattern as `propose()`)

### 9. cmd_run() triggers cold-start on starter template

1. Initialize a project where `pipeline.py` contains exactly `STARTER_PIPELINE`
2. Mock MetaAgent.generate_initial to return success with valid source
3. Call `main(["run", ...])`
4. **Expected:** `pipeline.py` is overwritten with generated source. stdout contains "Cold-start:". `generate_initial` called exactly once.

### 10. cmd_run() skips cold-start on customized pipeline

1. Initialize a project where `pipeline.py` contains custom code (different from `STARTER_PIPELINE`)
2. Call `main(["run", ...])`
3. **Expected:** `generate_initial` is never called. No "Cold-start:" in stdout. Pipeline unchanged.

### 11. cmd_run() retries once then falls back

1. Initialize a project with `STARTER_PIPELINE`
2. Mock `generate_initial` to return `success=False` both times
3. Call `main(["run", ...])`
4. **Expected:** `generate_initial` called exactly 2 times. stderr contains "Warning: cold-start generation failed". `pipeline.py` unchanged (still starter template). Loop still runs.

### 12. cmd_run() passes benchmark description to generate_initial

1. Initialize a project with `STARTER_PIPELINE` and a benchmark with examples
2. Mock `generate_initial`, capture its argument
3. Call `main(["run", ...])`
4. **Expected:** `generate_initial` receives a non-empty string containing benchmark information

## Edge Cases

### Empty benchmark (zero examples)

1. Create a Benchmark with 0 examples
2. Call `benchmark.describe()`
3. **Expected:** Returns valid string with "0 examples total" and no sample section (no crash)

### generate_initial() with empty LLM response

1. Mock LLM returns empty string
2. Call `generate_initial()`
3. **Expected:** Returns `ProposalResult(success=False)` — does not crash

### Pipeline with only whitespace differences from starter

1. Set `pipeline.py` to `STARTER_PIPELINE` with extra trailing whitespace
2. **Expected:** Cold-start is NOT triggered (exact match fails) — treated as customized

## Failure Signals

- `pytest tests/test_benchmark.py tests/test_meta_agent.py tests/test_cli.py -v` has any failures
- Full suite `pytest -v` shows regressions (should be 267 passing)
- `generate_initial()` returns success=True but source fails `_validate_source()` (internal inconsistency)
- Cold-start triggered on an already-customized pipeline (detection bug)

## Requirements Proved By This UAT

- R015 (Cold-Start Pipeline Generation) — cases 1-12 prove: benchmark description, LLM generation, validation, CLI integration, retry/fallback, end-to-end cold-start flow
- R011 (Structural Search, supporting) — cases 7 proves component vocabulary is included in cold-start prompts

## Not Proven By This UAT

- Live LLM cold-start quality — all tests use mock LLMs. Real generation quality depends on the LLM and prompt effectiveness.
- Cold-start optimization improvement over 10+ iterations — requires live run with real LLM and benchmark
- Archive compression interaction with cold-start — S01 feature, tested separately

## Notes for Tester

- All test cases map directly to existing pytest tests. Running `pytest tests/test_benchmark.py tests/test_meta_agent.py tests/test_cli.py -v` exercises all cases.
- The cold-start prompt includes a hardcoded example pipeline — if primitive APIs change, this example needs updating in `_build_cold_start_prompt()`.
- Cold-start detection is intentionally strict (exact string match). Even a comment change in the starter template will skip cold-start.
