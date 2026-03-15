---
id: T02
parent: S02
milestone: M004
provides:
  - Automatic benchmark generation in cmd_new when no dataset_path provided
  - CLI integration tests proving generation, failure, and round-trip loading
key_files:
  - src/autoagent/cli.py
  - tests/test_cli.py
key_decisions:
  - Benchmark written to .autoagent/benchmark.json (relative path stored in config) — consistent with existing project dir layout
  - Generation failure is non-fatal — warning to stderr, config written without benchmark path, cmd_run catches the missing path later
patterns_established:
  - SequenceMockLLM used with extra responses appended for benchmark generation calls in CLI tests
observability_surfaces:
  - stdout "Generated benchmark with N examples" confirms success
  - stderr "Warning: benchmark generation failed" with error detail on failure
  - config.benchmark.dataset_path presence/absence distinguishes generated vs missing benchmark
duration: ~15min
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T02: Wire generator into cmd_new and add CLI integration tests

**Integrated BenchmarkGenerator into cmd_new so interviews auto-generate benchmark.json when no dataset path is provided, with 3 CLI integration tests.**

## What Happened

Added benchmark generation logic to `cmd_new` in `cli.py`: after the interview completes, if `config.benchmark.dataset_path` is empty and `config.goal` is set, a `BenchmarkGenerator` is instantiated with the interview's LLM and goal, then `generate()` is called. On success, examples are written to `.autoagent/benchmark.json` (pretty-printed) and the config is updated with `dataset_path` and `scoring_function` before `write_config()`. On failure, a warning is printed to stderr and the config is written as-is.

Added `TestNewBenchmarkGen` class to `tests/test_cli.py` with 3 tests:
1. Happy path — interview + generation produces both config.json and benchmark.json with correct config fields
2. Generation failure — invalid LLM responses cause warning but config still written without benchmark path
3. Round-trip — generated benchmark.json is loadable via `Benchmark.from_file()` with correct examples

## Verification

- `pytest tests/test_cli.py -v -k benchmark_gen` — 3 passed
- `pytest tests/test_benchmark_gen.py -v` — 24 passed (T01 unit tests)
- `pytest tests/ -q` — 443 passed, 0 failures (full suite, no regressions)

## Diagnostics

After `cmd_new` runs:
- Check stdout for "Generated benchmark with N examples (scoring: includes)" — confirms generation succeeded
- Check stderr for "Warning: benchmark generation failed" — surfaces parse/validation error details
- Inspect `config.json` → `benchmark.dataset_path`: `"benchmark.json"` means generated, `""` means skipped/failed
- `.autoagent/benchmark.json` presence is the definitive success signal

## Deviations

Renamed test methods from `test_happy_path_generates_benchmark` etc. to `test_benchmark_gen_*` pattern so the slice-level `-k benchmark_gen` filter matches all 3 tests.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/cli.py` — Added `import json`, `BenchmarkGenerator`/`GenerationResult` imports, and benchmark generation block in `cmd_new`
- `tests/test_cli.py` — Added `TestNewBenchmarkGen` class with 3 integration tests, `json` and `Benchmark` imports
- `.gsd/milestones/M004/slices/S02/tasks/T02-PLAN.md` — Added Observability Impact section (pre-flight fix), marked must-haves done
