"""Stagnation detection and mutation classification for strategy guidance.

Pure functions — no LLM calls, no I/O.  Consume ``ArchiveEntry`` objects
and return human-readable strategy signals that the meta-agent interprets
as hints, not commands (per D005/D032).
"""

from __future__ import annotations

import re
import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autoagent.archive import ArchiveEntry

# ---------------------------------------------------------------------------
# Mutation classification
# ---------------------------------------------------------------------------

# Patterns that indicate *structural* changes in a pipeline diff.
_STRUCTURAL_PATTERNS: list[re.Pattern[str]] = [
    # New or removed function/class definitions
    re.compile(r"^[+-]\s*def\s+\w+\s*\(", re.MULTILINE),
    re.compile(r"^[+-]\s*class\s+\w+", re.MULTILINE),
    # New or removed primitive calls (primitives.xxx)
    re.compile(r"^[+-].*\bprimitives\.\w+", re.MULTILINE),
    # Control flow changes — added/removed if/else/for/while/try/return
    re.compile(
        r"^[+-]\s+(if|elif|else|for|while|try|except|finally)\b",
        re.MULTILINE,
    ),
    # Import changes
    re.compile(r"^[+-]\s*(import|from)\s+\w+", re.MULTILINE),
]


def classify_mutation(diff: str) -> str:
    """Classify a pipeline diff as ``"structural"`` or ``"parametric"``.

    Uses line-level heuristics (not AST parsing).  A diff is structural if
    it adds or removes function/class definitions, ``primitives.*`` calls,
    control-flow keywords, or imports.  Everything else — string literal
    changes, number tweaks, variable renames — is parametric.

    Returns ``"parametric"`` for empty diffs (no meaningful change).
    """
    if not diff or not diff.strip():
        return "parametric"

    for pattern in _STRUCTURAL_PATTERNS:
        if pattern.search(diff):
            return "structural"

    return "parametric"


# ---------------------------------------------------------------------------
# Stagnation detection
# ---------------------------------------------------------------------------


def _extract_primary_score(entry: ArchiveEntry) -> float | None:
    """Safely extract primary_score from an entry's evaluation result."""
    result = entry.evaluation_result
    if isinstance(result, dict):
        score = result.get("primary_score")
        if score is not None:
            try:
                return float(score)
            except (TypeError, ValueError):
                return None
    return None


def analyze_strategy(
    entries: list[ArchiveEntry],
    window: int = 10,
    plateau_threshold: int = 5,
) -> str:
    """Produce a graduated strategy signal from recent archive entries.

    Parameters
    ----------
    entries:
        Recent archive entries, newest-first (as returned by
        ``Archive.recent()``).
    window:
        Maximum number of entries to consider.
    plateau_threshold:
        Consecutive iterations without score improvement before signalling
        stagnation.

    Returns
    -------
    str
        A compact human-readable hint (200–500 chars) for the meta-agent,
        or ``""`` when no guidance is warranted.
    """
    if not entries:
        return ""

    # Take at most *window* entries (already newest-first).
    window_entries = entries[:window]
    n = len(window_entries)

    if n < 2:
        return ""

    # -- Scores ---------------------------------------------------------------
    scores: list[float] = []
    for e in window_entries:
        s = _extract_primary_score(e)
        if s is not None:
            scores.append(s)

    if len(scores) < 2:
        return ""

    best_score = max(scores)

    # Plateau length: how many of the *most recent* entries have not
    # improved over the best score in the window.  Walk from newest
    # (index 0) forward.
    plateau_len = 0
    for s in scores:
        if s < best_score:
            plateau_len += 1
        else:
            break

    # Score variance (population variance — we have the full window).
    score_var = statistics.pvariance(scores)

    # -- Structural diversity -------------------------------------------------
    structural_count = 0
    parametric_count = 0
    for e in window_entries:
        mt = e.mutation_type
        if mt is None:
            mt = classify_mutation(e.pipeline_diff)
        if mt == "structural":
            structural_count += 1
        else:
            parametric_count += 1

    total_mutations = structural_count + parametric_count
    structural_ratio = (
        structural_count / total_mutations if total_mutations > 0 else 0.0
    )

    # -- Signal generation ----------------------------------------------------
    # No plateau → check if we're improving with good topology
    if plateau_len < plateau_threshold:
        # Scores are improving — suggest fine-tuning if mostly structural
        if structural_ratio > 0.7 and n >= 3:
            return (
                f"Recent iterations show improvement with structural changes "
                f"(structural ratio: {structural_ratio:.0%}). "
                f"Consider tuning parameters within the current topology "
                f"to maximize gains before further restructuring."
            )
        return ""

    # -- Plateau detected — graduated signals based on severity ---------------
    parts: list[str] = []

    # Base message with plateau length
    parts.append(
        f"Scores plateaued for {plateau_len} iterations "
        f"(best: {best_score:.3f}, variance: {score_var:.4f})."
    )

    # Guidance depends on mutation diversity
    if structural_ratio < 0.3:
        # Mostly parametric mutations during plateau → suggest structural
        parts.append(
            f"Recent mutations are mostly parametric "
            f"(structural ratio: {structural_ratio:.0%}). "
            f"Consider structural changes — add or reorganize pipeline "
            f"stages, introduce new primitives, or change control flow."
        )
    elif structural_ratio > 0.7:
        # Mostly structural mutations during plateau → suggest parameter tuning
        parts.append(
            f"Recent mutations are mostly structural "
            f"(structural ratio: {structural_ratio:.0%}). "
            f"Consider parameter tuning — adjust prompts, thresholds, "
            f"or configuration within the current topology."
        )
    else:
        # Mixed — escalate based on plateau length
        if plateau_len >= plateau_threshold + 3:
            parts.append(
                f"Mixed mutation types (structural ratio: {structural_ratio:.0%}) "
                f"with extended plateau. Consider a fundamentally different "
                f"approach — rethink the pipeline architecture rather than "
                f"incremental changes."
            )
        else:
            parts.append(
                f"Mixed mutation types (structural ratio: {structural_ratio:.0%}). "
                f"Try focusing on one dimension — either structural "
                f"reorganization or parameter optimization."
            )

    return " ".join(parts)
