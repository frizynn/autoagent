---
id: S02
parent: M004
milestone: M004
provides:
  - BenchmarkGenerator class with generate() → GenerationResult
  - JSON extraction from fenced/bare/prose-wrapped LLM responses with retry
  - Validation pipeline (leakage via LeakageChecker, input diversity ≥80%, format round-trip)
  - Automatic benchmark generation in cmd_new when no dataset_path provided
  - Generated benchmarks consumable by Benchmark.from_file()
requires:
  - slice: S01
    provides: ProjectConfig with goal and benchmark fields, LLMProtocol, cmd_new interview flow
affects:
  - S03
key_files:
  - src/autoagent/benchmark_gen.py
  - tests/test_benchmark_gen.py
  - src/autoagent/cli.py
  - tests/test_cli.py
key_decisions:
  - Default scoring function is "includes" — safer partial matching for generated benchmarks
  - Diversity threshold at 80% unique inputs
  - Leakage check uses STARTER_PIPELINE source as pipeline_source argument
  - Generation failure is non-fatal — config written without benchmark, cmd_run catches missing path later
  - Benchmark written to .autoagent/benchmark.json with relative path in config
patterns_established:
  - Section-based prompt construction following meta_agent.py pattern
  - _extract_json with fence → bare → bracket-scan fallback chain
  - ValidationResult frozen dataclass exposes structured diagnostics
  - SequenceMockLLM used with extra responses appended for benchmark generation in CLI tests
observability_surfaces:
  - GenerationResult.validation — leakage_blocked, baseline_scores_identical, diversity_ratio, passed, details
  - GenerationResult.error — structured error string with parse/validation/retry context
  - stdout "Generated benchmark with N examples" on success; stderr warning on failure
  - config.benchmark.dataset_path presence/absence distinguishes generated vs missing benchmark
drill_down_paths:
  - .gsd/milestones/M004/slices/S02/tasks/T01-SUMMARY.md
  - .gsd/milestones/M004/slices/S02/tasks/T02-SUMMARY.md
duration: 2 context windows
verification_result: passed
completed_at: 2026-03-14
---

# S02: Benchmark Generation

**BenchmarkGenerator produces validated {input, expected} benchmarks from LLM-generated JSON, auto-triggered by cmd_new when no benchmark path is provided.**

## What Happened

Built `src/autoagent/benchmark_gen.py` with `BenchmarkGenerator`, `GenerationResult`, and `ValidationResult` frozen dataclasses. The generator builds a section-based prompt from goal + optional sample data, sends it to the LLM, and extracts JSON via a three-stage fallback chain (markdown-fenced → bare JSON → bracket-scan). On parse failure, retries once with a follow-up prompt requesting raw JSON only (max 2 attempts total).

Validation pipeline runs three checks: (1) leakage detection via `LeakageChecker.check()` against `STARTER_PIPELINE`, (2) input diversity ≥ 80% unique inputs, (3) format round-trip through `Benchmark.from_file()` via temp file. Results are structured in `ValidationResult` with individual diagnostics.

Wired into `cmd_new` in `cli.py`: after interview completes, if `config.benchmark.dataset_path` is empty and `config.goal` is set, calls `BenchmarkGenerator(llm, goal).generate()`. On success, writes examples to `.autoagent/benchmark.json` and updates config with `dataset_path` and `scoring_function` before `write_config()`. On failure, prints warning to stderr and writes config as-is — non-fatal by design.

## Verification

- `pytest tests/test_benchmark_gen.py -v` — 24/24 passed (JSON extraction, happy path, validation, retry, error handling, round-trip, imports)
- `pytest tests/test_cli.py -v -k benchmark_gen` — 3/3 passed (happy path, failure handling, round-trip loading)
- `pytest tests/ -q` — 443/443 passed (no regressions)

## Requirements Advanced

- R023 (Automatic Benchmark Generation) — now validated: BenchmarkGenerator produces {input, expected} JSON from goal, validates for leakage and discriminating power, integrates into cmd_new

## Requirements Validated

- R023 — BenchmarkGenerator generates benchmarks via LLM, validates with LeakageChecker + diversity + round-trip, writes to .autoagent/benchmark.json, consumable by evaluation loop. 24 unit tests + 3 CLI integration tests.

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

Leakage test initially used a function signature string which isn't matched by AST literal extraction — fixed to use an actual string literal (the module docstring) from STARTER_PIPELINE. The leakage checker operates on AST-extracted string literals, not arbitrary source substrings.

## Known Limitations

- Baseline validation (scores 0.1–0.9 from D056) is checked structurally but not with a real evaluation pass — the diversity check (≥80% unique inputs) serves as the discriminating power proxy
- No sample data ingestion beyond what the user provides via interview — generator relies on LLM creativity for example synthesis

## Follow-ups

- none

## Files Created/Modified

- `src/autoagent/benchmark_gen.py` — new module: BenchmarkGenerator, GenerationResult, ValidationResult, _extract_json
- `tests/test_benchmark_gen.py` — 24 tests covering JSON extraction, happy path, validation, retry, errors, round-trip, imports
- `src/autoagent/cli.py` — benchmark generation block in cmd_new, imports for BenchmarkGenerator/GenerationResult/json
- `tests/test_cli.py` — TestNewBenchmarkGen class with 3 CLI integration tests

## Forward Intelligence

### What the next slice should know
- `BenchmarkGenerator` uses the same `LLMProtocol` as everything else — SequenceMockLLM works for end-to-end tests, just append benchmark generation responses after interview responses
- Generated benchmarks land at `.autoagent/benchmark.json` with relative path `"benchmark.json"` stored in config — `Benchmark.from_file()` resolves relative to project dir
- `GenerationResult.examples` is a list of `{"input": ..., "expected": ...}` dicts — same format as benchmark JSON

### What's fragile
- `_extract_json` bracket-scan fallback finds the first `[` and scans for balanced brackets — deeply nested JSON with unbalanced brackets in string values could confuse it
- SequenceMockLLM response ordering in CLI tests must match exact call sequence: interview phases first, then benchmark generation calls

### Authoritative diagnostics
- `GenerationResult.validation` — structured validation outcome with individual check results
- `GenerationResult.error` — descriptive error string on any failure path

### What assumptions changed
- D056 (baseline validation 0.1–0.9) was planned but the actual validation uses diversity ratio + leakage + round-trip instead of running a real baseline pipeline — avoids coupling to evaluation infrastructure in the generator
