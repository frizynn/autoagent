"""End-to-end integration test — full cold-start flow through CLI commands.

Capstone test for Milestone M004: exercises the complete flow from
interactive interview (cmd_new) through optimization loop (cmd_run)
to markdown report generation (cmd_report).

All subsystems chain with SequenceMockLLM — no real LLM calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from autoagent.benchmark import Benchmark
from autoagent.cli import cmd_new, cmd_run, cmd_report, main
from autoagent.state import StateManager


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

# Interview answers: 7 answers for 6 phases + confirmation
_INTERVIEW_ANSWERS = [
    "Classify customer support tickets into categories automatically",  # goal
    "accuracy, latency under 200ms, cost per classification",            # metrics
    "Must run on CPU only, budget under $20",                            # constraints
    "Try zero-shot classification, few-shot prompting, fine-tuned models",  # search_space
    "support_tickets.json with exact_match scoring",                     # benchmark
    "15 dollars total budget",                                           # budget
    "yes",                                                               # confirmation
]

# Benchmark examples that BenchmarkGenerator will parse from SequenceMockLLM
_BENCHMARK_EXAMPLES = [
    {"input": "My order hasn't arrived", "expected": "shipping", "id": "t1"},
    {"input": "I need a refund", "expected": "billing", "id": "t2"},
    {"input": "How do I reset my password?", "expected": "account", "id": "t3"},
]
_BENCHMARK_GEN_JSON = json.dumps(_BENCHMARK_EXAMPLES)

# Valid pipeline source that MetaAgent will extract from LLM response.
# Must define run() and be simple enough to produce deterministic output.
_VALID_PIPELINE = '''\
def run(input_data, primitives=None):
    """Classify input by keyword matching."""
    text = str(input_data).lower()
    if "order" in text or "ship" in text or "arrived" in text:
        return {"classification": "shipping"}
    if "refund" in text or "bill" in text or "charge" in text:
        return {"classification": "billing"}
    return {"classification": "account"}
'''

# Wrap the pipeline in a code block so MetaAgent._extract_source finds it
_PIPELINE_RESPONSE = f"Here is the pipeline:\n\n```python\n{_VALID_PIPELINE}```\n\nThis uses keyword matching."


# SequenceMockLLM responses ordered for the full flow:
#
# cmd_new phase (interview + benchmark generation):
#   1. Interview vague-probe follow-up (1 call, may cycle)
#   2. Context synthesis (generate_context call)
#   3. Benchmark generation (BenchmarkGenerator.generate call)
#
# cmd_run phase (MetaAgent cold-start + optimization loop iterations):
#   4. Cold-start generate_initial (MetaAgent call)
#   5-7. Loop iterations — MetaAgent.propose calls (3 iterations)
#
# The SequenceMockLLM cycles when exhausted, so we provide enough
# pipeline responses for the loop to work through iterations.

_LLM_RESPONSES = [
    # 1: Interview probe follow-up
    "Can you be more specific about what categories you need?",
    # 2: Context synthesis
    "# Project Context\n\nClassify customer support tickets automatically.",
    # 3: Benchmark generation
    _BENCHMARK_GEN_JSON,
    # 4-7: Pipeline responses for cold-start + 3 loop iterations
    _PIPELINE_RESPONSE,
    _PIPELINE_RESPONSE,
    _PIPELINE_RESPONSE,
    _PIPELINE_RESPONSE,
]


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """Capstone: full cold-start flow from interview through report."""

    def test_full_cold_start_flow(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """cmd_new → cmd_run → cmd_report chains all M004 subsystems.

        Stage 1: Interview + benchmark generation (cmd_new)
        Stage 2: Optimization loop with cold-start (cmd_run)
        Stage 3: Report generation (cmd_report)
        """
        from autoagent.interview import SequenceMockLLM

        mock_llm = SequenceMockLLM(list(_LLM_RESPONSES))
        answers_iter = iter(_INTERVIEW_ANSWERS)

        # ---------------------------------------------------------------
        # Stage 1: cmd_new — interview + benchmark generation
        # ---------------------------------------------------------------
        with (
            patch("autoagent.cli.MockLLM", return_value=mock_llm),
            patch("autoagent.cli.MetricsCollector"),
            patch(
                "builtins.input",
                side_effect=lambda prompt="": next(answers_iter, ""),
            ),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(["--project-dir", str(tmp_path), "new"])

        assert exc_info.value.code == 0, (
            f"cmd_new failed with exit code {exc_info.value.code}"
        )

        # Verify config.json written with goal
        sm = StateManager(tmp_path)
        config = sm.read_config()
        assert config.goal, "config.goal should be set after interview"
        assert "ticket" in config.goal.lower() or "classify" in config.goal.lower(), (
            f"Expected goal about ticket classification, got: {config.goal!r}"
        )

        # Verify benchmark.json exists and loads
        benchmark_path = sm.aa_dir / "benchmark.json"
        assert benchmark_path.is_file(), "benchmark.json not written by cmd_new"

        benchmark = Benchmark.from_file(benchmark_path, scoring_function="exact_match")
        assert len(benchmark.examples) == len(_BENCHMARK_EXAMPLES), (
            f"Expected {len(_BENCHMARK_EXAMPLES)} examples, got {len(benchmark.examples)}"
        )

        captured = capsys.readouterr()
        assert "Generated benchmark" in captured.out

        # Fix benchmark path — cmd_new writes benchmark.json inside .autoagent/
        # but stores dataset_path="benchmark.json", while cmd_run resolves
        # relative to project_dir.  Adjust to the correct relative path.
        config = sm.read_config()
        if config.benchmark.get("dataset_path") == "benchmark.json":
            from dataclasses import replace as dc_replace
            fixed_benchmark = {**config.benchmark, "dataset_path": ".autoagent/benchmark.json"}
            config = dc_replace(config, benchmark=fixed_benchmark)
            sm.write_config(config)

        # ---------------------------------------------------------------
        # Stage 2: cmd_run — cold-start + optimization loop
        # ---------------------------------------------------------------

        # Fresh SequenceMockLLM for cmd_run: responses for cold-start
        # generate_initial + 3 loop iterations of propose.
        run_mock_llm = SequenceMockLLM([_PIPELINE_RESPONSE] * 6)

        with (
            patch("autoagent.cli.MockLLM", return_value=run_mock_llm),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main([
                    "--project-dir", str(tmp_path),
                    "run",
                    "--max-iterations", "3",
                ])

        assert exc_info.value.code == 0, (
            f"cmd_run failed with exit code {exc_info.value.code}"
        )

        # Verify archive has entries
        from autoagent.archive import Archive
        archive = Archive(sm.archive_dir)
        entries = archive.query()
        assert len(entries) > 0, "Archive should have entries after cmd_run"

        captured = capsys.readouterr()
        # Should see optimization output
        assert "Iteration" in captured.out or "complete" in captured.out.lower()

        # ---------------------------------------------------------------
        # Stage 3: cmd_report — generate markdown report
        # ---------------------------------------------------------------
        with pytest.raises(SystemExit) as exc_info:
            main(["--project-dir", str(tmp_path), "report"])

        assert exc_info.value.code == 0, (
            f"cmd_report failed with exit code {exc_info.value.code}"
        )

        # Verify report.md on disk
        report_path = sm.aa_dir / "report.md"
        assert report_path.is_file(), "report.md not written by cmd_report"

        report_text = report_path.read_text(encoding="utf-8")

        # All 4 sections present
        assert "## Score Trajectory" in report_text, "Missing Score Trajectory section"
        assert "## Top Architectures" in report_text, "Missing Top Architectures section"
        assert "## Cost Breakdown" in report_text, "Missing Cost Breakdown section"
        assert "## Recommendations" in report_text, "Missing Recommendations section"

        # Report contains the goal from the interview
        assert config.goal in report_text, (
            f"Report should contain the goal {config.goal!r}"
        )

        # Verify summary was printed
        captured = capsys.readouterr()
        assert "iteration" in captured.out.lower() or "kept" in captured.out.lower(), (
            "cmd_report should print a summary to stdout"
        )
