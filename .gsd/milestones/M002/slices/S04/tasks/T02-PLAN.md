---
estimated_steps: 4
estimated_files: 2
---

# T02: Wire cold-start into CLI and verify end-to-end

**Slice:** S04 — Cold-Start Pipeline Generation
**Milestone:** M002

## Description

Wire cold-start detection and generation into `cmd_run()` so it happens transparently before the optimization loop starts. Detect by comparing pipeline.py content to `STARTER_PIPELINE`. On match, call `meta_agent.generate_initial()` with benchmark description, write successful result to pipeline.py, then enter loop normally. One retry on failure; second failure logs warning and continues with starter template. Add integration tests exercising the full cold-start path through cmd_run.

## Steps

1. In `cmd_run()`, after benchmark loading and meta_agent creation, read pipeline.py and compare to `STARTER_PIPELINE`. If match: log cold-start message, call `benchmark.describe()` to get description, call `meta_agent.generate_initial(benchmark_desc)`. On success: write `result.proposed_source` to pipeline.py. On failure: retry once. On second failure: log warning, continue (loop will score 0.0 and improve).
2. Import `STARTER_PIPELINE` from `autoagent.state` in cli.py.
3. Add integration tests in `tests/test_cli.py`: (a) cold-start triggered when pipeline matches STARTER_PIPELINE — mock MetaAgent.generate_initial to return valid source, verify pipeline.py was rewritten; (b) cold-start skipped when pipeline has been customized; (c) cold-start generation failure after retries falls through to loop; (d) generate_initial receives benchmark description.
4. Run full test suite `pytest -v` to verify no regressions.

## Must-Haves

- [ ] `cmd_run()` detects STARTER_PIPELINE and triggers cold-start before loop
- [ ] Successful generation writes new pipeline.py content
- [ ] One retry on generation failure; second failure continues with starter
- [ ] Cold-start event printed/logged for user awareness
- [ ] Customized pipeline (any edit to starter) skips cold-start entirely
- [ ] All existing tests pass (no regressions)

## Verification

- `pytest tests/test_cli.py -v` — new cold-start CLI tests pass
- `pytest -v` — full suite green

## Inputs

- `src/autoagent/cli.py` — cmd_run() with benchmark loading, MetaAgent creation
- `src/autoagent/meta_agent.py` — generate_initial() from T01
- `src/autoagent/benchmark.py` — describe() from T01
- `src/autoagent/state.py` — STARTER_PIPELINE constant

## Expected Output

- `src/autoagent/cli.py` — cold-start detection and generation wired into cmd_run()
- `tests/test_cli.py` — 4+ new integration tests for cold-start CLI path

## Observability Impact

- **Cold-start stdout messages**: `cmd_run()` prints `"Cold-start: generating initial pipeline from benchmark…"` on trigger, followed by success/retry/fallback outcome. A future agent running `autoagent run` can grep stdout for `Cold-start:` to determine whether cold-start was attempted and its outcome.
- **Failure warning on stderr**: When both attempts fail, a `Warning:` message goes to stderr with the error string — detectable via stderr capture or log monitoring.
- **Pipeline file comparison**: To check whether cold-start ran, compare `pipeline.py` content against `STARTER_PIPELINE` — if they differ and no manual edit occurred, cold-start succeeded.
- **No new persistent state**: Cold-start does not write additional state files; its effect is fully visible in the pipeline.py content and stdout/stderr output.
