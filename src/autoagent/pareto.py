"""Pareto dominance evaluation with simplicity tiebreaker.

Pure functions for multi-objective comparison across (primary_score,
latency_ms, cost_usd, complexity).  Incomparable pipelines are resolved
by preferring simpler code (D042 / R020).  First iteration is always
kept (D024).

Self-contained — no imports from loop.py or archive.py.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metric direction configuration
# ---------------------------------------------------------------------------

METRIC_DIRECTIONS: dict[str, str] = {
    "primary_score": "higher",
    "latency_ms": "lower",
    "cost_usd": "lower",
    "complexity": "lower",
}
"""Which direction is 'better' for each metric in the Pareto vector."""

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParetoResult:
    """Outcome of a Pareto dominance evaluation.

    Fields:
        decision: ``"keep"`` or ``"discard"``.
        rationale: Human/agent-readable explanation for the decision.
        candidate_metrics: The metric vector of the candidate pipeline.
        best_metrics: The metric vector of the current best (None on first iteration).
    """

    decision: str
    rationale: str
    candidate_metrics: dict[str, Any] = field(default_factory=dict)
    best_metrics: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Complexity scoring
# ---------------------------------------------------------------------------

# AST node types that indicate branching / structural complexity.
_BRANCH_NODE_TYPES = (
    ast.If,
    ast.For,
    ast.While,
    ast.Try,
    ast.With,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
)

_BRANCH_WEIGHT = 2  # Branch nodes count double.


def compute_complexity(source: str) -> float:
    """Return an AST-based complexity score for Python *source*.

    Score = (total AST nodes) + (branch-statement nodes × extra weight).
    Higher values mean more complex code.

    Returns ``float('inf')`` if *source* has a ``SyntaxError`` — unparseable
    code is treated as maximally complex.  An empty string returns ``0.0``.
    """
    if not source or not source.strip():
        return 0.0

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return float("inf")

    total = 0
    branch_extra = 0
    for node in ast.walk(tree):
        total += 1
        if isinstance(node, _BRANCH_NODE_TYPES):
            branch_extra += _BRANCH_WEIGHT

    score = float(total + branch_extra)
    return score


# ---------------------------------------------------------------------------
# Pareto dominance
# ---------------------------------------------------------------------------


def pareto_dominates(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Return True if metric vector *a* Pareto-dominates *b*.

    *a* dominates *b* iff *a* is at least as good as *b* on every shared
    metric **and** strictly better on at least one.  Metric directions are
    looked up in :data:`METRIC_DIRECTIONS`.

    Only keys present in **both** dicts are compared.  If no shared keys
    exist, returns False (cannot dominate with no basis for comparison).
    """
    shared_keys = set(a) & set(b) & set(METRIC_DIRECTIONS)
    if not shared_keys:
        return False

    at_least_as_good = True
    strictly_better = False

    for key in shared_keys:
        a_val = float(a[key])
        b_val = float(b[key])
        direction = METRIC_DIRECTIONS[key]

        if direction == "higher":
            if a_val < b_val:
                at_least_as_good = False
                break
            if a_val > b_val:
                strictly_better = True
        else:  # "lower"
            if a_val > b_val:
                at_least_as_good = False
                break
            if a_val < b_val:
                strictly_better = True

    return at_least_as_good and strictly_better


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------


def pareto_decision(
    candidate_metrics: dict[str, Any],
    current_best_metrics: dict[str, Any] | None,
    candidate_source: str,
    best_source: str | None,
) -> ParetoResult:
    """Decide whether to keep or discard the candidate pipeline.

    Decision rules (in order):

    1. **No current best** (first iteration, D024) → keep.
    2. **Candidate dominates** best → keep.
    3. **Best dominates** candidate → discard.
    4. **Incomparable** → prefer the simpler pipeline (D042 / R020).
       If complexity is equal, discard (conservative — keep the incumbent).

    Parameters
    ----------
    candidate_metrics:
        Metric dict for the candidate (must include at least ``primary_score``).
    current_best_metrics:
        Metric dict for the current best pipeline, or ``None`` if this is the
        first iteration.
    candidate_source:
        Source code of the candidate pipeline (used for complexity scoring).
    best_source:
        Source code of the current best pipeline, or ``None``.

    Returns
    -------
    ParetoResult
        Frozen dataclass with ``decision``, ``rationale``, and both metric dicts.
    """
    # D024: first iteration — always keep
    if current_best_metrics is None:
        return ParetoResult(
            decision="keep",
            rationale="First iteration — no current best to compare against (D024)",
            candidate_metrics=candidate_metrics,
            best_metrics=None,
        )

    # Check dominance in both directions
    candidate_wins = pareto_dominates(candidate_metrics, current_best_metrics)
    best_wins = pareto_dominates(current_best_metrics, candidate_metrics)

    if candidate_wins:
        return ParetoResult(
            decision="keep",
            rationale="Candidate Pareto-dominates current best on all shared metrics",
            candidate_metrics=candidate_metrics,
            best_metrics=current_best_metrics,
        )

    if best_wins:
        return ParetoResult(
            decision="discard",
            rationale="Current best Pareto-dominates candidate on all shared metrics",
            candidate_metrics=candidate_metrics,
            best_metrics=current_best_metrics,
        )

    # Incomparable — use simplicity tiebreaker (D042)
    cand_complexity = compute_complexity(candidate_source)
    best_complexity = compute_complexity(best_source or "")

    if cand_complexity < best_complexity:
        return ParetoResult(
            decision="keep",
            rationale=(
                f"Incomparable on metrics — candidate is simpler "
                f"(complexity {cand_complexity:.1f} vs {best_complexity:.1f}, D042)"
            ),
            candidate_metrics=candidate_metrics,
            best_metrics=current_best_metrics,
        )

    if cand_complexity > best_complexity:
        return ParetoResult(
            decision="discard",
            rationale=(
                f"Incomparable on metrics — current best is simpler "
                f"(complexity {best_complexity:.1f} vs {cand_complexity:.1f}, D042)"
            ),
            candidate_metrics=candidate_metrics,
            best_metrics=current_best_metrics,
        )

    # Equal complexity — conservative: keep the incumbent
    return ParetoResult(
        decision="discard",
        rationale=(
            f"Incomparable on metrics, equal complexity "
            f"({cand_complexity:.1f}) — keeping incumbent (conservative)"
        ),
        candidate_metrics=candidate_metrics,
        best_metrics=current_best_metrics,
    )
