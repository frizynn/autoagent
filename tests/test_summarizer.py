"""Tests for ArchiveSummarizer — prompt construction, output handling, cost tracking."""

from __future__ import annotations

import pytest

from autoagent.archive import ArchiveEntry
from autoagent.primitives import MetricsCollector, MockLLM
from autoagent.summarizer import ArchiveSummarizer, SummaryResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WELL_STRUCTURED_SUMMARY = (
    "## Top-K Results\n"
    "- Iteration 5 (score=0.95): Best performer with optimized parsing.\n"
    "- Iteration 3 (score=0.85): Improved tokenization.\n\n"
    "## Failure Clusters\n"
    "- Regex-based approaches consistently failed (iterations 2, 4, 8).\n"
    "- Overly aggressive caching caused stale results (iterations 6, 10).\n\n"
    "## Unexplored Regions\n"
    "- No attempts at async/parallel processing.\n"
    "- Embedding-based retrieval has not been tried.\n\n"
    "## Score Trends\n"
    "- Scores improved from 0.3 to 0.95 over 12 iterations.\n"
    "- Plateau between iterations 7-10 at ~0.8."
)


def _make_entries(
    n: int,
    *,
    keep_ratio: float = 0.3,
    base_score: float = 0.5,
) -> list[ArchiveEntry]:
    """Generate N synthetic ArchiveEntry objects with varied scores and decisions."""
    entries: list[ArchiveEntry] = []
    for i in range(1, n + 1):
        decision = "keep" if (i % int(1 / keep_ratio) == 0) else "discard"
        score = round(base_score + (i * 0.01), 4)
        entries.append(
            ArchiveEntry(
                iteration_id=i,
                timestamp=1000.0 + i,
                pipeline_diff=f"--- a/pipeline.py\n+++ b/pipeline.py\n@@ change {i}",
                evaluation_result={
                    "primary_score": score,
                    "per_example_results": [],
                    "benchmark_id": "test",
                    "duration_ms": 100.0,
                    "num_examples": 5,
                    "num_failures": max(0, 3 - i),
                },
                rationale=f"Rationale for iteration {i}: {'improved' if decision == 'keep' else 'degraded'} performance",
                decision=decision,
                parent_iteration_id=i - 1 if i > 1 else None,
            )
        )
    return entries


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


class TestPromptConstruction:
    """Tests for the summarization prompt built from archive entries."""

    def test_prompt_includes_section_instructions(self):
        """The prompt must instruct the LLM to produce all four required sections."""
        collector = MetricsCollector()
        llm = MockLLM(response=WELL_STRUCTURED_SUMMARY, collector=collector)
        summarizer = ArchiveSummarizer(llm)

        entries = _make_entries(5)
        prompt = summarizer._build_summarization_prompt(entries)

        assert "## Top-K Results" in prompt
        assert "## Failure Clusters" in prompt
        assert "## Unexplored Regions" in prompt
        assert "## Score Trends" in prompt

    def test_prompt_includes_entry_data(self):
        """The prompt should contain iteration IDs, scores, decisions, and rationales."""
        collector = MetricsCollector()
        llm = MockLLM(response="summary", collector=collector)
        summarizer = ArchiveSummarizer(llm)

        entries = _make_entries(3)
        prompt = summarizer._build_summarization_prompt(entries)

        assert "Iteration 1" in prompt
        assert "Iteration 2" in prompt
        assert "Iteration 3" in prompt
        assert "decision=keep" in prompt or "decision=discard" in prompt
        assert "Rationale for iteration" in prompt

    def test_prompt_includes_diff_snippets(self):
        """Diff snippets should appear in the prompt, truncated if too long."""
        collector = MetricsCollector()
        llm = MockLLM(response="summary", collector=collector)
        summarizer = ArchiveSummarizer(llm)

        entries = _make_entries(2)
        prompt = summarizer._build_summarization_prompt(entries)

        assert "change 1" in prompt  # diff snippet content


# ---------------------------------------------------------------------------
# Summarize output
# ---------------------------------------------------------------------------


class TestSummarize:
    """Tests for the summarize() method."""

    def test_returns_llm_output_as_is(self):
        """When the LLM returns a well-structured summary, it's returned verbatim."""
        collector = MetricsCollector()
        llm = MockLLM(response=WELL_STRUCTURED_SUMMARY, collector=collector)
        summarizer = ArchiveSummarizer(llm)

        entries = _make_entries(10)
        result = summarizer.summarize(entries)

        assert isinstance(result, SummaryResult)
        assert result.text == WELL_STRUCTURED_SUMMARY
        assert result.entry_count == 10

    def test_summarize_50_plus_entries(self):
        """Summarize should handle 50+ entries without error."""
        collector = MetricsCollector()
        llm = MockLLM(response=WELL_STRUCTURED_SUMMARY, collector=collector)
        summarizer = ArchiveSummarizer(llm)

        entries = _make_entries(55)
        result = summarizer.summarize(entries)

        assert result.text == WELL_STRUCTURED_SUMMARY
        assert result.entry_count == 55

    def test_empty_entries_returns_empty(self):
        """Summarize with no entries returns empty result without calling LLM."""
        collector = MetricsCollector()
        llm = MockLLM(response="should not be called", collector=collector)
        summarizer = ArchiveSummarizer(llm)

        result = summarizer.summarize([])

        assert result.text == ""
        assert result.cost_usd == 0.0
        assert result.entry_count == 0
        # LLM should not have been called
        assert len(collector.snapshots) == 0

    def test_empty_llm_response_returns_empty_text(self):
        """When LLM returns empty, summarize returns SummaryResult with empty text."""
        collector = MetricsCollector()
        llm = MockLLM(response="", collector=collector)
        summarizer = ArchiveSummarizer(llm)

        entries = _make_entries(5)
        result = summarizer.summarize(entries)

        assert result.text == ""
        assert result.entry_count == 5

    def test_whitespace_llm_response_returns_empty_text(self):
        """Whitespace-only LLM response is treated as empty."""
        collector = MetricsCollector()
        llm = MockLLM(response="   \n\n  ", collector=collector)
        summarizer = ArchiveSummarizer(llm)

        entries = _make_entries(3)
        result = summarizer.summarize(entries)

        assert result.text == ""


