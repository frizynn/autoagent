"""Tests for the evaluation harness."""

from __future__ import annotations

import textwrap
from pathlib import Path

from autoagent.harness import evaluate, TEST_CASES


class TestEvaluate:
    def test_perfect_score(self, tmp_path: Path) -> None:
        """A pipeline that uppercases correctly scores 1.0."""
        pipeline = tmp_path / "pipeline.py"
        pipeline.write_text(textwrap.dedent('''
            def run(input_data, context=None):
                return {"output": input_data.upper()}
        '''))
        result = evaluate(str(pipeline))
        assert result["score"] == 1.0
        assert result["passed"] == len(TEST_CASES)
        assert result["failed"] == 0

    def test_baseline_scores_partial(self, tmp_path: Path) -> None:
        """The baseline (echo) pipeline scores > 0 but < 1."""
        pipeline = tmp_path / "pipeline.py"
        pipeline.write_text(textwrap.dedent('''
            def run(input_data, context=None):
                return {"output": input_data}
        '''))
        result = evaluate(str(pipeline))
        # Some test cases are already uppercase or empty, so score > 0
        assert 0.0 < result["score"] < 1.0

    def test_zero_score(self, tmp_path: Path) -> None:
        """A pipeline that returns wrong output scores 0."""
        pipeline = tmp_path / "pipeline.py"
        pipeline.write_text(textwrap.dedent('''
            def run(input_data, context=None):
                return {"output": "WRONG"}
        '''))
        result = evaluate(str(pipeline))
        assert result["score"] < 0.5  # Most will be wrong

    def test_crash_counts_as_failure(self, tmp_path: Path) -> None:
        """A pipeline that raises scores failures, not crashes."""
        pipeline = tmp_path / "pipeline.py"
        pipeline.write_text(textwrap.dedent('''
            def run(input_data, context=None):
                raise ValueError("boom")
        '''))
        result = evaluate(str(pipeline))
        assert result["score"] == 0.0
        assert result["failed"] == len(TEST_CASES)

    def test_result_has_required_fields(self, tmp_path: Path) -> None:
        """Result dict has all required fields."""
        pipeline = tmp_path / "pipeline.py"
        pipeline.write_text(textwrap.dedent('''
            def run(input_data, context=None):
                return {"output": input_data}
        '''))
        result = evaluate(str(pipeline))
        assert "score" in result
        assert "total_examples" in result
        assert "passed" in result
        assert "failed" in result
        assert "duration_ms" in result

    def test_string_return_accepted(self, tmp_path: Path) -> None:
        """Pipeline returning a raw string (not dict) is accepted."""
        pipeline = tmp_path / "pipeline.py"
        pipeline.write_text(textwrap.dedent('''
            def run(input_data, context=None):
                return input_data.upper()
        '''))
        result = evaluate(str(pipeline))
        assert result["score"] == 1.0
