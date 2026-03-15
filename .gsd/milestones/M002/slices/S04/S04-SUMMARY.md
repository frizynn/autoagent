---
id: S04
parent: M002
milestone: M002
provides:
  - Benchmark.describe() method for compact benchmark description (~500 tokens)
  - MetaAgent.generate_initial() for cold-start pipeline generation via LLM
  - Cold-start detection and generation wired into cmd_run() with retry + fallback
requires:
  - slice: S02
    provides: build_component_vocabulary() for pipeline generation prompts
affects: []
key_files:
  - src/autoagent/benchmark.py
  - src/autoagent/meta_agent.py
  - src/autoagent/cli.py
  - tests/test_benchmark.py
  - tests/test_meta_agent.py
  - tests/test_cli.py
key_decisions:
  - Cold-start detection uses exact string comparison against STARTER_PIPELINE — any edit skips cold-start
  - generate_initial() uses separate _build_cold_start_prompt() with different system instructions and example pipeline, not reusing _build_prompt()
  - describe() samples first N examples deterministically (not random) for reproducible output
  - Exactly one retry on generation failure, then fallback to starter template — loop handles 0.0 gracefully
patterns_established:
  - _build_cold_start_prompt() follows same section-based prompt construction as _build_prompt()
  - generate_initial() uses identical extract→validate→cost-track pattern as propose()
  - Cold-start stdout messages prefixed "Cold-start:" for grep-ability; warnings on stderr
observability_surfaces:
  - stdout "Cold-start:" prefix indicates trigger/success/retry/fallback
  - stderr warning when both generation attempts fail
  - generate_initial() returns ProposalResult with success/error/cost_usd
  - Benchmark.describe() output inspectable as plain string
drill_down_paths:
  - .gsd/milestones/M002/slices/S04/tasks/T01-SUMMARY.md
  - .gsd/milestones/M002/slices/S04/tasks/T02-SUMMARY.md
duration: 30m
verification_result: passed
completed_at: 2026-03-14
---

# S04: Cold-Start Pipeline Generation

**`autoagent run` with no custom pipeline generates an initial pipeline from goal + benchmark via LLM, validates it, and begins optimizing from scratch.**

## What Happened

Two tasks, both straightforward:

**T01** added `Benchmark.describe(max_examples=3)` — produces a compact text block with total count, scorer name, sampled input/expected pairs, and format hints. Also added `MetaAgent.generate_initial(benchmark_description)` which builds a cold-start-specific prompt via `_build_cold_start_prompt()` containing system instructions for from-scratch generation, goal, component vocabulary (from S02), benchmark description, and a concrete example pipeline. Uses the same `_extract_source()` → `_validate_source()` pipeline and collector snapshot cost tracking as `propose()`.

**T02** wired cold-start into `cmd_run()`. After benchmark loading and meta-agent creation, reads `pipeline.py` and compares to `STARTER_PIPELINE`. On match: calls `benchmark.describe()`, then `meta_agent.generate_initial()`. On success, writes generated source to `pipeline.py`. On failure, retries once. On second failure, logs warning and continues with starter template (loop handles 0.0 score gracefully). Imported `STARTER_PIPELINE` from `autoagent.state`.

## Verification

- `pytest tests/test_benchmark.py tests/test_meta_agent.py tests/test_cli.py -v` — 86 passed
- `pytest -v` — 267 passed, zero failures (full suite, no regressions)
- Tests cover: `describe()` output structure (6 tests), `generate_initial()` success/failure/cost paths (7 tests), CLI cold-start trigger/skip/retry/benchmark-description (4 tests)

## Requirements Advanced

- R015 (Cold-Start Pipeline Generation) — cold-start generation implemented end-to-end: detection → LLM generation → validation → write → optimize
- R011 (Structural Search) — cold-start uses component vocabulary from S02 to generate architecturally-aware initial pipelines
- R013 (Autonomous Search Strategy) — cold-start feeds into the full M002 stack (vocabulary, strategy signals, archive compression)

## Requirements Validated

- R015 (Cold-Start Pipeline Generation) — `autoagent run` with starter template generates initial pipeline via LLM using goal + benchmark + component vocabulary, validates it compiles with callable run(), writes it, and enters optimization loop. Retry + fallback on failure. 17 tests across benchmark description, generation, and CLI integration.

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

None.

## Known Limitations

- Cold-start generation quality depends entirely on the LLM's ability to produce valid pipelines from the prompt — no mechanical fallback to a pattern-specific template
- describe() samples first N examples, not a representative sample — could miss diversity in large benchmarks
- No cold-start-specific retry with modified prompt (same prompt used for retry)

## Follow-ups

- none — S04 is the final M002 slice

## Files Created/Modified

- `src/autoagent/benchmark.py` — added `describe()` method
- `src/autoagent/meta_agent.py` — added `_build_cold_start_prompt()` and `generate_initial()` methods
- `src/autoagent/cli.py` — added STARTER_PIPELINE import, cold-start detection + retry logic in `cmd_run()`
- `tests/test_benchmark.py` — added TestBenchmarkDescribe (6 tests)
- `tests/test_meta_agent.py` — added TestGenerateInitial (7 tests)
- `tests/test_cli.py` — added TestColdStart (4 tests)

## Forward Intelligence

### What the next slice should know
- M002 is complete. The full stack is: component vocabulary → strategy signals → archive compression → cold-start generation → optimization loop. All wired together in `cmd_run()`.
- Cold-start prompt is in `_build_cold_start_prompt()` — separate from the iteration prompt in `_build_prompt()`. If prompt structure changes, both need updating.

### What's fragile
- Cold-start detection relies on exact string match against `STARTER_PIPELINE` — if the starter template changes, detection must be updated in tandem
- `_build_cold_start_prompt()` includes a hardcoded example pipeline — if primitive APIs change, the example may become invalid

### Authoritative diagnostics
- `pytest -v` (267 tests) — full regression suite, all M001+M002 features
- Grep stdout for `Cold-start:` to trace cold-start behavior in production runs

### What assumptions changed
- none — slice executed cleanly per plan
