"""ArchiveSummarizer — compresses archive history into a structured ~3K token summary.

When the archive grows past a configurable threshold, raw archive entries
in the meta-agent prompt are replaced with a structured LLM-generated summary.
The summary preserves the most important signals: top results, failure clusters,
unexplored regions, and score trends.

Cost is tracked via MetricsCollector delta — each summarize() call exposes
its incremental cost in the returned SummaryResult.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from autoagent.archive import ArchiveEntry
from autoagent.primitives import LLMProtocol, MetricsCollector

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SummaryResult:
    """Outcome of a single summarize() call.

    Attributes:
        text: The structured summary text (empty string on failure).
        cost_usd: Incremental LLM cost for this summarization call.
        entry_count: Number of archive entries that were summarized.
    """

    text: str = ""
    cost_usd: float = 0.0
    entry_count: int = 0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_DISCARD_SAMPLE = 20  # Cap sampled discards to keep prompt reasonable
_MAX_DIFF_CHARS = 300  # Truncate diffs per entry in the summarization prompt


# ---------------------------------------------------------------------------
# ArchiveSummarizer
# ---------------------------------------------------------------------------


class ArchiveSummarizer:
    """Compresses archive entries into a structured summary via LLM.

    Parameters
    ----------
    llm:
        An object satisfying ``LLMProtocol`` (has ``.complete()`` and
        optionally ``.collector``).
    max_summary_chars:
        Target maximum characters for the summary output (~3K tokens at 4
        chars/token = 12000 chars).
    resummarize_interval:
        Number of new archive entries that must accumulate before
        re-summarization is triggered.
    """

    def __init__(
        self,
        llm: LLMProtocol,
        max_summary_chars: int = 12000,
        resummarize_interval: int = 10,
    ) -> None:
        self.llm = llm
        self.max_summary_chars = max_summary_chars
        self.resummarize_interval = resummarize_interval

    # -- public API --------------------------------------------------------

    def summarize(self, entries: list[ArchiveEntry]) -> SummaryResult:
        """Produce a structured summary from archive entries.

        Builds a prompt from the entries, calls the LLM, and returns the
        summary text as-is. If the LLM returns an empty response, returns
        a SummaryResult with empty text — callers can check ``if not result.text``.

        Cost is computed as a MetricsCollector delta before/after the call.
        """
        if not entries:
            return SummaryResult(text="", cost_usd=0.0, entry_count=0)

        # Snapshot collector state for incremental cost
        collector: MetricsCollector | None = getattr(self.llm, "collector", None)
        cost_before = collector.aggregate().cost_usd if collector else 0.0

        prompt = self._build_summarization_prompt(entries)
        response = self.llm.complete(prompt)

        # Compute incremental cost
        cost_after = collector.aggregate().cost_usd if collector else 0.0
        call_cost = cost_after - cost_before

        text = response.strip() if response else ""

        if text:
            # Truncate if over budget
            if len(text) > self.max_summary_chars:
                text = text[: self.max_summary_chars]
            logger.info(
                "Archive summary generated: %d chars, $%.6f, from %d entries",
                len(text),
                call_cost,
                len(entries),
            )
        else:
            logger.warning(
                "Summarizer LLM returned empty response for %d entries", len(entries)
            )

        return SummaryResult(
            text=text,
            cost_usd=call_cost,
            entry_count=len(entries),
        )

    def should_resummarize(
        self, current_archive_len: int, last_summary_len: int
    ) -> bool:
        """Return True when the archive has grown enough to warrant re-summarization.

        Parameters
        ----------
        current_archive_len:
            Current total number of entries in the archive.
        last_summary_len:
            Number of entries that were included in the last summary.
        """
        return (current_archive_len - last_summary_len) >= self.resummarize_interval

    # -- prompt construction -----------------------------------------------

    def _build_summarization_prompt(self, entries: list[ArchiveEntry]) -> str:
        """Build the prompt that instructs the LLM to produce a structured summary."""
        # Separate kept and discarded
        kept = [e for e in entries if e.decision == "keep"]
        discarded = [e for e in entries if e.decision == "discard"]

        # Always include all kept entries; sample discards if too many
        sampled_discards = discarded
        if len(discarded) > _MAX_DISCARD_SAMPLE:
            # Take most recent discards (highest iteration_id)
            sampled_discards = sorted(
                discarded, key=lambda e: e.iteration_id, reverse=True
            )[:_MAX_DISCARD_SAMPLE]

        all_entries = sorted(kept + sampled_discards, key=lambda e: e.iteration_id)

        sections: list[str] = []

        # Instructions
        sections.append(
            "You are summarizing the optimization history of a data pipeline.\n"
            "Given the archive entries below, produce a structured summary with "
            "EXACTLY these four sections:\n\n"
            "## Top-K Results\n"
            "List the top-scoring kept iterations with their scores and key changes.\n\n"
            "## Failure Clusters\n"
            "Group discarded iterations by common failure patterns. "
            "Identify what approaches consistently fail.\n\n"
            "## Unexplored Regions\n"
            "Based on the history, identify optimization directions that have NOT "
            "been tried yet.\n\n"
            "## Score Trends\n"
            "Describe how scores have changed over iterations. "
            "Note any plateaus, improvements, or regressions.\n\n"
            f"Keep the total summary under {self.max_summary_chars} characters."
        )

        # Entry data
        entry_lines: list[str] = []
        for entry in all_entries:
            score = entry.evaluation_result.get("primary_score", "?")
            diff_snippet = entry.pipeline_diff[:_MAX_DIFF_CHARS]
            if len(entry.pipeline_diff) > _MAX_DIFF_CHARS:
                diff_snippet += "..."
            entry_lines.append(
                f"- Iteration {entry.iteration_id} | decision={entry.decision} | "
                f"score={score} | rationale: {entry.rationale}"
                + (f"\n  diff: {diff_snippet}" if diff_snippet else "")
            )

        sections.append(
            f"## Archive Entries ({len(all_entries)} of {len(entries)} total)\n"
            + "\n".join(entry_lines)
        )

        return "\n\n".join(sections)
