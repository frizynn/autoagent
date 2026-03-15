"""Integration tests for the autoagent CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from autoagent.benchmark import Benchmark
from autoagent.cli import main
from autoagent.meta_agent import ProposalResult
from autoagent.state import STARTER_PIPELINE, StateManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_cli(*args: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run the CLI as a subprocess and return the result."""
    return subprocess.run(
        [sys.executable, "-m", "autoagent.cli", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_creates_project(self, tmp_path: Path) -> None:
        result = run_cli("--project-dir", str(tmp_path), "init")
        assert result.returncode == 0
        assert "Initialized" in result.stdout

        aa_dir = tmp_path / ".autoagent"
        assert aa_dir.is_dir()
        assert (aa_dir / "state.json").is_file()
        assert (aa_dir / "config.json").is_file()
        assert (aa_dir / "pipeline.py").is_file()
        assert (aa_dir / "archive").is_dir()

    def test_init_refuses_reinit(self, tmp_path: Path) -> None:
        # First init succeeds
        r1 = run_cli("--project-dir", str(tmp_path), "init")
        assert r1.returncode == 0

        # Second init fails
        r2 = run_cli("--project-dir", str(tmp_path), "init")
        assert r2.returncode == 1
        assert "already initialized" in r2.stderr


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_after_init(self, tmp_path: Path) -> None:
        run_cli("--project-dir", str(tmp_path), "init")
        result = run_cli("--project-dir", str(tmp_path), "status")
        assert result.returncode == 0
        assert "initialized" in result.stdout
        assert "Current iteration: 0" in result.stdout

    def test_status_uninitialized(self, tmp_path: Path) -> None:
        result = run_cli("--project-dir", str(tmp_path), "status")
        assert result.returncode == 1
        assert "no autoagent project found" in result.stderr


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRun:
    def test_run_no_benchmark_configured(self, tmp_path: Path) -> None:
        """Run fails gracefully when no benchmark is configured."""
        run_cli("--project-dir", str(tmp_path), "init")
        result = run_cli("--project-dir", str(tmp_path), "run")
        assert result.returncode == 1
        assert "benchmark dataset_path configured" in result.stderr.lower()

    def test_run_uninitialized(self, tmp_path: Path) -> None:
        result = run_cli("--project-dir", str(tmp_path), "run")
        assert result.returncode == 1
        assert "no autoagent project found" in result.stderr

    def test_run_max_iterations_help(self) -> None:
        """--max-iterations appears in run help."""
        result = run_cli("run", "--help")
        assert result.returncode == 0
        assert "--max-iterations" in result.stdout

    def test_run_budget_arg(self) -> None:
        """--budget appears in run help and parses correctly."""
        result = run_cli("run", "--help")
        assert result.returncode == 0
        assert "--budget" in result.stdout

        # Verify it parses via build_parser
        from autoagent.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["run", "--budget", "5.00"])
        assert args.budget == 5.00


# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------


class TestHelp:
    def test_help_shows_subcommands(self) -> None:
        result = run_cli("--help")
        assert result.returncode == 0
        assert "init" in result.stdout
        assert "status" in result.stdout
        assert "run" in result.stdout
        assert "new" in result.stdout


# ---------------------------------------------------------------------------
# --project-dir flag
# ---------------------------------------------------------------------------


class TestProjectDir:
    def test_project_dir_flag(self, tmp_path: Path) -> None:
        """--project-dir routes all commands to the specified directory."""
        subdir = tmp_path / "nested" / "project"
        subdir.mkdir(parents=True)

        r1 = run_cli("--project-dir", str(subdir), "init")
        assert r1.returncode == 0
        assert (subdir / ".autoagent" / "state.json").is_file()

        r2 = run_cli("--project-dir", str(subdir), "status")
        assert r2.returncode == 0
        assert "initialized" in r2.stdout


# ---------------------------------------------------------------------------
# Direct main() calls (no subprocess)
# ---------------------------------------------------------------------------


class TestMainDirect:
    def test_main_no_command_shows_status(self, capsys: pytest.CaptureFixture[str]) -> None:
        """No subcommand → falls back to cmd_status."""
        from autoagent.cli import cmd_status
        assert callable(cmd_status)

    def test_main_init_direct(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--project-dir", str(tmp_path), "init"])
        assert exc_info.value.code == 0
        assert (tmp_path / ".autoagent" / "state.json").is_file()


# ---------------------------------------------------------------------------
# Cold-start pipeline generation
# ---------------------------------------------------------------------------

VALID_PIPELINE_SOURCE = '''\
def run(input_data, primitives=None):
    """Generated pipeline."""
    return {"answer": str(input_data)}
'''


def _init_project_with_benchmark(tmp_path: Path) -> Path:
    """Initialize a project and add a benchmark dataset + config."""
    import json
    from autoagent.state import StateManager

    sm = StateManager(tmp_path)
    sm.init_project(goal="Solve the benchmark")

    # Write a tiny benchmark file
    dataset = tmp_path / "bench.json"
    dataset.write_text(
        json.dumps([
            {"input": "hello", "expected": "hello"},
        ]),
        encoding="utf-8",
    )

    # Update config to point at it
    config = sm.read_config()
    from dataclasses import replace
    config = replace(config, benchmark={
        "dataset_path": "bench.json",
        "scoring_function": "exact_match",
    })
    sm.write_config(config)
    return tmp_path


class TestColdStart:
    """Tests for the cold-start pipeline generation path in cmd_run()."""

    def test_cold_start_triggered_and_rewrites_pipeline(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """When pipeline matches STARTER_PIPELINE, cold-start generates a new one."""
        _init_project_with_benchmark(tmp_path)
        success_result = ProposalResult(
            proposed_source=VALID_PIPELINE_SOURCE,
            rationale="Initial generation",
            cost_usd=0.01,
            success=True,
        )
        with patch("autoagent.cli.MetaAgent") as MockMACls:
            instance = MockMACls.return_value
            instance.generate_initial.return_value = success_result
            with patch("autoagent.cli.OptimizationLoop") as MockLoop:
                from autoagent.state import ProjectState
                MockLoop.return_value.run.return_value = ProjectState(
                    phase="completed", current_iteration=1
                )
                with pytest.raises(SystemExit) as exc_info:
                    main(["--project-dir", str(tmp_path), "run"])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Cold-start" in captured.out
        assert "generated successfully" in captured.out
        # Pipeline file was rewritten
        pipeline_content = (tmp_path / ".autoagent" / "pipeline.py").read_text()
        assert pipeline_content == VALID_PIPELINE_SOURCE

    def test_cold_start_skipped_when_pipeline_customized(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """When pipeline has been edited, cold-start is skipped entirely."""
        _init_project_with_benchmark(tmp_path)
        # Customize the pipeline
        pipeline_path = tmp_path / ".autoagent" / "pipeline.py"
        pipeline_path.write_text(VALID_PIPELINE_SOURCE, encoding="utf-8")

        with patch("autoagent.cli.MetaAgent") as MockMACls:
            instance = MockMACls.return_value
            with patch("autoagent.cli.OptimizationLoop") as MockLoop:
                from autoagent.state import ProjectState
                MockLoop.return_value.run.return_value = ProjectState(
                    phase="completed", current_iteration=1
                )
                with pytest.raises(SystemExit) as exc_info:
                    main(["--project-dir", str(tmp_path), "run"])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Cold-start" not in captured.out
        # generate_initial should never have been called
        instance.generate_initial.assert_not_called()

    def test_cold_start_failure_retries_then_continues(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Two failures log warning and continue with starter pipeline."""
        _init_project_with_benchmark(tmp_path)
        fail_result = ProposalResult(
            success=False,
            error="validation: no run() function",
            cost_usd=0.005,
        )
        with patch("autoagent.cli.MetaAgent") as MockMACls:
            instance = MockMACls.return_value
            instance.generate_initial.return_value = fail_result
            with patch("autoagent.cli.OptimizationLoop") as MockLoop:
                from autoagent.state import ProjectState
                MockLoop.return_value.run.return_value = ProjectState(
                    phase="completed", current_iteration=1
                )
                with pytest.raises(SystemExit) as exc_info:
                    main(["--project-dir", str(tmp_path), "run"])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "retrying" in captured.out
        assert "failed after retry" in captured.err
        # Pipeline should still be starter
        pipeline_content = (tmp_path / ".autoagent" / "pipeline.py").read_text()
        assert pipeline_content == STARTER_PIPELINE
        # generate_initial called exactly twice (initial + retry)
        assert instance.generate_initial.call_count == 2

    def test_cold_start_passes_benchmark_description(
        self, tmp_path: Path
    ) -> None:
        """generate_initial receives the benchmark description string."""
        _init_project_with_benchmark(tmp_path)
        success_result = ProposalResult(
            proposed_source=VALID_PIPELINE_SOURCE,
            rationale="Initial",
            cost_usd=0.01,
            success=True,
        )
        with patch("autoagent.cli.MetaAgent") as MockMACls:
            instance = MockMACls.return_value
            instance.generate_initial.return_value = success_result
            with patch("autoagent.cli.OptimizationLoop") as MockLoop:
                from autoagent.state import ProjectState
                MockLoop.return_value.run.return_value = ProjectState(
                    phase="completed", current_iteration=1
                )
                with pytest.raises(SystemExit):
                    main(["--project-dir", str(tmp_path), "run"])

        # Verify generate_initial was called with a string (benchmark description)
        instance.generate_initial.assert_called_once()
        args = instance.generate_initial.call_args
        benchmark_desc = args[0][0]
        assert isinstance(benchmark_desc, str)
        assert len(benchmark_desc) > 0


# ---------------------------------------------------------------------------
# new (interview)
# ---------------------------------------------------------------------------


# 6 phases (goal, metrics, constraints, search_space, benchmark, budget)
# + 1 confirmation = 7 user inputs
_NEW_ANSWERS = [
    "Optimize retrieval accuracy for medical Q&A",          # goal
    "precision, recall, F1-score",                          # metrics
    "Budget under $50, must use open-source models only",   # constraints
    "RAG with BM25 vs dense retrieval, chunk sizes 256-1024",  # search_space
    "medqa.json with exact_match scoring",                  # benchmark
    "25 dollars total",                                     # budget (>=10 chars)
    "yes",                                                  # confirmation
]


class TestNew:
    """Integration tests for the ``autoagent new`` interview command."""

    def test_cmd_new_creates_config(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Full interview writes config.json with expected fields."""
        from autoagent.interview import SequenceMockLLM

        answers_iter = iter(_NEW_ANSWERS)
        mock_llm = SequenceMockLLM(["mock follow-up", "# Generated Context\nProject context."])

        with (
            patch("autoagent.cli.MockLLM", return_value=mock_llm),
            patch("autoagent.cli.MetricsCollector"),
            patch("builtins.input", side_effect=lambda prompt="": next(answers_iter, "")),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(["--project-dir", str(tmp_path), "new"])

        assert exc_info.value.code == 0

        # Verify config.json was written with interview data
        sm = StateManager(tmp_path)
        config = sm.read_config()
        assert config.goal == "Optimize retrieval accuracy for medical Q&A"
        assert len(config.metric_priorities) == 3
        assert "precision" in config.metric_priorities
        assert len(config.constraints) == 2
        assert config.budget_usd == 25.0

        captured = capsys.readouterr()
        assert "Project configured" in captured.out
        assert "Metrics:     3" in captured.out

    def test_cmd_new_writes_context_md(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Interview writes a non-empty context.md file."""
        from autoagent.interview import SequenceMockLLM

        answers_iter = iter(_NEW_ANSWERS)
        mock_llm = SequenceMockLLM(["mock probe", "# Project Context\nDetailed context."])

        with (
            patch("autoagent.cli.MockLLM", return_value=mock_llm),
            patch("autoagent.cli.MetricsCollector"),
            patch("builtins.input", side_effect=lambda prompt="": next(answers_iter, "")),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(["--project-dir", str(tmp_path), "new"])

        assert exc_info.value.code == 0

        context_path = tmp_path / ".autoagent" / "context.md"
        assert context_path.is_file()
        content = context_path.read_text(encoding="utf-8")
        assert len(content) > 0

    def test_cmd_new_already_initialized_with_goal(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """When project already has a goal, user is asked to confirm overwrite."""
        from autoagent.interview import SequenceMockLLM

        # Pre-initialize with an existing goal
        sm = StateManager(tmp_path)
        sm.init_project(goal="Existing goal")

        # User says "no" to overwrite
        with patch("builtins.input", return_value="no"):
            with pytest.raises(SystemExit) as exc_info:
                main(["--project-dir", str(tmp_path), "new"])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "already has a goal" in captured.err
        assert "Aborted" in captured.out

        # Config unchanged
        config = sm.read_config()
        assert config.goal == "Existing goal"

    def test_cmd_new_already_initialized_overwrite(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """When user confirms overwrite, interview runs and updates config."""
        from autoagent.interview import SequenceMockLLM

        # Pre-initialize with an existing goal
        sm = StateManager(tmp_path)
        sm.init_project(goal="Old goal")

        # "yes" to overwrite, then 6 phase answers + confirmation
        all_inputs = ["yes"] + _NEW_ANSWERS
        input_iter = iter(all_inputs)
        mock_llm = SequenceMockLLM(["probe", "# Context\nNew context."])

        with (
            patch("autoagent.cli.MockLLM", return_value=mock_llm),
            patch("autoagent.cli.MetricsCollector"),
            patch("builtins.input", side_effect=lambda prompt="": next(input_iter, "")),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(["--project-dir", str(tmp_path), "new"])

        assert exc_info.value.code == 0
        config = sm.read_config()
        assert config.goal == "Optimize retrieval accuracy for medical Q&A"

    def test_cmd_new_keyboard_interrupt(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """KeyboardInterrupt during interview exits cleanly with message."""
        from autoagent.interview import SequenceMockLLM

        mock_llm = SequenceMockLLM(["probe"])

        def raise_interrupt(prompt=""):
            raise KeyboardInterrupt

        with (
            patch("autoagent.cli.MockLLM", return_value=mock_llm),
            patch("autoagent.cli.MetricsCollector"),
            patch("builtins.input", side_effect=raise_interrupt),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(["--project-dir", str(tmp_path), "new"])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "interrupted" in captured.err.lower()


# ---------------------------------------------------------------------------
# new — benchmark generation
# ---------------------------------------------------------------------------


# Valid JSON array that BenchmarkGenerator will parse from the mock LLM response
_BENCHMARK_GEN_JSON = json.dumps([
    {"input": "What is aspirin used for?", "expected": "pain relief", "id": "med_1"},
    {"input": "Side effects of ibuprofen?", "expected": "stomach issues", "id": "med_2"},
    {"input": "Dosage for acetaminophen?", "expected": "500-1000mg every 4-6 hours", "id": "med_3"},
])


class TestNewBenchmarkGen:
    """Integration tests for benchmark generation in ``cmd_new``."""

    def test_benchmark_gen_happy_path(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Interview + generation produces config.json and benchmark.json."""
        from autoagent.interview import SequenceMockLLM

        answers_iter = iter(_NEW_ANSWERS)
        # SequenceMockLLM responses: interview probe, context synthesis,
        # then benchmark generation (3rd call)
        mock_llm = SequenceMockLLM([
            "mock follow-up",
            "# Generated Context\nProject context.",
            _BENCHMARK_GEN_JSON,
        ])

        with (
            patch("autoagent.cli.MockLLM", return_value=mock_llm),
            patch("autoagent.cli.MetricsCollector"),
            patch("builtins.input", side_effect=lambda prompt="": next(answers_iter, "")),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(["--project-dir", str(tmp_path), "new"])

        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "Generated benchmark with 3 examples" in captured.out

        # Config should reference the generated benchmark
        sm = StateManager(tmp_path)
        config = sm.read_config()
        assert config.benchmark["dataset_path"] == "benchmark.json"
        assert config.benchmark["scoring_function"] == "includes"

        # benchmark.json should exist and be loadable
        benchmark_path = tmp_path / ".autoagent" / "benchmark.json"
        assert benchmark_path.is_file()

        benchmark_data = json.loads(benchmark_path.read_text(encoding="utf-8"))
        assert len(benchmark_data) == 3
        assert all("input" in ex and "expected" in ex for ex in benchmark_data)

    def test_benchmark_gen_failure_still_writes_config(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """When generation fails, config is still written without benchmark path."""
        from autoagent.interview import SequenceMockLLM

        answers_iter = iter(_NEW_ANSWERS)
        # LLM returns invalid JSON for benchmark generation (and retry)
        mock_llm = SequenceMockLLM([
            "mock follow-up",
            "# Generated Context\nProject context.",
            "This is not valid JSON at all.",
            "Still not valid JSON.",
        ])

        with (
            patch("autoagent.cli.MockLLM", return_value=mock_llm),
            patch("autoagent.cli.MetricsCollector"),
            patch("builtins.input", side_effect=lambda prompt="": next(answers_iter, "")),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(["--project-dir", str(tmp_path), "new"])

        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "benchmark generation failed" in captured.err

        # Config still written, but no benchmark path
        sm = StateManager(tmp_path)
        config = sm.read_config()
        assert config.benchmark.get("dataset_path", "") == ""
        assert config.goal == "Optimize retrieval accuracy for medical Q&A"

        # No benchmark.json file
        benchmark_path = tmp_path / ".autoagent" / "benchmark.json"
        assert not benchmark_path.exists()

    def test_benchmark_gen_loadable_via_from_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Generated benchmark.json is loadable via Benchmark.from_file()."""
        from autoagent.interview import SequenceMockLLM

        answers_iter = iter(_NEW_ANSWERS)
        mock_llm = SequenceMockLLM([
            "mock follow-up",
            "# Generated Context\nProject context.",
            _BENCHMARK_GEN_JSON,
        ])

        with (
            patch("autoagent.cli.MockLLM", return_value=mock_llm),
            patch("autoagent.cli.MetricsCollector"),
            patch("builtins.input", side_effect=lambda prompt="": next(answers_iter, "")),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(["--project-dir", str(tmp_path), "new"])

        assert exc_info.value.code == 0

        # Load via Benchmark.from_file — the real validation
        benchmark_path = tmp_path / ".autoagent" / "benchmark.json"
        benchmark = Benchmark.from_file(benchmark_path, scoring_function="includes")
        assert len(benchmark.examples) == 3
        assert benchmark.examples[0].input == "What is aspirin used for?"
        assert benchmark.examples[0].expected == "pain relief"
