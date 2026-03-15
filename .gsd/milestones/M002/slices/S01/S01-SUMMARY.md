---
id: S01
parent: M002
milestone: M002
provides:
  - ArchiveSummarizer class with structured LLM-generated archive summaries (~3K tokens)
  - SummaryResult dataclass exposing cost_usd and entry_count for observability
  - OptimizationLoop threshold switching from raw entries to summaries
  - Cached summary regeneration every N iterations with configurable interval
  - Graceful fallback to raw entries on summarizer failure
  - Compression cost tracked against budget
requires: []
affects:
  - S03
key_files:
  - src/autoagent/summarizer.py
  - src/autoagent/meta_agent.py
  - src/autoagent/loop.py
  - tests/test_summarizer.py
  - tests/test_loop_summarizer.py
key_decisions:
  - SummaryResult dataclass returned from summarize() instead of raw string — exposes cost_usd and entry_count
  - Discard sampling caps at 20 most-recent to keep summarization prompt bounded
  - Summary cached on loop instance (_cached_summary, _summary_archive_len) rather than persisted to disk — cheap to regenerate, avoids state file complexity
  - When summary is active, raw kept/discarded entries are not queried — avoids redundant archive queries
patterns_established:
  - MetricsCollector delta pattern for tracking incremental LLM cost (snapshot before/after)
  - Structured result dataclass (SummaryResult) for operations with side costs — same pattern as ProposalResult
  - Exception-safe fallback in loop: try/except with logger.warning and graceful degradation
observability_surfaces:
  - SummaryResult.cost_usd — incremental cost of each summarization call
  - SummaryResult.entry_count — number of entries compressed
  - Logger autoagent.summarizer at INFO — summary char count, cost, entry count
  - Logger autoagent.summarizer at WARNING — empty LLM response
  - Logger autoagent.loop at INFO — archive summary regeneration with entry count and cost
  - Logger autoagent.loop at WARNING — summarizer failures with exc_info
  - total_cost_usd in state.json includes summarizer costs
drill_down_paths:
  - .gsd/milestones/M002/slices/S01/tasks/T01-SUMMARY.md
  - .gsd/milestones/M002/slices/S01/tasks/T02-SUMMARY.md
duration: 2 tasks across 2 context windows
verification_result: passed
completed_at: 2026-03-14
---

# S01: Archive Compression & Summarization

**ArchiveSummarizer compresses 50+ archive entries into structured ~3K token LLM summaries with top-K results, failure clusters, unexplored regions, and score trends — automatically used by the optimization loop past a configurable threshold, with cost tracking and graceful fallback.**

## What Happened

T01 built the `ArchiveSummarizer` class in `src/autoagent/summarizer.py`. It takes a list of `ArchiveEntry` objects, constructs a prompt instructing the LLM to produce four sections (Top-K Results, Failure Clusters, Unexplored Regions, Score Trends), and returns a `SummaryResult` with the summary text, cost, and entry count. All kept entries are included; discards are sampled (most recent 20) to bound prompt size. Diff snippets are truncated to 300 chars. The `should_resummarize()` method provides regeneration trigger logic. `MetaAgent._build_prompt()` was extended with an `archive_summary` parameter that replaces raw kept/discarded sections when non-empty.

T02 wired the summarizer into `OptimizationLoop`. Three new init parameters: `summary_threshold` (default 20), `summary_interval` (default 10), `summarizer_llm` (optional, falls back to meta_agent.llm). When archive size reaches threshold, the loop generates a summary and passes it to `meta_agent.propose()` via the new `archive_summary` parameter. Summaries are cached and regenerated only when the archive grows by `summary_interval` entries. Summarizer cost is accumulated into `total_cost` and counted against budget. On failure (empty text or exception), the loop falls back to raw entries with a warning log.

## Verification

- `pytest tests/test_summarizer.py -v` — 17/17 passed (prompt construction, output handling, 50+ entries, empty responses, should_resummarize logic, cost tracking, discard sampling)
- `pytest tests/test_loop_summarizer.py -v` — 8/8 passed (threshold switching, cost tracking, caching, regeneration interval, fallback on empty/exception, budget interaction)
- `pytest tests/test_meta_agent.py -v` — 27/27 passed (25 existing + 2 new archive_summary tests)
- `pytest tests/test_loop.py -v` — 17/17 passed (no regressions)
- `pytest tests/ -v` — 208/208 all passed

## Requirements Advanced

- R016 (Archive Compression for Scale) — ArchiveSummarizer produces structured summaries from 50+ entries, loop switches to summaries past threshold, cost tracked

## Requirements Validated

- R016 — Summarizer produces structured summaries with top-K, failure clusters, unexplored regions, score trends from 50+ synthetic entries. Summaries fit ~3K token budget (~12K chars). Loop switches from raw entries to summaries past configurable threshold. Compression cost tracked in budget. Graceful fallback on failure. 25 tests prove contract + integration.

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

None.

## Known Limitations

- Summary quality depends entirely on LLM output — no mechanical validation of section content beyond character budget
- Token budget enforced via character-count heuristic (~4 chars/token), not actual tokenizer
- No drill-down capability yet (mentioned in R016) — summaries are flat text, not hierarchical

## Follow-ups

- S03 will consume score trend data and structural diversity signals from summaries for stagnation detection
- Drill-down capability (expanding summary sections to raw entries) deferred — not needed for M002 success criteria

## Files Created/Modified

- `src/autoagent/summarizer.py` — new module with ArchiveSummarizer class and SummaryResult dataclass
- `src/autoagent/meta_agent.py` — added archive_summary parameter to _build_prompt() and propose()
- `src/autoagent/loop.py` — summarizer integration: threshold check, summary generation/caching, cost tracking, fallback logic
- `tests/test_summarizer.py` — 17 tests for summarizer contract
- `tests/test_loop_summarizer.py` — 8 integration tests for loop summarizer wiring
- `tests/test_meta_agent.py` — 2 new tests for archive_summary behavior
- `tests/test_loop.py` — updated mock meta-agent signature for archive_summary parameter

## Forward Intelligence

### What the next slice should know
- `MetaAgent._build_prompt()` now accepts `archive_summary: str` — S02/S03 can extend the prompt knowing this parameter exists
- `MetaAgent.propose()` accepts `archive_summary` and forwards it — any new prompt sections (component vocabulary, strategy signals) are additive, not conflicting
- The summary text contains "Score Trends" and structural diversity info that S03 needs for stagnation detection — it's unstructured text in the summary, not a parsed data structure

### What's fragile
- Character-count heuristic for token budget (~4 chars/token) — if summaries run long, the meta-agent prompt could exceed context window. Monitor in S03 when adding more prompt sections.
- Discard sampling (20 most recent) means old failure patterns may be lost in very long runs — the summary LLM is expected to compensate

### Authoritative diagnostics
- `tests/test_summarizer.py` and `tests/test_loop_summarizer.py` — these are the contract tests. If something breaks in summarizer behavior, start here.
- Logger `autoagent.loop` at WARNING — surfaces summarizer failures with full traceback

### What assumptions changed
- No assumptions changed — implementation matched the plan exactly
