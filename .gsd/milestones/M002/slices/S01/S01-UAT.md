# S01: Archive Compression & Summarization — UAT

**Milestone:** M002
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: All behavior is tested via pytest with mocked LLM calls. No live runtime or human judgment needed — the slice proves contract (summary structure, token budget, cost tracking) and integration (loop threshold switching, caching, fallback) through deterministic tests.

## Preconditions

- Python 3.11+ with `.venv` activated
- Project dependencies installed (`pip install -e .`)
- Working directory is the autoagent repo root

## Smoke Test

```bash
.venv/bin/python -m pytest tests/test_summarizer.py tests/test_loop_summarizer.py -v
```
All tests pass — confirms summarizer produces structured output and loop switches to summaries past threshold.

## Test Cases

### 1. Summarizer produces structured summary from 50+ entries

1. Run `pytest tests/test_summarizer.py::TestSummarize::test_summarize_50_plus_entries -v`
2. **Expected:** Test passes — summarizer processes 50+ synthetic archive entries and returns a SummaryResult with non-empty text

### 2. Summary prompt includes required section instructions

1. Run `pytest tests/test_summarizer.py::TestPromptConstruction -v`
2. **Expected:** All 3 tests pass — prompt includes "Top-K Results", "Failure Clusters", "Unexplored Regions", "Score Trends" section headers, entry data, and diff snippets

### 3. Summarizer tracks cost via MetricsCollector delta

1. Run `pytest tests/test_summarizer.py::TestCostTracking -v`
2. **Expected:** Both tests pass — SummaryResult.cost_usd reflects incremental cost from collector delta, not cumulative

### 4. Discard sampling bounds prompt size

1. Run `pytest tests/test_summarizer.py::TestDiscardSampling::test_many_discards_are_sampled -v`
2. **Expected:** Test passes — with 30+ discarded entries, only 20 most-recent appear in the summarization prompt

### 5. Resummarization triggers correctly

1. Run `pytest tests/test_summarizer.py::TestShouldResummarize -v`
2. **Expected:** All 5 tests pass — `should_resummarize()` returns True when archive has grown by interval since last summary, False otherwise

### 6. Loop uses raw entries below threshold

1. Run `pytest tests/test_loop_summarizer.py::TestLoopSummarizerIntegration::test_below_threshold_uses_raw_entries -v`
2. **Expected:** Test passes — with archive size below `summary_threshold`, `propose()` is called without `archive_summary`

### 7. Loop switches to summary above threshold

1. Run `pytest tests/test_loop_summarizer.py::TestLoopSummarizerIntegration::test_above_threshold_uses_summary -v`
2. **Expected:** Test passes — with archive size at/above threshold, `propose()` receives non-empty `archive_summary`

### 8. Summarizer cost counted against budget

1. Run `pytest tests/test_loop_summarizer.py::TestLoopSummarizerIntegration::test_summarizer_cost_counted_against_budget -v`
2. **Expected:** Test passes — summarizer LLM cost added to `total_cost`, which is checked against `budget_usd` ceiling

### 9. Summary is cached and regenerated at interval

1. Run `pytest tests/test_loop_summarizer.py::TestLoopSummarizerIntegration::test_summary_cached_not_regenerated_every_iteration -v`
2. Run `pytest tests/test_loop_summarizer.py::TestLoopSummarizerIntegration::test_summary_regenerated_at_interval -v`
3. **Expected:** Both pass — summary is reused across iterations until archive grows by `summary_interval` entries, then regenerated

### 10. MetaAgent._build_prompt() uses archive_summary when provided

1. Run `pytest tests/test_meta_agent.py::TestArchiveSummaryPrompt -v`
2. **Expected:** Both tests pass — when `archive_summary` is non-empty, prompt contains "Archive Summary" section and omits raw kept/discarded entries; when empty, raw entries are preserved

### 11. No regressions in existing tests

1. Run `pytest tests/ -v`
2. **Expected:** All 208 tests pass — no regressions from M001 or within M002 S01

## Edge Cases

### Empty LLM response from summarizer

1. Run `pytest tests/test_summarizer.py::TestSummarize::test_empty_llm_response_returns_empty_text -v`
2. Run `pytest tests/test_summarizer.py::TestSummarize::test_whitespace_llm_response_returns_empty_text -v`
3. **Expected:** Both pass — empty/whitespace LLM responses produce SummaryResult with empty text, no crash

### Summarizer exception during loop iteration

1. Run `pytest tests/test_loop_summarizer.py::TestLoopSummarizerIntegration::test_fallback_on_summarizer_exception -v`
2. **Expected:** Test passes — loop catches exception, logs warning, falls back to raw entries, continues iterating

### Summarizer returns empty summary during loop

1. Run `pytest tests/test_loop_summarizer.py::TestLoopSummarizerIntegration::test_fallback_on_empty_summary -v`
2. **Expected:** Test passes — loop detects empty summary text, falls back to raw entries for that iteration

### Empty archive entries list

1. Run `pytest tests/test_summarizer.py::TestSummarize::test_empty_entries_returns_empty -v`
2. **Expected:** Test passes — empty entry list returns SummaryResult with empty text, no LLM call

## Failure Signals

- Any test in `tests/test_summarizer.py` or `tests/test_loop_summarizer.py` failing
- Regressions in `tests/test_meta_agent.py` or `tests/test_loop.py`
- Logger warnings about summarizer failures appearing in non-fallback test scenarios
- `archive_summary` parameter not forwarded through `propose()` to `_build_prompt()`

## Requirements Proved By This UAT

- R016 (Archive Compression for Scale) — Summarizer compresses 50+ entries into structured summary with required sections, fits token budget, loop switches automatically past threshold, cost tracked in budget, graceful fallback on failure

## Not Proven By This UAT

- Drill-down capability (expanding summary to raw entries) — deferred, not in M002 scope
- Summary quality with real LLM — all tests use mocked LLM; real output quality depends on prompt engineering proven through live runs
- Summary behavior at 200+ iterations — tested with 50+ synthetic entries; extreme scale is inferred, not directly proven
- Integration with S03 stagnation detection — S03 will consume summary text; this slice only produces it

## Notes for Tester

- All LLM calls are mocked — no API keys or network access needed
- The token budget is enforced via character-count heuristic (~4 chars/token ≈ ~12K chars for ~3K tokens). This is approximate.
- The `summary_threshold` default is 20 iterations. Tests set it lower (3-5) for practical test scenarios.
- Fallback behavior means the loop never crashes due to summarizer issues — it just uses raw entries as before.
