---
id: T01
parent: S02
milestone: M004
provides:
  - BenchmarkGenerator class with generate() → GenerationResult
  - JSON extraction from fenced/bare/prose-wrapped LLM responses
  - Validation pipeline (leakage, diversity, format round-trip)
  - Retry logic on JSON parse failure (max 2 attempts)
key_files:
  - src/autoagent/benchmark_gen.py
  - tests/test_benchmark_gen.py
key_decisions:
  - Default scoring function is "includes" (safer partial matching for generated benchmarks)
  - Diversity threshold at 80% unique inputs — consistent with research recommendation
  - Leakage check uses STARTER_PIPELINE source as the pipeline_source argument
  - Validation constructs Benchmark object directly (no file I/O) for leakage check, uses temp file only for round-trip verification
patterns_established:
  - Section-based prompt construction following meta_agent.py pattern
  - _extract_json with fence → bare → bracket-scan fallback chain
  - ValidationResult frozen dataclass exposes structured diagnostics
observability_surfaces:
  - GenerationResult.validation — leakage_blocked, baseline_scores_identical, diversity_ratio, passed, details
  - GenerationResult.error — structured error string with parse/validation/retry context
  - GenerationResult.success — quick boolean check
duration: 1 context window
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Build BenchmarkGenerator with validation pipeline and tests

**Built BenchmarkGenerator that produces validated {input, expected} benchmarks from LLM-generated JSON with retry, leakage checking, and diversity validation.**

## What Happened

Created `src/autoagent/benchmark_gen.py` with three frozen dataclasses (`ValidationResult`, `GenerationResult`) and the `BenchmarkGenerator` class. The generator builds a section-based prompt (task/goal/sample data/constraints), sends it to the LLM, extracts JSON via a three-stage fallback chain (fenced → bare → bracket-scan), validates the result, and returns a structured `GenerationResult`.

Validation checks: (1) required keys, (2) leakage via `LeakageChecker.check()` against `STARTER_PIPELINE`, (3) input diversity ≥ 80%, (4) round-trip through `Benchmark.from_file()` via temp file.

Retry logic: if JSON extraction fails on first attempt, sends a follow-up prompt asking for raw JSON only, tries once more (max 2 total).

## Verification

- `pytest tests/test_benchmark_gen.py -v` — 24/24 tests pass
- `pytest tests/ -q` — 440/440 tests pass (416 existing + 24 new)
- Import check: `from autoagent.benchmark_gen import BenchmarkGenerator, GenerationResult` — verified via test

Slice-level checks status:
- ✅ `pytest tests/test_benchmark_gen.py -v` — all pass
- ⏳ `pytest tests/test_cli.py -v -k benchmark_gen` — no CLI integration tests yet (T02/T03 scope)
- ✅ `pytest tests/ -q` — 440 pass

## Diagnostics

After calling `gen.generate()`, inspect `result.validation` for structured validation outcomes:
- `result.validation.leakage_blocked` — True if examples contain STARTER_PIPELINE literals
- `result.validation.diversity_ratio` — fraction of unique inputs
- `result.validation.passed` — overall validation gate
- `result.error` — detailed error string on any failure

## Deviations

Leakage test initially used a function signature string which isn't matched by AST literal extraction — fixed to use an actual string literal (the module docstring) from STARTER_PIPELINE. The leakage checker operates on AST-extracted string literals, not arbitrary source substrings.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/benchmark_gen.py` — new module with BenchmarkGenerator, GenerationResult, ValidationResult, _extract_json
- `tests/test_benchmark_gen.py` — 24 tests covering JSON extraction (7), happy path (4), validation (4), retry (3), errors (2), round-trip (2), imports (2)
