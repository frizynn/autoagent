---
id: T01
parent: S04
milestone: M002
provides:
  - Benchmark.describe() method for compact benchmark description
  - MetaAgent.generate_initial() method for cold-start pipeline generation
key_files:
  - src/autoagent/benchmark.py
  - src/autoagent/meta_agent.py
  - tests/test_benchmark.py
  - tests/test_meta_agent.py
key_decisions:
  - describe() samples first N examples (not random) for deterministic output
  - generate_initial() uses a separate _build_cold_start_prompt() rather than reusing _build_prompt() — the cold-start prompt has different system instructions and includes an example pipeline section
  - Cold-start prompt includes a concrete example pipeline to anchor the LLM's output format
patterns_established:
  - _build_cold_start_prompt() follows same section-based prompt construction as _build_prompt()
  - generate_initial() uses identical extract→validate→cost-track pattern as propose()
observability_surfaces:
  - generate_initial() returns ProposalResult with success/error/cost_usd — same diagnostic interface as propose()
  - Benchmark.describe() output is a plain string inspectable by calling it directly
duration: 15m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Implement benchmark description and cold-start generation

**Added `Benchmark.describe()` for compact benchmark descriptions and `MetaAgent.generate_initial()` for cold-start pipeline generation from scratch.**

## What Happened

1. Added `Benchmark.describe(max_examples=3)` — produces a compact text block with total example count, scorer name, sampled input/expected pairs, and usage hints. Dict/list inputs are JSON-serialized for clarity.

2. Added `MetaAgent.generate_initial(benchmark_description)` — builds a cold-start-specific prompt via `_build_cold_start_prompt()` with from-scratch system instructions, goal, component vocabulary, benchmark description, and a concrete example pipeline. Uses the same `_extract_source()` → `_validate_source()` pipeline and collector snapshot cost tracking as `propose()`.

3. Added 6 tests for `describe()`: scorer name inclusion, total count, sampling behavior, fewer-than-max edge case, output size constraint, dict input formatting.

4. Added 7 tests for `generate_initial()`: success path, syntax error failure, missing-run failure, prompt content verification (vocabulary + benchmark + example pipeline), cost tracking, empty response.

## Verification

- `pytest tests/test_benchmark.py tests/test_meta_agent.py -v` — 70 tests passed (13 new)
- `pytest tests/test_benchmark.py tests/test_meta_agent.py tests/test_cli.py -v` — 82 tests passed (slice-level verification, all pass)
- CLI tests from T02 not yet written — expected, this is an intermediate task

## Diagnostics

- Call `benchmark.describe()` to inspect what the LLM sees about the benchmark
- Call `agent._build_cold_start_prompt(desc)` to inspect the full cold-start prompt
- `generate_initial()` returns `ProposalResult` with `success`, `error`, `cost_usd` fields

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/benchmark.py` — added `describe()` method to Benchmark class
- `src/autoagent/meta_agent.py` — added `_build_cold_start_prompt()` and `generate_initial()` methods to MetaAgent class
- `tests/test_benchmark.py` — added TestBenchmarkDescribe class with 6 tests
- `tests/test_meta_agent.py` — added TestGenerateInitial class with 7 tests
- `.gsd/milestones/M002/slices/S04/S04-PLAN.md` — added Observability / Diagnostics section
- `.gsd/milestones/M002/slices/S04/tasks/T01-PLAN.md` — added Observability Impact section
