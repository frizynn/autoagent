"""Tests for the Pareto dominance evaluation module."""

from __future__ import annotations

import math

import pytest

from autoagent.pareto import (
    METRIC_DIRECTIONS,
    ParetoResult,
    compute_complexity,
    pareto_decision,
    pareto_dominates,
)


# ---------------------------------------------------------------------------
# compute_complexity
# ---------------------------------------------------------------------------


class TestComputeComplexity:
    def test_simple_source(self) -> None:
        """Known simple source produces a positive, finite score."""
        source = "x = 1\ny = 2\nz = x + y\n"
        score = compute_complexity(source)
        assert 0 < score < float("inf")
        # Module + 3 Assign + 3 Name + 3 Constant + BinOp = ~11 nodes
        assert score >= 5  # at least a handful of nodes

    def test_stability(self) -> None:
        """Same source always produces the same score."""
        source = "def run(x):\n    if x > 0:\n        return x\n    return -x\n"
        scores = [compute_complexity(source) for _ in range(5)]
        assert len(set(scores)) == 1

    def test_syntax_error(self) -> None:
        """Unparseable source returns inf."""
        assert compute_complexity("def (((broken") == float("inf")

    def test_empty_string(self) -> None:
        """Empty source returns 0."""
        assert compute_complexity("") == 0.0

    def test_whitespace_only(self) -> None:
        """Whitespace-only source returns 0."""
        assert compute_complexity("   \n  \n  ") == 0.0

    def test_branch_weighting(self) -> None:
        """Source with branches scores higher than equivalent without."""
        no_branch = "x = 1\ny = 2\n"
        with_branch = "x = 1\nif x:\n    y = 2\n"
        assert compute_complexity(with_branch) > compute_complexity(no_branch)

    def test_more_complex_is_higher(self) -> None:
        """More complex code scores higher."""
        simple = "x = 1\n"
        complex_ = (
            "def run(x):\n"
            "    for i in range(10):\n"
            "        if i > 5:\n"
            "            try:\n"
            "                x += i\n"
            "            except Exception:\n"
            "                pass\n"
            "    return x\n"
        )
        assert compute_complexity(complex_) > compute_complexity(simple)


# ---------------------------------------------------------------------------
# pareto_dominates
# ---------------------------------------------------------------------------


class TestParetoDominates:
    def test_clear_winner(self) -> None:
        """Better on all metrics → dominates."""
        a = {"primary_score": 0.9, "latency_ms": 50, "cost_usd": 0.01, "complexity": 10}
        b = {"primary_score": 0.7, "latency_ms": 100, "cost_usd": 0.05, "complexity": 20}
        assert pareto_dominates(a, b) is True

    def test_mixed(self) -> None:
        """Better on some, worse on others → does NOT dominate."""
        a = {"primary_score": 0.9, "latency_ms": 150}  # better score, worse latency
        b = {"primary_score": 0.7, "latency_ms": 50}
        assert pareto_dominates(a, b) is False

    def test_equal(self) -> None:
        """Identical metrics → does NOT dominate (needs strict improvement)."""
        a = {"primary_score": 0.8, "latency_ms": 100, "cost_usd": 0.02}
        b = {"primary_score": 0.8, "latency_ms": 100, "cost_usd": 0.02}
        assert pareto_dominates(a, b) is False

    def test_direction_lower_is_better(self) -> None:
        """Lower latency IS better — verify direction handling."""
        a = {"primary_score": 0.8, "latency_ms": 50}   # same score, lower latency
        b = {"primary_score": 0.8, "latency_ms": 100}
        assert pareto_dominates(a, b) is True

    def test_direction_higher_score_is_better(self) -> None:
        """Higher primary_score IS better."""
        a = {"primary_score": 0.9, "cost_usd": 0.01}
        b = {"primary_score": 0.8, "cost_usd": 0.01}
        assert pareto_dominates(a, b) is True

    def test_partial_keys(self) -> None:
        """Only shared keys are compared."""
        a = {"primary_score": 0.9, "latency_ms": 50}
        b = {"primary_score": 0.8}  # no latency_ms
        # Only primary_score is shared — a is strictly better on it
        assert pareto_dominates(a, b) is True

    def test_no_shared_keys(self) -> None:
        """No shared metric keys → cannot dominate."""
        a = {"latency_ms": 50}
        b = {"cost_usd": 0.01}
        assert pareto_dominates(a, b) is False

    def test_unknown_keys_ignored(self) -> None:
        """Keys not in METRIC_DIRECTIONS are ignored."""
        a = {"primary_score": 0.9, "unknown_metric": 100}
        b = {"primary_score": 0.8, "unknown_metric": 1}
        # Only primary_score is in METRIC_DIRECTIONS
        assert pareto_dominates(a, b) is True


# ---------------------------------------------------------------------------
# pareto_decision
# ---------------------------------------------------------------------------


