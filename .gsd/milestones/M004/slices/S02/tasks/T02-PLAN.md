---
estimated_steps: 4
estimated_files: 2
---

# T02: Wire generator into cmd_new and add CLI integration tests

**Slice:** S02 — Benchmark Generation
**Milestone:** M004

## Description

Integrate `BenchmarkGenerator` into the `cmd_new` CLI flow so that when the interview produces a config with an empty `benchmark.dataset_path`, the generator runs automatically, writes `benchmark.json`, and updates the config before saving. Add CLI integration tests proving the full flow.

## Steps

1. In `cli.py`, import `BenchmarkGenerator` and `GenerationResult`. After the interview completes in `cmd_new`, check `result.config.benchmark.get("dataset_path", "")`. If empty and `result.config.goal` is non-empty, instantiate `BenchmarkGenerator(llm=llm, goal=result.config.goal)` and call `generate()`.

2. On successful generation: write examples to `project_dir / "benchmark.json"` using `json.dump` (pretty-printed). Update config via `dataclasses.replace()` setting `benchmark={"dataset_path": "benchmark.json", "scoring_function": gen_result.scoring_function, ...preserving other keys}`. Print a summary line (e.g., "Generated benchmark with N examples"). On failure: print warning to stderr, continue with config as-is (no benchmark path — `cmd_run` will catch this later).

3. Add CLI integration tests in `tests/test_cli.py` under a new `TestNewBenchmarkGen` class: (a) happy path — interview + generation produces both `config.json` and `benchmark.json`, config has `dataset_path` set, (b) generation failure — interview succeeds but generation fails, config still written without benchmark path, (c) verify generated `benchmark.json` is loadable via `Benchmark.from_file()`.

4. Run full test suite to confirm no regressions.

## Must-Haves

- [x] `cmd_new` calls `BenchmarkGenerator` when `dataset_path` is empty
- [x] Generated benchmark written to `.autoagent/benchmark.json`
- [x] Config updated with benchmark path before `write_config()`
- [x] Generation failure is non-fatal — config still written, warning printed
- [x] CLI integration tests pass
- [x] Full test suite passes (no regressions)

## Verification

- `pytest tests/test_cli.py -v -k benchmark_gen` — integration tests pass
- `pytest tests/ -q` — full suite passes (416 + all new tests)

## Inputs

- `src/autoagent/benchmark_gen.py` — `BenchmarkGenerator` class from T01
- `src/autoagent/cli.py` — existing `cmd_new` function
- `tests/test_cli.py` — existing CLI test patterns (TestNew class from S01)
- `src/autoagent/interview.py` — `SequenceMockLLM` for mock LLM in tests

## Expected Output

- `src/autoagent/cli.py` — modified with benchmark generation integration in `cmd_new`
- `tests/test_cli.py` — new `TestNewBenchmarkGen` class with ≥3 integration tests

## Observability Impact

- **stdout**: `cmd_new` prints "Generated benchmark with N examples (scoring: <function>)" on success — confirms generation happened and what scoring was applied.
- **stderr**: On generation failure, prints "Warning: benchmark generation failed: <error>" — surfaces the specific error (JSON parse failure, validation failure, retry exhaustion) without blocking the interview flow.
- **Config inspection**: After `cmd_new`, check `config.benchmark["dataset_path"]` — if set to `"benchmark.json"`, generation succeeded; if empty string, it either wasn't attempted (no goal) or failed.
- **Benchmark file**: Presence of `.autoagent/benchmark.json` is the definitive signal that generation completed successfully. The file is pretty-printed JSON, inspectable by agents and humans.
