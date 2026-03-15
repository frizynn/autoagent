---
estimated_steps: 5
estimated_files: 4
---

# T02: Wire summarizer into OptimizationLoop with threshold switching and cost tracking

**Slice:** S01 — Archive Compression & Summarization
**Milestone:** M002

## Description

Integrate `ArchiveSummarizer` into `OptimizationLoop` so that past a configurable iteration threshold, the loop generates and caches an archive summary, passes it to the meta-agent prompt instead of raw entries, and counts the compression cost against the budget. Below threshold, behavior is unchanged. If the summarizer fails, fall back to raw entries.

## Steps

1. Add summarizer parameters to `OptimizationLoop.__init__()`:
   - `summary_threshold: int = 20` — archive size at which summaries replace raw entries
   - `summary_interval: int = 10` — regenerate summary every N iterations past threshold
   - `summarizer_llm: LLMProtocol | None = None` — LLM for summarization (if None, use meta_agent's LLM)
   - Store cached summary string and the archive length at last summarization

2. Modify the iteration loop in `OptimizationLoop.run()`:
   - Before gathering archive context (lines ~192-206), check `len(archive) >= summary_threshold`
   - If above threshold and summary needs (re)generation: instantiate `ArchiveSummarizer`, call `summarize()` with all entries, cache result, track cost
   - Pass `archive_summary` to `meta_agent.propose()` — which requires adding it to `propose()` signature and forwarding to `_build_prompt()`
   - If below threshold or summarizer fails: use existing raw entry logic (no behavior change)

3. Extend `MetaAgent.propose()` to accept and forward `archive_summary`:
   - Add `archive_summary: str = ""` parameter
   - Forward to `_build_prompt()` call

4. Wire cost tracking:
   - After `summarize()` call, read cost from summarizer's collector delta
   - Add to `total_cost` so it counts against `budget_usd`

5. Write `tests/test_loop_summarizer.py`:
   - Test loop with archive below threshold — verify raw entries used (mock meta_agent.propose checks prompt content)
   - Test loop with archive pre-populated above threshold — verify summary generated and passed to propose
   - Test cost tracking: summarizer cost added to total_cost and checked against budget
   - Test summary caching: summary not regenerated every iteration, only every N iterations
   - Test fallback: if summarizer LLM returns empty/fails, loop continues with raw entries
   - Run existing `test_loop.py` tests to verify no regressions

## Must-Haves

- [ ] Loop uses raw entries when archive size < threshold
- [ ] Loop generates and uses summary when archive size >= threshold
- [ ] Summary cached and regenerated at configurable interval
- [ ] Summarizer cost counted in total_cost and checked against budget_usd
- [ ] Graceful fallback to raw entries on summarizer failure
- [ ] `MetaAgent.propose()` accepts and forwards `archive_summary`
- [ ] All existing `test_loop.py` tests pass

## Verification

- `pytest tests/test_loop_summarizer.py -v` — all integration tests pass
- `pytest tests/test_loop.py -v` — no regressions in existing loop tests
- `pytest tests/ -v` — full test suite green

## Observability Impact

- Signals added/changed: summary regeneration logged with archive length and cost
- How a future agent inspects this: check `total_cost_usd` in state.json includes summarizer costs; summary content visible in prompt passed to LLM
- Failure state exposed: summarizer failure falls back to raw entries — visible in prompt content (no "Archive Summary" section when fallback active)

## Inputs

- `src/autoagent/summarizer.py` — `ArchiveSummarizer` from T01
- `src/autoagent/meta_agent.py` — `MetaAgent.propose()` and `_build_prompt()` (extended in T01)
- `src/autoagent/loop.py` — current `OptimizationLoop` implementation
- `tests/test_loop.py` — existing loop tests for regression checking

## Expected Output

- `src/autoagent/loop.py` — `OptimizationLoop` with summarizer integration, threshold switching, cost tracking
- `src/autoagent/meta_agent.py` — `propose()` extended with `archive_summary` parameter
- `tests/test_loop_summarizer.py` — new test file with 5+ integration tests
