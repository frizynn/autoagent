# S01: Archive Compression & Summarization

**Goal:** When the archive exceeds a configurable iteration threshold, the optimization loop uses an LLM-generated structured summary (~3K tokens) instead of raw archive entries in the meta-agent prompt — preserving top-K results, failure clusters, unexplored regions, and score trends.
**Demo:** `pytest tests/test_summarizer.py tests/test_loop_summarizer.py` passes — unit tests prove summary structure/token budget from 50+ synthetic entries, integration tests prove the loop switches from raw entries to summaries past threshold and tracks compression cost in budget.

## Must-Haves

- `ArchiveSummarizer` class with `summarize(entries) -> str` that calls an LLM to produce structured summaries
- Summary prompt enforces sections: Top-K Results, Failure Clusters, Unexplored Regions, Score Trends
- Summary output fits ~3K token budget (validated by character-count heuristic, ~12K chars)
- Regeneration logic: summarize every N iterations or when archive grows past last summary coverage
- `OptimizationLoop` uses summary string instead of raw `kept_entries`/`discarded_entries` past configurable threshold
- `MetaAgent._build_prompt()` accepts an optional `archive_summary` parameter that replaces the kept/discarded sections
- Compression LLM cost tracked through existing cost accumulation path and counted against budget
- Score trend data and structural diversity signals in summary (consumed by S03 later)

## Proof Level

- This slice proves: contract + integration
- Real runtime required: no (LLM calls mocked in tests)
- Human/UAT required: no

## Verification

- `pytest tests/test_summarizer.py -v` — unit tests for ArchiveSummarizer: prompt construction, output parsing, section structure validation, token budget enforcement, regeneration trigger logic, cost tracking
- `pytest tests/test_loop_summarizer.py -v` — integration tests: loop uses summary past threshold, raw entries used below threshold, compression cost counted in budget, summary regeneration on archive growth
- `pytest tests/test_meta_agent.py -v` — existing tests still pass + new tests for `archive_summary` parameter in `_build_prompt()`

## Observability / Diagnostics

- Runtime signals: summarizer logs summary token count and cost per regeneration
- Inspection surfaces: summary text is inspectable as a string in the prompt (same as current archive context)
- Failure visibility: summarizer returns a fallback (raw entries) if LLM call fails — no silent degradation

## Integration Closure

- Upstream surfaces consumed: `Archive.query()`, `ArchiveEntry`, `LLMProtocol`, `MetricsCollector`
- New wiring introduced: `ArchiveSummarizer` instantiated in loop setup; `_build_prompt()` gains `archive_summary` kwarg; loop calls summarizer when `len(archive) > threshold`
- What remains before the milestone is truly usable end-to-end: S02 (component vocabulary), S03 (strategy signals), S04 (cold-start)

## Tasks

- [x] **T01: Build ArchiveSummarizer with structured summary generation and tests** `est:2h`
  - Why: Core novel piece — the summarizer that compresses 50+ archive entries into a structured ~3K token summary via LLM. Must be independently testable before wiring into the loop.
  - Files: `src/autoagent/summarizer.py`, `tests/test_summarizer.py`
  - Do: Implement `ArchiveSummarizer` class with `summarize(entries: list[ArchiveEntry]) -> str`. Build prompt that instructs LLM to produce sections (Top-K Results, Failure Clusters, Unexplored Regions, Score Trends). Track cost via `MetricsCollector`. Include `should_resummarize(archive_len, last_summary_coverage)` method for regeneration triggers. Add `archive_summary` kwarg to `MetaAgent._build_prompt()` that replaces kept/discarded sections when provided. Test with 50+ synthetic archive entries, validate section structure via string checks, enforce ~12K char budget (~3K tokens).
  - Verify: `pytest tests/test_summarizer.py tests/test_meta_agent.py -v`
  - Done when: Summarizer produces structured summaries from 50+ entries within token budget, `_build_prompt()` accepts and uses `archive_summary`, all existing meta-agent tests pass

- [x] **T02: Wire summarizer into OptimizationLoop with threshold switching and cost tracking** `est:1.5h`
  - Why: Closes the slice — the loop must actually use summaries past a threshold, not just have the capability. Cost must count against budget.
  - Files: `src/autoagent/loop.py`, `tests/test_loop_summarizer.py`
  - Do: Add `summary_threshold` param to `OptimizationLoop.__init__()` (default 20). When `len(archive) >= threshold`, instantiate/call `ArchiveSummarizer` to generate summary, pass it to `_build_prompt()` via `archive_summary`. Cache summary and regenerate every N iterations (configurable, default 10) or when archive grows past last coverage. Accumulate summarizer LLM cost into `total_cost`. Fallback: if summarizer fails, use raw entries (no crash). Test: loop below threshold uses raw entries, loop above threshold uses summary, cost tracked, regeneration triggers work.
  - Verify: `pytest tests/test_loop_summarizer.py tests/test_loop.py -v`
  - Done when: Loop switches to summaries past threshold, compression cost counted in budget, all existing loop tests pass, fallback to raw entries on summarizer failure

## Files Likely Touched

- `src/autoagent/summarizer.py` (new)
- `src/autoagent/meta_agent.py`
- `src/autoagent/loop.py`
- `tests/test_summarizer.py` (new)
- `tests/test_loop_summarizer.py` (new)
- `tests/test_meta_agent.py`