# ---------------------------------------------------------------------------
# should_resummarize
# ---------------------------------------------------------------------------


class TestShouldResummarize:
    """Tests for the resummarization trigger logic."""

    def test_below_interval_returns_false(self):
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        summarizer = ArchiveSummarizer(llm, resummarize_interval=10)

        assert summarizer.should_resummarize(current_archive_len=15, last_summary_len=10) is False
        assert summarizer.should_resummarize(current_archive_len=19, last_summary_len=10) is False

    def test_at_interval_returns_true(self):
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        summarizer = ArchiveSummarizer(llm, resummarize_interval=10)

        assert summarizer.should_resummarize(current_archive_len=20, last_summary_len=10) is True

    def test_above_interval_returns_true(self):
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        summarizer = ArchiveSummarizer(llm, resummarize_interval=10)

        assert summarizer.should_resummarize(current_archive_len=25, last_summary_len=10) is True

    def test_custom_interval(self):
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        summarizer = ArchiveSummarizer(llm, resummarize_interval=5)

        assert summarizer.should_resummarize(current_archive_len=10, last_summary_len=5) is True
        assert summarizer.should_resummarize(current_archive_len=9, last_summary_len=5) is False

    def test_zero_last_summary_len(self):
        """First summarization: last_summary_len=0, archive has grown past interval."""
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        summarizer = ArchiveSummarizer(llm, resummarize_interval=10)

        assert summarizer.should_resummarize(current_archive_len=10, last_summary_len=0) is True
        assert summarizer.should_resummarize(current_archive_len=5, last_summary_len=0) is False


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------


class TestCostTracking:
    """Tests for incremental cost tracking via MetricsCollector delta."""

    def test_cost_computed_from_collector_delta(self):
        collector = MetricsCollector()
        llm = MockLLM(
            response=WELL_STRUCTURED_SUMMARY,
            tokens_in=500,
            tokens_out=1000,
            model="gpt-4o-mini",
            collector=collector,
        )
        summarizer = ArchiveSummarizer(llm)

        entries = _make_entries(10)
        result = summarizer.summarize(entries)

        # MockLLM with gpt-4o-mini pricing should produce a positive cost
        assert result.cost_usd > 0
        assert result.cost_usd == collector.aggregate().cost_usd

    def test_cost_is_incremental(self):
        """When collector already has snapshots, cost reflects only the new call."""
        collector = MetricsCollector()

        # Pre-existing call recorded in the collector
        pre_llm = MockLLM(
            response="prior call",
            tokens_in=100,
            tokens_out=200,
            model="gpt-4o-mini",
            collector=collector,
        )
        pre_llm.complete("something")
        cost_before = collector.aggregate().cost_usd
        assert cost_before > 0

        # Now do a summarize call
        llm = MockLLM(
            response=WELL_STRUCTURED_SUMMARY,
            tokens_in=500,
            tokens_out=1000,
            model="gpt-4o-mini",
            collector=collector,
        )
        summarizer = ArchiveSummarizer(llm)

        entries = _make_entries(5)
        result = summarizer.summarize(entries)

        # Cost should be incremental (only the summarize call), not cumulative
        assert result.cost_usd > 0
        assert result.cost_usd < collector.aggregate().cost_usd
        # Total = pre + summarize
        expected_total = cost_before + result.cost_usd
        assert abs(collector.aggregate().cost_usd - expected_total) < 1e-10


# ---------------------------------------------------------------------------
# Discard sampling
# ---------------------------------------------------------------------------


class TestDiscardSampling:
    """Tests for truncation of discard entries in the prompt."""

    def test_many_discards_are_sampled(self):
        """With 50+ entries, prompt should still be built without error."""
        collector = MetricsCollector()
        llm = MockLLM(response="summary", collector=collector)
        summarizer = ArchiveSummarizer(llm)

        # Generate 60 entries, mostly discards
        entries = _make_entries(60, keep_ratio=0.1)
        prompt = summarizer._build_summarization_prompt(entries)

        # Should mention that not all entries are shown
        assert "of 60 total" in prompt


# ---------------------------------------------------------------------------
# Import contract
# ---------------------------------------------------------------------------


class TestImportContract:
    def test_importable(self):
        from autoagent.summarizer import ArchiveSummarizer, SummaryResult

        assert ArchiveSummarizer is not None
        assert SummaryResult is not None
