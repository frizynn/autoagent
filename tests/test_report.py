"""Tests for the report generator module and cmd_report CLI command."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import pytest

from autoagent.archive import Archive, ArchiveEntry
from autoagent.evaluation import EvaluationResult, ExampleResult
from autoagent.report import (
    ReportResult,
    _cost_breakdown,
    _recommendations,
    _score_trajectory,
    _top_architectures,
    generate_report,
)
from autoagent.state import ProjectConfig, ProjectState, StateManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_eval_result(score: float, cost: float = 0.01) -> EvaluationResult:
    """Create a minimal EvaluationResult for testing."""
    from autoagent.types import MetricsSnapshot

    return EvaluationResult(
        primary_score=score,
        per_example_results=[
            ExampleResult(example_id="ex1", score=score, success=score > 0),
        ],
        metrics=MetricsSnapshot(
            latency_ms=100.0,
            tokens_in=50,
            tokens_out=50,
            cost_usd=cost,
            model="test",
            provider="test",
            timestamp=time.time(),
        ),
        benchmark_id="test-bench",
        duration_ms=100.0,
        num_examples=1,
        num_failures=0 if score > 0 else 1,
    )


def _make_entry(
    iteration_id: int,
    score: float,
    decision: str = "keep",
    mutation_type: str | None = "parametric",
    eval_cost: float = 0.01,
    tla_cost: float | None = None,
    leakage_cost: float | None = None,
    rationale: str = "Test rationale",
) -> ArchiveEntry:
    """Create an ArchiveEntry for testing."""
    eval_result = _make_eval_result(score, cost=eval_cost)
    tla = {"cost_usd": tla_cost, "passed": True} if tla_cost is not None else None
    leakage = {"cost_usd": leakage_cost, "passed": True} if leakage_cost is not None else None

    return ArchiveEntry(
        iteration_id=iteration_id,
        timestamp=time.time(),
        pipeline_diff="--- a\n+++ b\n",
        evaluation_result=asdict(eval_result),
        rationale=rationale,
        decision=decision,
        parent_iteration_id=iteration_id - 1 if iteration_id > 1 else None,
        mutation_type=mutation_type,
        tla_verification=tla,
        leakage_check=leakage,
    )


def _default_state(cost: float = 0.05, iteration: int = 3) -> ProjectState:
    return ProjectState(
        current_iteration=iteration,
        total_cost_usd=cost,
        phase="running",
    )


def _default_config(goal: str = "Optimize a test pipeline", budget: float | None = 1.0) -> ProjectConfig:
    return ProjectConfig(goal=goal, budget_usd=budget)


def run_cli(*args: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run the CLI as a subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "autoagent.cli", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


# ---------------------------------------------------------------------------
# _score_trajectory
# ---------------------------------------------------------------------------


class TestScoreTrajectory:
    def test_empty_entries(self) -> None:
        result = _score_trajectory([])
        assert "No iterations recorded" in result

    def test_single_entry(self) -> None:
        entries = [_make_entry(1, 0.5)]
        result = _score_trajectory(entries)
        assert "Score Trajectory" in result
        assert "0.5000" in result

    def test_progression_tracking(self) -> None:
        entries = [
            _make_entry(1, 0.3),
            _make_entry(2, 0.5),
            _make_entry(3, 0.4),  # regression, not in progression
            _make_entry(4, 0.7),
        ]
        result = _score_trajectory(entries)
        # Should show 3 improvements: 0.3, 0.5, 0.7
        assert "0.3000" in result
        assert "0.5000" in result
        assert "0.7000" in result

    def test_phase_detection_stagnated(self) -> None:
        entries = [
            _make_entry(1, 0.5),
            _make_entry(2, 0.5),
            _make_entry(3, 0.5),
        ]
        result = _score_trajectory(entries)
        assert "stagnated" in result

    def test_phase_detection_converging(self) -> None:
        entries = [
            _make_entry(1, 0.3),
            _make_entry(2, 0.5),
            _make_entry(3, 0.7),
        ]
        result = _score_trajectory(entries)
        assert "converging" in result


# ---------------------------------------------------------------------------
# _top_architectures
# ---------------------------------------------------------------------------


class TestTopArchitectures:
    def test_empty_entries(self) -> None:
        result = _top_architectures([])
        assert "No iterations recorded" in result

    def test_all_discarded(self) -> None:
        entries = [
            _make_entry(1, 0.3, decision="discard"),
            _make_entry(2, 0.2, decision="discard"),
        ]
        result = _top_architectures(entries)
        assert "No iterations were kept" in result
        assert "discarded" in result

    def test_top_k_ordering(self) -> None:
        entries = [
            _make_entry(1, 0.3, decision="keep"),
            _make_entry(2, 0.9, decision="keep"),
            _make_entry(3, 0.5, decision="keep"),
            _make_entry(4, 0.1, decision="discard"),
        ]
        result = _top_architectures(entries, limit=2)
        # Should show iteration 2 first (0.9), then iteration 3 (0.5)
        assert result.index("Iteration 2") < result.index("Iteration 3")

    def test_limit_respected(self) -> None:
        entries = [_make_entry(i, 0.1 * i, decision="keep") for i in range(1, 8)]
        result = _top_architectures(entries, limit=3)
        # Should only show 3
        assert result.count("Iteration") == 3

    def test_mixed_decisions(self) -> None:
        entries = [
            _make_entry(1, 0.8, decision="keep"),
            _make_entry(2, 0.2, decision="discard"),
            _make_entry(3, 0.6, decision="keep"),
        ]
        result = _top_architectures(entries)
        assert "Iteration 1" in result
        assert "Iteration 3" in result
        # Discarded entry should not appear in top architectures
        assert "Iteration 2" not in result


# ---------------------------------------------------------------------------
# _cost_breakdown
# ---------------------------------------------------------------------------


class TestCostBreakdown:
    def test_empty_entries(self) -> None:
        state = _default_state(cost=0.0)
        result = _cost_breakdown(state, [])
        assert "No iterations to break down" in result
        assert "$0.0000" in result

    def test_total_cost_from_state(self) -> None:
        state = _default_state(cost=1.2345)
        entries = [_make_entry(1, 0.5, eval_cost=0.01)]
        result = _cost_breakdown(state, entries)
        assert "$1.2345" in result

    def test_gate_costs_summed(self) -> None:
        state = _default_state(cost=0.10)
        entries = [
            _make_entry(1, 0.5, eval_cost=0.01, tla_cost=0.02, leakage_cost=0.03),
            _make_entry(2, 0.6, eval_cost=0.01, tla_cost=0.01, leakage_cost=0.02),
        ]
        result = _cost_breakdown(state, entries)
        # TLA total: 0.02 + 0.01 = 0.03
        assert "TLA+ verification costs" in result
        assert "$0.0300" in result
        # Leakage total: 0.03 + 0.02 = 0.05
        assert "Leakage check costs" in result
        assert "$0.0500" in result
        # Gate subtotal: 0.03 + 0.05 = 0.08
        assert "$0.0800" in result

    def test_missing_gate_costs_handled(self) -> None:
        state = _default_state(cost=0.05)
        entries = [_make_entry(1, 0.5, eval_cost=0.01)]
        result = _cost_breakdown(state, entries)
        # Should not crash, gate costs should be 0
        assert "TLA+ verification costs" in result
        assert "$0.0000" in result


# ---------------------------------------------------------------------------
# _recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    def test_empty_entries(self) -> None:
        state = _default_state()
        result = _recommendations([], state)
        assert "Recommendations" in result
        assert "No stagnation" in result

    def test_budget_remaining(self) -> None:
        state = _default_state(cost=0.30)
        config = _default_config(budget=1.0)
        result = _recommendations([], state, config)
        assert "$0.7000" in result
        assert "70.0%" in result

    def test_no_budget_configured(self) -> None:
        state = _default_state()
        config = _default_config(budget=None)
        result = _recommendations([], state, config)
        assert "No budget limit" in result

    def test_stagnation_signal(self) -> None:
        # Create entries where best was early and recent iterations can't improve
        entries = [_make_entry(1, 0.8)]  # best score
        entries += [_make_entry(i, 0.5) for i in range(2, 9)]  # 7 stagnant
        state = _default_state(iteration=8)
        config = _default_config()
        result = _recommendations(entries, state, config)
        assert "Strategy signal" in result


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_empty_archive(self) -> None:
        state = _default_state(cost=0.0, iteration=0)
        config = _default_config()
        result = generate_report([], state, config)

        assert isinstance(result, ReportResult)
        assert "No optimization data available" in result.markdown
        assert "No data" in result.summary
        assert "Optimization Report" in result.markdown

    def test_full_report_with_all_sections(self) -> None:
        entries = [
            _make_entry(1, 0.3, decision="keep", tla_cost=0.01, leakage_cost=0.02),
            _make_entry(2, 0.5, decision="keep", tla_cost=0.01),
            _make_entry(3, 0.4, decision="discard"),
        ]
        state = _default_state(cost=0.10, iteration=3)
        config = _default_config(goal="Test goal", budget=1.0)

        result = generate_report(entries, state, config)

        assert isinstance(result, ReportResult)
        # Header
        assert "Test goal" in result.markdown
        assert "3" in result.markdown  # iterations
        assert "0.5000" in result.markdown  # best score

        # All sections present
        assert "## Score Trajectory" in result.markdown
        assert "## Top Architectures" in result.markdown
        assert "## Cost Breakdown" in result.markdown
        assert "## Recommendations" in result.markdown

        # Summary
        assert "3 iterations" in result.summary
        assert "2 kept" in result.summary
        assert "0.5000" in result.summary

    def test_all_discarded_entries(self) -> None:
        entries = [
            _make_entry(1, 0.2, decision="discard"),
            _make_entry(2, 0.1, decision="discard"),
        ]
        state = _default_state(cost=0.02, iteration=2)
        config = _default_config()

        result = generate_report(entries, state, config)

        # Should not crash
        assert "Top Architectures" in result.markdown
        assert "No iterations were kept" in result.markdown
        assert "0 kept" in result.summary

    def test_report_result_is_frozen(self) -> None:
        result = ReportResult(markdown="# test", summary="test")
        with pytest.raises(AttributeError):
            result.markdown = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# cmd_report CLI
# ---------------------------------------------------------------------------


class TestCmdReport:
    def test_report_not_initialized(self, tmp_path: Path) -> None:
        result = run_cli("--project-dir", str(tmp_path), "report")
        assert result.returncode == 1
        assert "no autoagent project found" in result.stderr

    def test_report_empty_archive(self, tmp_path: Path) -> None:
        # Initialize project
        sm = StateManager(tmp_path)
        sm.init_project()

        result = run_cli("--project-dir", str(tmp_path), "report")
        assert result.returncode == 0
        assert "No data" in result.stdout

        # Check report.md written
        report_path = tmp_path / ".autoagent" / "report.md"
        assert report_path.exists()
        content = report_path.read_text(encoding="utf-8")
        assert "Optimization Report" in content

    def test_report_with_archive_data(self, tmp_path: Path) -> None:
        # Initialize project with a goal
        sm = StateManager(tmp_path)
        sm.init_project()
        config = ProjectConfig(goal="Test optimization")
        sm.write_config(config)

        # Add archive entries
        archive = Archive(sm.archive_dir)
        eval1 = _make_eval_result(0.5, cost=0.01)
        archive.add(
            pipeline_source="def run(x, p=None): return {'out': x}",
            evaluation_result=eval1,
            rationale="Initial pipeline",
            decision="keep",
            mutation_type="structural",
        )
        eval2 = _make_eval_result(0.7, cost=0.02)
        archive.add(
            pipeline_source="def run(x, p=None): return {'out': x, 'extra': 1}",
            evaluation_result=eval2,
            rationale="Improved pipeline",
            decision="keep",
            parent_iteration_id=1,
            mutation_type="parametric",
        )

        result = run_cli("--project-dir", str(tmp_path), "report")
        assert result.returncode == 0
        assert "2 iterations" in result.stdout
        assert "2 kept" in result.stdout

        # Report file
        report_path = tmp_path / ".autoagent" / "report.md"
        assert report_path.exists()
        content = report_path.read_text(encoding="utf-8")
        assert "Score Trajectory" in content
        assert "Top Architectures" in content
        assert "Cost Breakdown" in content
        assert "Recommendations" in content
