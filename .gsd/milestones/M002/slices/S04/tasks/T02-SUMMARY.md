---
id: T02
parent: S04
milestone: M002
provides:
  - Cold-start detection and generation wired into cmd_run()
  - 4 integration tests covering cold-start CLI paths
key_files:
  - src/autoagent/cli.py
  - tests/test_cli.py
key_decisions:
  - Cold-start detection uses exact string comparison against STARTER_PIPELINE — any edit (even whitespace) skips cold-start
  - Retry logic is inline (not a loop) for clarity — exactly one retry attempt before fallback
patterns_established:
  - Cold-start messages on stdout prefixed with "Cold-start:" for grep-ability; warnings on stderr
  - Tests use main() directly with mock.patch on MetaAgent and OptimizationLoop — avoids subprocess for mockability
observability_surfaces:
  - stdout messages prefixed "Cold-start:" indicate trigger/success/retry/fallback
  - stderr warning when both generation attempts fail
duration: 15min
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T02: Wire cold-start into CLI and verify end-to-end

**Wired cold-start pipeline generation into `cmd_run()` with retry logic and 4 integration tests.**

## What Happened

Added cold-start detection to `cmd_run()` between meta-agent creation and the optimization loop. Reads `pipeline.py` and compares to `STARTER_PIPELINE`. On match:
1. Calls `benchmark.describe()` for benchmark description
2. Calls `meta_agent.generate_initial(benchmark_desc)`
3. On success: writes `result.proposed_source` to `pipeline.py`
4. On failure: retries once. Second failure prints warning to stderr and continues with starter template.

Imported `STARTER_PIPELINE` from `autoagent.state` in cli.py.

Added 4 integration tests using `main()` directly with `unittest.mock.patch` on `MetaAgent` and `OptimizationLoop`:
- Cold-start triggered → pipeline rewritten
- Customized pipeline → cold-start skipped, `generate_initial` never called
- Both attempts fail → warning on stderr, pipeline unchanged, 2 calls made
- `generate_initial` receives non-empty benchmark description string

## Verification

- `pytest tests/test_cli.py -v` — 16 tests pass (12 existing + 4 new cold-start)
- `pytest -v` — 267 tests pass, zero failures
- Slice-level: `pytest tests/test_benchmark.py tests/test_meta_agent.py tests/test_cli.py -v` — 86 passed

## Diagnostics

- Grep stdout for `Cold-start:` to see if cold-start was attempted and its outcome
- Grep stderr for `Warning: cold-start generation failed` to detect fallback
- Compare `pipeline.py` content against `STARTER_PIPELINE` to verify whether cold-start generation produced new content

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/cli.py` — Added STARTER_PIPELINE import, cold-start detection + retry logic in cmd_run()
- `tests/test_cli.py` — Added TestColdStart class with 4 integration tests, helper _init_project_with_benchmark()
- `.gsd/milestones/M002/slices/S04/tasks/T02-PLAN.md` — Added Observability Impact section