class TestParetoDecision:
    SIMPLE_SOURCE = "x = 1\n"
    COMPLEX_SOURCE = (
        "def run(x):\n"
        "    for i in range(10):\n"
        "        if i > 5:\n"
        "            x += i\n"
        "    return x\n"
    )

    def test_no_current_best(self) -> None:
        """First iteration (D024) — always keep."""
        result = pareto_decision(
            candidate_metrics={"primary_score": 0.5},
            current_best_metrics=None,
            candidate_source=self.SIMPLE_SOURCE,
            best_source=None,
        )
        assert result.decision == "keep"
        assert "D024" in result.rationale or "first" in result.rationale.lower()
        assert result.best_metrics is None

    def test_candidate_dominates(self) -> None:
        """Candidate is better on all metrics → keep."""
        result = pareto_decision(
            candidate_metrics={"primary_score": 0.9, "latency_ms": 50, "cost_usd": 0.01},
            current_best_metrics={"primary_score": 0.7, "latency_ms": 100, "cost_usd": 0.05},
            candidate_source=self.SIMPLE_SOURCE,
            best_source=self.SIMPLE_SOURCE,
        )
        assert result.decision == "keep"
        assert "dominates" in result.rationale.lower()

    def test_best_dominates(self) -> None:
        """Best is better on all metrics → discard."""
        result = pareto_decision(
            candidate_metrics={"primary_score": 0.5, "latency_ms": 200, "cost_usd": 0.10},
            current_best_metrics={"primary_score": 0.9, "latency_ms": 50, "cost_usd": 0.01},
            candidate_source=self.SIMPLE_SOURCE,
            best_source=self.SIMPLE_SOURCE,
        )
        assert result.decision == "discard"
        assert "dominates" in result.rationale.lower()

    def test_incomparable_simpler_wins(self) -> None:
        """Incomparable on metrics — simpler candidate wins (D042)."""
        result = pareto_decision(
            candidate_metrics={"primary_score": 0.9, "latency_ms": 200},  # better score, worse latency
            current_best_metrics={"primary_score": 0.7, "latency_ms": 50},
            candidate_source=self.SIMPLE_SOURCE,     # simpler
            best_source=self.COMPLEX_SOURCE,          # more complex
        )
        assert result.decision == "keep"
        assert "simpler" in result.rationale.lower() or "D042" in result.rationale

    def test_incomparable_best_simpler_wins(self) -> None:
        """Incomparable — best is simpler → discard candidate."""
        result = pareto_decision(
            candidate_metrics={"primary_score": 0.9, "latency_ms": 200},
            current_best_metrics={"primary_score": 0.7, "latency_ms": 50},
            candidate_source=self.COMPLEX_SOURCE,     # more complex
            best_source=self.SIMPLE_SOURCE,            # simpler
        )
        assert result.decision == "discard"
        assert "simpler" in result.rationale.lower() or "D042" in result.rationale

    def test_incomparable_equal_complexity(self) -> None:
        """Incomparable, same complexity → discard (conservative)."""
        result = pareto_decision(
            candidate_metrics={"primary_score": 0.9, "latency_ms": 200},
            current_best_metrics={"primary_score": 0.7, "latency_ms": 50},
            candidate_source=self.SIMPLE_SOURCE,
            best_source=self.SIMPLE_SOURCE,  # same source = same complexity
        )
        assert result.decision == "discard"
        assert "conservative" in result.rationale.lower()

    def test_none_metrics_degrades_to_score(self) -> None:
        """When only primary_score is present, behaves like score-only comparison."""
        # Higher score candidate should dominate on the only metric
        result = pareto_decision(
            candidate_metrics={"primary_score": 0.9},
            current_best_metrics={"primary_score": 0.7},
            candidate_source=self.SIMPLE_SOURCE,
            best_source=self.SIMPLE_SOURCE,
        )
        assert result.decision == "keep"

        # Lower score candidate → best dominates
        result = pareto_decision(
            candidate_metrics={"primary_score": 0.5},
            current_best_metrics={"primary_score": 0.7},
            candidate_source=self.SIMPLE_SOURCE,
            best_source=self.SIMPLE_SOURCE,
        )
        assert result.decision == "discard"

    def test_result_is_frozen(self) -> None:
        """ParetoResult is immutable."""
        result = pareto_decision(
            candidate_metrics={"primary_score": 0.9},
            current_best_metrics=None,
            candidate_source="x=1",
            best_source=None,
        )
        with pytest.raises(AttributeError):
            result.decision = "discard"  # type: ignore[misc]

    def test_result_carries_metrics(self) -> None:
        """ParetoResult includes both metric dicts."""
        cand = {"primary_score": 0.9, "latency_ms": 50}
        best = {"primary_score": 0.7, "latency_ms": 100}
        result = pareto_decision(cand, best, self.SIMPLE_SOURCE, self.SIMPLE_SOURCE)
        assert result.candidate_metrics == cand
        assert result.best_metrics == best


# ---------------------------------------------------------------------------
# ParetoResult dataclass
# ---------------------------------------------------------------------------


class TestParetoResult:
    def test_frozen(self) -> None:
        r = ParetoResult(decision="keep", rationale="test")
        with pytest.raises(AttributeError):
            r.decision = "discard"  # type: ignore[misc]

    def test_defaults(self) -> None:
        r = ParetoResult(decision="keep", rationale="test")
        assert r.candidate_metrics == {}
        assert r.best_metrics is None


# ---------------------------------------------------------------------------
# METRIC_DIRECTIONS
# ---------------------------------------------------------------------------


class TestMetricDirections:
    def test_primary_score_higher(self) -> None:
        assert METRIC_DIRECTIONS["primary_score"] == "higher"

    def test_lower_is_better_metrics(self) -> None:
        for key in ("latency_ms", "cost_usd", "complexity"):
            assert METRIC_DIRECTIONS[key] == "lower", f"{key} should be lower-is-better"
