"""Tests for autoagent.benchmark — loading, scoring, and error handling."""

import json
import pytest
from pathlib import Path

from autoagent.benchmark import (
    Benchmark,
    BenchmarkExample,
    ScoringResult,
    BUILT_IN_SCORERS,
    _exact_match,
    _includes,
)


FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Built-in scorer tests
# ---------------------------------------------------------------------------


class TestExactMatch:
    def test_equal_strings(self):
        result = _exact_match("hello", "hello")
        assert result.score == 1.0
        assert result.error is None

    def test_different_strings(self):
        result = _exact_match("hello", "world")
        assert result.score == 0.0

    def test_stringifies_non_strings(self):
        result = _exact_match(42, "42")
        assert result.score == 1.0

    def test_dict_vs_string(self):
        d = {"key": "value"}
        result = _exact_match(d, str(d))
        assert result.score == 1.0


class TestIncludes:
    def test_substring_present(self):
        result = _includes("hello world", "world")
        assert result.score == 1.0

    def test_substring_absent(self):
        result = _includes("hello world", "xyz")
        assert result.score == 0.0

    def test_stringifies_non_strings(self):
        result = _includes({"answer": "mock"}, "mock")
        assert result.score == 1.0

    def test_exact_match_is_also_includes(self):
        result = _includes("abc", "abc")
        assert result.score == 1.0


# ---------------------------------------------------------------------------
# Benchmark.from_file tests
# ---------------------------------------------------------------------------


class TestBenchmarkFromFile:
    def test_loads_toy_benchmark(self):
        bm = Benchmark.from_file(FIXTURES / "toy_benchmark.json")
        assert len(bm.examples) == 5
        assert all(isinstance(e, BenchmarkExample) for e in bm.examples)
        assert bm.examples[0].id == "ex_match_1"
        assert bm.examples[0].input == "test query 1"
        assert bm.scoring_function_name == "exact_match"

    def test_default_scorer_is_exact_match(self):
        bm = Benchmark.from_file(FIXTURES / "toy_benchmark.json")
        assert bm.scorer is BUILT_IN_SCORERS["exact_match"]

    def test_includes_scorer(self):
        bm = Benchmark.from_file(FIXTURES / "toy_benchmark.json", scoring_function="includes")
        assert bm.scorer is BUILT_IN_SCORERS["includes"]

    def test_auto_generates_ids_when_missing(self, tmp_path):
        data = [{"input": "a", "expected": "b"}, {"input": "c", "expected": "d"}]
        p = tmp_path / "bench.json"
        p.write_text(json.dumps(data))
        bm = Benchmark.from_file(p)
        assert bm.examples[0].id == "example_0"
        assert bm.examples[1].id == "example_1"

    def test_custom_scorer_file(self):
        scorer_path = str(FIXTURES / "toy_scorer.py")
        bm = Benchmark.from_file(FIXTURES / "toy_benchmark.json", scoring_function=scorer_path)
        # The loaded scorer should work
        result = bm.scorer("Hello World", "hello")
        assert result.score == 1.0
        result2 = bm.scorer("abc", "xyz")
        assert result2.score == 0.0


class TestBenchmarkErrors:
    def test_missing_file(self):
        with pytest.raises(FileNotFoundError, match="Benchmark file not found"):
            Benchmark.from_file("/nonexistent/path.json")

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json {{{")
        with pytest.raises(ValueError, match="Invalid JSON"):
            Benchmark.from_file(p)

    def test_json_not_array(self, tmp_path):
        p = tmp_path / "obj.json"
        p.write_text('{"key": "value"}')
        with pytest.raises(ValueError, match="must be an array"):
            Benchmark.from_file(p)

    def test_example_missing_keys(self, tmp_path):
        p = tmp_path / "missing.json"
        p.write_text('[{"input": "x"}]')
        with pytest.raises(ValueError, match="'input' and 'expected'"):
            Benchmark.from_file(p)

    def test_unknown_scorer_name(self):
        with pytest.raises(ValueError, match="Unknown scoring function"):
            Benchmark.from_file(FIXTURES / "toy_benchmark.json", scoring_function="nonexistent")

    def test_missing_scorer_file(self):
        with pytest.raises(FileNotFoundError, match="Custom scorer file not found"):
            Benchmark.from_file(
                FIXTURES / "toy_benchmark.json",
                scoring_function="/tmp/does_not_exist.py",
            )


# ---------------------------------------------------------------------------
# Benchmark.describe() tests
# ---------------------------------------------------------------------------


class TestBenchmarkDescribe:
    def _make_benchmark(self, n: int = 5) -> Benchmark:
        """Create a Benchmark with *n* examples for describe() testing."""
        examples = [
            BenchmarkExample(input=f"q{i}", expected=f"a{i}", id=f"ex_{i}")
            for i in range(n)
        ]
        return Benchmark(
            examples=examples,
            scorer=BUILT_IN_SCORERS["exact_match"],
            scoring_function_name="exact_match",
        )

    def test_describe_includes_scorer_name(self):
        bm = self._make_benchmark()
        desc = bm.describe()
        assert "exact_match" in desc

    def test_describe_includes_total_count(self):
        bm = self._make_benchmark(10)
        desc = bm.describe()
        assert "10 examples" in desc

    def test_describe_samples_max_examples(self):
        bm = self._make_benchmark(10)
        desc = bm.describe(max_examples=3)
        assert "3 of 10" in desc
        # Should contain first 3 examples
        assert "q0" in desc
        assert "q2" in desc
        # Should NOT contain 4th example input
        assert "q3" not in desc

    def test_describe_fewer_than_max(self):
        bm = self._make_benchmark(2)
        desc = bm.describe(max_examples=5)
        assert "2 of 2" in desc
        assert "q0" in desc
        assert "q1" in desc

    def test_describe_output_under_2k_chars(self):
        bm = self._make_benchmark(100)
        desc = bm.describe(max_examples=3)
        assert isinstance(desc, str)
        assert len(desc) > 0
        assert len(desc) < 2000

    def test_describe_with_dict_inputs(self):
        examples = [
            BenchmarkExample(
                input={"question": "What is 2+2?", "context": "Math"},
                expected={"answer": "4"},
                id="dict_ex",
            )
        ]
        bm = Benchmark(
            examples=examples,
            scorer=BUILT_IN_SCORERS["exact_match"],
            scoring_function_name="exact_match",
        )
        desc = bm.describe()
        assert "question" in desc
        assert "What is 2+2?" in desc
