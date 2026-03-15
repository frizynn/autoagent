# S02: Benchmark Generation

**Goal:** When the interview finds no benchmark, generate valid `{input, expected}` JSON from goal + sample data, validate for leakage and discriminating power, and write to `.autoagent/benchmark.json`.
**Demo:** `BenchmarkGenerator` produces a benchmark from a goal string via MockLLM, passes leakage + baseline validation, and `cmd_new` automatically generates and writes it when no benchmark path is provided.

## Must-Haves

- `BenchmarkGenerator` class takes goal + optional sample data + LLMProtocol, generates `{input, expected}` JSON examples
- LLM response parsing handles markdown-fenced JSON, prose wrapping, and malformed output with retry (max 2 attempts)
- Validation pipeline: leakage check via `LeakageChecker.check()` + baseline score check (not all identical scores) + diversity check (≥80% unique inputs)
- `GenerationResult` dataclass with examples, scoring_function, validation, success, error
- Integration with `cmd_new`: when `dataset_path` is empty after interview, call generator, write benchmark, update config
- Generated benchmark consumable by `Benchmark.from_file()` — round-trip validated
- Default scorer is `includes` (safer for generated benchmarks), overridable

## Proof Level

- This slice proves: contract + integration
- Real runtime required: no (MockLLM for all tests)
- Human/UAT required: no

## Verification

- `pytest tests/test_benchmark_gen.py -v` — unit tests for generator, JSON parsing, validation, retry, error cases
- `pytest tests/test_cli.py -v -k benchmark_gen` — CLI integration tests for `cmd_new` with benchmark generation
- `pytest tests/ -q` — all tests pass (416 existing + new)

## Observability / Diagnostics

- Runtime signals: `GenerationResult.validation` exposes leakage_result, baseline_scores, diversity_ratio for inspection
- Inspection surfaces: `GenerationResult` dataclass fields — success/error/validation all structured
- Failure visibility: `GenerationResult.error` captures parse failures, validation failures, retry exhaustion with context
- Redaction constraints: none

## Integration Closure

- Upstream surfaces consumed: `LLMProtocol` (primitives), `LeakageChecker` (leakage.py), `Benchmark.from_file()` (benchmark.py), `Evaluator.evaluate()` (evaluation.py), `STARTER_PIPELINE` (state.py), `ProjectConfig` (state.py), `StateManager.write_config()` (state.py)
- New wiring introduced: `cmd_new` calls `BenchmarkGenerator.generate()` when no benchmark path, writes result, updates config before `write_config()`
- What remains before milestone is truly usable end-to-end: S03 (reporting + end-to-end assembly)

## Tasks

- [x] **T01: Build BenchmarkGenerator with validation pipeline and tests** `est:1h`
  - Why: Core deliverable — standalone generator class with LLM prompting, JSON extraction, leakage + baseline validation, all testable in isolation
  - Files: `src/autoagent/benchmark_gen.py`, `tests/test_benchmark_gen.py`
  - Do: Create `BenchmarkGenerator` class with `generate()` method. Build prompt from goal + sample data. Extract JSON from LLM response (strip markdown fences, parse array). Run validation: `LeakageChecker.check()` against `STARTER_PIPELINE`, baseline score diversity check (not all identical), input diversity ≥80%. Return `GenerationResult` with structured validation. Retry on JSON parse failure (max 2). Use `SequenceMockLLM` for all tests. Test happy path, validation failures, retry on bad JSON, diversity check, leakage detection.
  - Verify: `pytest tests/test_benchmark_gen.py -v` — all pass
  - Done when: `BenchmarkGenerator.generate()` returns valid `GenerationResult` with examples that round-trip through `Benchmark.from_file()`, and validation catches degenerate benchmarks

- [x] **T02: Wire generator into cmd_new and add CLI integration tests** `est:30m`
  - Why: Closes the integration — benchmark generation triggers automatically when interview leaves dataset_path empty
  - Files: `src/autoagent/cli.py`, `tests/test_cli.py`
  - Do: In `cmd_new`, after interview completes, check if `config.benchmark["dataset_path"]` is empty. If so, call `BenchmarkGenerator(llm, config.goal).generate()`. On success: write examples to `.autoagent/benchmark.json` via `_atomic_write_json`, update config with `dataclasses.replace()` to set `dataset_path` and `scoring_function`, then write updated config. On failure: print error, continue (config still written without benchmark). Add CLI integration tests using `SequenceMockLLM` with benchmark generation responses.
  - Verify: `pytest tests/test_cli.py -v -k benchmark_gen` — all pass; `pytest tests/ -q` — full suite passes
  - Done when: `autoagent new` with no benchmark input produces both `config.json` and `benchmark.json` in `.autoagent/`, and `cmd_run` can load the generated benchmark

## Files Likely Touched

- `src/autoagent/benchmark_gen.py` (new)
- `tests/test_benchmark_gen.py` (new)
- `src/autoagent/cli.py`
- `tests/test_cli.py`
