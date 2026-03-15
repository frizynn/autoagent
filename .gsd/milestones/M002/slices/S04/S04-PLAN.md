# S04: Cold-Start Pipeline Generation

**Goal:** `autoagent run` with no custom pipeline generates an initial pipeline from goal + benchmark using the component vocabulary, validates it, and begins optimizing.
**Demo:** Run `autoagent run` on a project with the starter template pipeline → cold-start generates a real pipeline via LLM → loop optimizes from that baseline.

## Must-Haves

- Benchmark description method producing compact text (examples sampled, scorer name, format hints) under 500 tokens
- `MetaAgent.generate_initial(benchmark_description)` generating valid pipeline source via same extract/validate path as `propose()`
- Cold-start detection in `cmd_run()` — exact match against `STARTER_PIPELINE`
- Cold-start pipelines pass `_validate_source()` (compile + callable run())
- Generated pipeline uses `primitives` parameter (not raw provider imports)
- One retry on generation failure; fallback to starter template (loop handles 0.0 score gracefully)
- Cold-start event logged visibly for user awareness

## Verification

- `pytest tests/test_benchmark.py tests/test_meta_agent.py tests/test_cli.py -v` — all pass
- New tests cover: `Benchmark.describe()` output structure, `generate_initial()` success path, `generate_initial()` validation failure, cold-start detection in CLI, CLI cold-start with successful generation, CLI with already-customized pipeline skips cold-start

## Integration Closure

- Upstream surfaces consumed: `build_component_vocabulary()` from S02, `_extract_source()`/`_validate_source()` from M01, `STARTER_PIPELINE` from state.py
- New wiring: `cmd_run()` detects cold-start → calls `meta_agent.generate_initial()` → writes pipeline.py → enters loop
- What remains before milestone is truly usable end-to-end: nothing — S04 is the final assembly slice

## Tasks

- [x] **T01: Implement benchmark description and cold-start generation** `est:45m`
  - Why: Core cold-start capability — the LLM needs benchmark context to generate a relevant pipeline, and MetaAgent needs a generation method
  - Files: `src/autoagent/benchmark.py`, `src/autoagent/meta_agent.py`, `tests/test_benchmark.py`, `tests/test_meta_agent.py`
  - Do: Add `Benchmark.describe()` returning compact text (sample 2-3 examples, scorer name, total count, I/O format). Add `MetaAgent.generate_initial(benchmark_description: str) -> ProposalResult` — builds cold-start prompt (system instructions for from-scratch generation, goal, vocabulary, benchmark description, primitive usage rules, one concrete example), calls LLM, uses `_extract_source()` → `_validate_source()`. Same cost tracking pattern as `propose()`. Unit tests for both.
  - Verify: `pytest tests/test_benchmark.py tests/test_meta_agent.py -v`
  - Done when: `generate_initial()` returns `ProposalResult` with valid pipeline source from a mock LLM response, and `Benchmark.describe()` produces text with example samples and scorer info

- [x] **T02: Wire cold-start into CLI and verify end-to-end** `est:30m`
  - Why: Users need cold-start to happen transparently — detect starter template, generate, write, then loop
  - Files: `src/autoagent/cli.py`, `tests/test_cli.py`
  - Do: In `cmd_run()`, after benchmark loading and before loop creation, check if `pipeline_path.read_text() == STARTER_PIPELINE`. If so, log "No custom pipeline found. Generating initial pipeline from goal and benchmark...", call `meta_agent.generate_initial(benchmark_desc)`. On success, write to pipeline.py. On failure, retry once. On second failure, log warning and continue with starter (loop handles 0.0). Import `STARTER_PIPELINE` from state. Add `Benchmark.describe()` call to produce `benchmark_desc`. Integration tests covering: cold-start triggered on starter template, cold-start skipped on customized pipeline, successful generation writes new pipeline, generation failure falls through to loop.
  - Verify: `pytest tests/test_cli.py -v` and full suite `pytest -v`
  - Done when: `cmd_run()` with starter template triggers cold-start generation before loop entry, and all existing tests still pass

## Observability / Diagnostics

- **Cold-start event**: `cmd_run()` logs clearly when cold-start is triggered, including generation outcome (success/retry/fallback)
- **Benchmark description**: `describe()` output is inspectable — it's a plain string returned to the caller, included in the LLM prompt (visible in prompt logs)
- **Generation failure visibility**: `generate_initial()` returns `ProposalResult` with `success=False` and `error` string on failure — same structured error surface as `propose()`
- **Cost tracking**: `generate_initial()` cost captured via collector snapshot pattern — appears in MetricsCollector aggregates alongside proposal costs
- **Redaction**: No secrets involved in cold-start pipeline generation — benchmark data and prompts are not sensitive

## Files Likely Touched

- `src/autoagent/benchmark.py`
- `src/autoagent/meta_agent.py`
- `src/autoagent/cli.py`
- `tests/test_benchmark.py`
- `tests/test_meta_agent.py`
- `tests/test_cli.py`
