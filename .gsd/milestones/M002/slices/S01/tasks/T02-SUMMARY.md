---
id: T02
parent: S01
milestone: M002
provides:
  - OptimizationLoop with summarizer integration, threshold switching, and cost tracking
  - MetaAgent.propose() extended with archive_summary parameter
key_files:
  - src/autoagent/loop.py
  - src/autoagent/meta_agent.py
  - tests/test_loop_summarizer.py
key_decisions:
  - Summary cached on loop instance (_cached_summary, _summary_archive_len) rather than persisted to disk — summary is cheap to regenerate and avoids state file complexity
  - Summarizer instantiated fresh each time summary is needed rather than stored as instance — keeps the LLM reference flexible (supports summarizer_llm override or meta_agent.llm fallback)
  - When summary is active, raw kept/discarded entries are not queried — avoids redundant archive queries
patterns_established:
  - Exception-safe fallback in loop: try/except around summarizer with logger.warning and graceful degradation to raw entries
observability_surfaces:
  - Logger `autoagent.loop` at INFO — logs archive summary regeneration with entry count and cost
  - Logger `autoagent.loop` at WARNING — logs summarizer failures (empty text or exception) with exc_info
  - total_cost_usd in state.json includes summarizer costs
  - Prompt content: "Archive Summary" section present when summary active, absent on fallback
duration: 30m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T02: Wire summarizer into OptimizationLoop with threshold switching and cost tracking

**Integrated ArchiveSummarizer into OptimizationLoop with configurable threshold switching, cached summary regeneration, cost tracking against budget, and graceful fallback to raw entries on failure.**

## What Happened

Extended `OptimizationLoop.__init__()` with three new parameters: `summary_threshold` (default 20), `summary_interval` (default 10), and `summarizer_llm` (optional, falls back to `meta_agent.llm`). The loop now checks archive size before each iteration — when `len(archive) >= summary_threshold`, it generates (or uses cached) an LLM summary and passes it to `meta_agent.propose()` via the new `archive_summary` parameter. Below threshold, behavior is unchanged.

Extended `MetaAgent.propose()` to accept and forward `archive_summary` to `_build_prompt()` (which already supported it from T01).

Summary caching avoids regenerating every iteration: the summary is only regenerated when the archive has grown by `summary_interval` entries since last generation. Summarizer cost is added to `total_cost` so it counts against `budget_usd`.

Fallback: if the summarizer returns empty text or raises an exception, the loop logs a warning and falls back to raw entries — no crash, no silent degradation.

## Verification

- `pytest tests/test_loop_summarizer.py -v` — 8/8 tests pass: below-threshold raw entries, above-threshold summary, cost tracking, caching, regeneration interval, empty-summary fallback, exception fallback, budget interaction
- `pytest tests/test_loop.py -v` — 17/17 existing tests pass (no regressions)
- `pytest tests/test_summarizer.py -v` — 12/12 pass
- `pytest tests/test_meta_agent.py -v` — passes (verified in full suite)
- `pytest tests/ -v` — 208/208 all pass

## Diagnostics

- Check `total_cost_usd` in state.json to verify summarizer costs are included
- Summary content visible in prompt passed to LLM — look for "Archive Summary" section header
- When fallback is active, "Archive Summary" section is absent and "Top Kept Iterations" / "Recent Discarded Iterations" sections appear instead
- Logger `autoagent.loop` at WARNING level surfaces summarizer failures with full traceback

## Deviations

None — implementation followed the plan exactly.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/loop.py` — Added summarizer integration: threshold check, summary generation/caching, cost tracking, fallback logic
- `src/autoagent/meta_agent.py` — Extended `propose()` with `archive_summary` parameter, forwarded to `_build_prompt()`
- `tests/test_loop_summarizer.py` — New test file with 8 integration tests covering all must-haves
- `tests/test_loop.py` — Updated `SequentialMockMetaAgent.propose()` signature to accept `archive_summary`
