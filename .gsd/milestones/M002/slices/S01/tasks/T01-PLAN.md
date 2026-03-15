---
estimated_steps: 6
estimated_files: 4
---

# T01: Build ArchiveSummarizer with structured summary generation and tests

**Slice:** S01 — Archive Compression & Summarization
**Milestone:** M002

## Description

Build the `ArchiveSummarizer` class that takes a list of archive entries and produces a structured ~3K token summary via LLM call. The summary must have explicit sections (Top-K Results, Failure Clusters, Unexplored Regions, Score Trends) that preserve the most important signals for the meta-agent's decision-making. Also extend `MetaAgent._build_prompt()` to accept an `archive_summary` parameter that replaces the raw kept/discarded entry sections.

## Steps

1. Create `src/autoagent/summarizer.py` with `ArchiveSummarizer` class:
   - Constructor takes `llm: LLMProtocol`, `max_summary_chars: int = 12000` (~3K tokens), `resummarize_interval: int = 10`
   - `summarize(entries: list[ArchiveEntry]) -> str` — builds a prompt from all entries, calls LLM, returns structured summary text
   - `should_resummarize(current_archive_len: int, last_summary_len: int) -> bool` — returns True when archive has grown by `resummarize_interval` entries since last summary
   - Build the summarization prompt: feed entry data (iteration_id, score, decision, rationale, diff snippet) and instruct LLM to produce sections: `## Top-K Results`, `## Failure Clusters`, `## Unexplored Regions`, `## Score Trends`
   - Track cost via the LLM's `MetricsCollector` — expose incremental cost from the summarize call
   - Truncate input if entries are too numerous (include all kept entries + sample of discards) to keep prompt reasonable

2. Add `archive_summary: str = ""` parameter to `MetaAgent._build_prompt()`:
   - When `archive_summary` is non-empty, use it instead of the kept/discarded entry sections
   - Add a `## Archive Summary` section header
   - When empty, preserve existing behavior (raw kept + discarded sections)

3. Write `tests/test_summarizer.py`:
   - Helper to generate N synthetic `ArchiveEntry` objects with varied scores, decisions, rationales
   - Test prompt construction includes all required section instructions
   - Test with MockLLM returning a well-structured summary — verify output is returned as-is
   - Test with 50+ synthetic entries — verify prompt is built without error and summary is produced
   - Test `should_resummarize()` logic: returns False when growth < interval, True when ≥ interval
   - Test cost tracking: verify `cost_usd` is computed from collector delta
   - Test with MockLLM returning empty response — verify graceful handling (returns fallback/empty)

4. Add tests to `tests/test_meta_agent.py` for the `archive_summary` parameter:
   - Test `_build_prompt()` with `archive_summary` set — verify "Archive Summary" section appears, kept/discarded sections do not
   - Test `_build_prompt()` without `archive_summary` — verify existing behavior unchanged

## Must-Haves

- [ ] `ArchiveSummarizer.summarize()` produces output from 50+ entries
- [ ] Summary prompt requests sections: Top-K Results, Failure Clusters, Unexplored Regions, Score Trends
- [ ] `should_resummarize()` correctly detects when regeneration is needed
- [ ] Cost tracking via MetricsCollector delta
- [ ] `_build_prompt()` accepts `archive_summary` and replaces raw entry sections
- [ ] All existing `test_meta_agent.py` tests still pass

## Verification

- `pytest tests/test_summarizer.py -v` — all summarizer unit tests pass
- `pytest tests/test_meta_agent.py -v` — all meta-agent tests pass (existing + new)

## Inputs

- `src/autoagent/archive.py` — `ArchiveEntry` dataclass and `Archive.query()` API
- `src/autoagent/meta_agent.py` — `MetaAgent._build_prompt()` to extend
- `src/autoagent/primitives.py` — `LLMProtocol`, `MetricsCollector`, `MockLLM` for testing

## Expected Output

- `src/autoagent/summarizer.py` — new module with `ArchiveSummarizer` class
- `tests/test_summarizer.py` — new test file with 7+ test cases
- `src/autoagent/meta_agent.py` — `_build_prompt()` extended with `archive_summary` parameter
- `tests/test_meta_agent.py` — 2+ new tests for archive_summary behavior

## Observability Impact

- **New signal:** `ArchiveSummarizer.summarize()` returns a `SummaryResult` with `text`, `cost_usd`, and `entry_count` — future agents can inspect the summary text and cost of each compression call.
- **Cost tracking:** Summarizer cost is computed as a MetricsCollector delta before/after the LLM call. The `cost_usd` field on the result is the incremental cost of that single summarization.
- **Regeneration trigger:** `should_resummarize()` is a pure function — testable without LLM calls. A future agent can inspect archive length vs last summary length to understand when re-summarization fires.
- **Failure visibility:** If the LLM returns an empty response, `summarize()` returns an empty string (not None) — callers can check `if not result.text` to detect failures. No silent swallowing.
- **Prompt inspection:** The summarization prompt is built as a plain string — inspectable for debugging without calling the LLM, same pattern as `MetaAgent._build_prompt()`.
