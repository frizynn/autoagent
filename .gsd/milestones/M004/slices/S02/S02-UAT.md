# S02: Benchmark Generation — UAT

**Milestone:** M004
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: All generation and validation logic is exercised through MockLLM — no live LLM or runtime services needed. Generated files are deterministic and inspectable.

## Preconditions

- Python 3.11+ with `.venv` activated
- `pip install -e .` completed (autoagent package importable)
- All 443 tests passing (`pytest tests/ -q`)

## Smoke Test

Run `pytest tests/test_benchmark_gen.py -v && pytest tests/test_cli.py -v -k benchmark_gen` — 27 tests pass, confirming generator and CLI integration both work.

## Test Cases

### 1. Generator produces valid benchmark from goal

1. Create a `BenchmarkGenerator` with a `SequenceMockLLM` that returns a JSON array of 5 `{"input": ..., "expected": ...}` objects
2. Call `generator.generate()`
3. **Expected:** `result.success` is True, `result.examples` has 5 items, each with `"input"`, `"expected"`, and auto-assigned `"id"` keys, `result.scoring_function` is `"includes"`

### 2. Generator retries on malformed JSON

1. Create a `SequenceMockLLM` with first response being invalid JSON (`"Here are some examples..."`) and second response being valid JSON array
2. Call `generator.generate()`
3. **Expected:** `result.success` is True — generator extracted valid JSON on retry. Second prompt asked for raw JSON only.

### 3. Generator fails after exhausting retries

1. Create a `SequenceMockLLM` with two responses that are both unparseable (`"not json"`, `"still not json"`)
2. Call `generator.generate()`
3. **Expected:** `result.success` is False, `result.error` contains parse failure context, `result.examples` is empty list

### 4. Leakage detection blocks contaminated benchmark

1. Create a `SequenceMockLLM` returning examples where an `expected` value contains a string literal from `STARTER_PIPELINE` (the module docstring)
2. Call `generator.generate()`
3. **Expected:** `result.success` is False, `result.validation.leakage_blocked` is True

### 5. Diversity check rejects duplicate inputs

1. Create a `SequenceMockLLM` returning 5 examples where 4 have identical `input` values (diversity = 40%, below 80% threshold)
2. Call `generator.generate()`
3. **Expected:** `result.success` is False, `result.validation.diversity_ratio` < 0.8

### 6. cmd_new generates benchmark when no dataset_path provided

1. Set up a temp directory with `SequenceMockLLM` responses for all 6 interview phases + benchmark generation
2. Run `cmd_new` with the mock LLM (interview answers leave `dataset_path` empty)
3. **Expected:** `.autoagent/config.json` exists with `benchmark.dataset_path` set to `"benchmark.json"`. `.autoagent/benchmark.json` exists and contains valid JSON array. stdout includes "Generated benchmark with N examples".

### 7. cmd_new handles generation failure gracefully

1. Set up `SequenceMockLLM` with valid interview responses but invalid benchmark generation responses
2. Run `cmd_new`
3. **Expected:** `.autoagent/config.json` exists with `benchmark.dataset_path` set to `""`. No `benchmark.json` file created. stderr includes "Warning: benchmark generation failed".

### 8. Generated benchmark round-trips through Benchmark.from_file()

1. After test case 6, load `.autoagent/benchmark.json` via `Benchmark.from_file()`
2. **Expected:** Benchmark loads without error, `len(benchmark.examples)` matches the generated count, each example has `input` and `expected` fields matching the generated content

## Edge Cases

### Empty goal string

1. Create `BenchmarkGenerator` with `goal=""`
2. Call `generate()`
3. **Expected:** Generator still attempts — the LLM prompt includes the empty goal. Result depends on LLM response quality.

### JSON extraction from markdown-fenced block

1. LLM returns response wrapped in ````json\n[...]\n````
2. `_extract_json()` is called on the response
3. **Expected:** JSON is extracted from within the fences, ignoring surrounding prose

### JSON extraction from prose-wrapped response

1. LLM returns `"Here are the examples:\n[{...}]\nI hope these help!"`
2. `_extract_json()` is called
3. **Expected:** Bracket-scan fallback finds the `[` and extracts the balanced array

### JSON object instead of array

1. LLM returns `{"examples": [...]}` (object, not array)
2. `_extract_json()` is called
3. **Expected:** Raises ValueError — generator expects a JSON array at the top level

## Failure Signals

- `pytest tests/test_benchmark_gen.py` has any failures — generator logic broken
- `pytest tests/test_cli.py -k benchmark_gen` has any failures — CLI integration broken
- `GenerationResult.success` is False when valid JSON was provided — validation pipeline overly strict
- `.autoagent/benchmark.json` not loadable by `Benchmark.from_file()` — format contract broken
- Full test suite (`pytest tests/ -q`) shows regressions — new code broke existing functionality

## Requirements Proved By This UAT

- R023 (Automatic Benchmark Generation) — test cases 1, 6, 8 prove generation from goal, CLI integration, and format compatibility with evaluation loop

## Not Proven By This UAT

- Real LLM benchmark quality — all tests use MockLLM; whether a real LLM generates useful benchmarks is a manual spot-check concern
- Baseline evaluation pass — D056's 0.1–0.9 score range validation is not mechanically tested (diversity + leakage serve as proxies)
- End-to-end flow from interview through optimization to report — that's S03 scope

## Notes for Tester

- All tests are deterministic via SequenceMockLLM — no API keys or network access needed
- The leakage test (case 4) depends on STARTER_PIPELINE's module docstring being a string literal detectable by AST extraction — if STARTER_PIPELINE changes, the test fixture may need updating
- CLI integration tests create temp directories and clean up after themselves
