"""Unit tests for LeakageChecker and LeakageResult."""

from __future__ import annotations

import pytest

from autoagent.benchmark import Benchmark, BenchmarkExample, _exact_match
from autoagent.leakage import (
    LeakageChecker,
    LeakageResult,
    _combined_ngrams,
    _extract_string_literals_ast,
    _extract_string_literals_regex,
    _jaccard,
    _tokenize,
)


def _make_benchmark(examples: list[BenchmarkExample]) -> Benchmark:
    """Helper to create a Benchmark with exact_match scorer."""
    return Benchmark(
        examples=examples,
        scorer=_exact_match,
        source_path="test.json",
        scoring_function_name="exact_match",
    )


# ---------------------------------------------------------------------------
# LeakageResult basics
# ---------------------------------------------------------------------------


class TestLeakageResult:
    def test_frozen(self) -> None:
        result = LeakageResult(blocked=False)
        with pytest.raises(AttributeError):
            result.blocked = True  # type: ignore[misc]

    def test_defaults(self) -> None:
        result = LeakageResult(blocked=False)
        assert result.exact_matches == 0
        assert result.fuzzy_warnings == []
        assert result.cost_usd == 0.0


# ---------------------------------------------------------------------------
# Exact match detection
# ---------------------------------------------------------------------------


class TestExactMatch:
    def test_exact_match_blocks(self) -> None:
        """Pipeline contains a benchmark example verbatim → blocked."""
        benchmark = _make_benchmark([
            BenchmarkExample(
                input="What is the capital of France?",
                expected="Paris",
                id="q1",
            ),
        ])
        # Pipeline embeds the exact input string as a literal
        source = '''
def run(input_data, primitives=None):
    answers = {"What is the capital of France?": "Paris"}
    return answers.get(input_data, "unknown")
'''
        checker = LeakageChecker()
        result = checker.check(benchmark, source)
        assert result.blocked is True
        assert result.exact_matches >= 1

    def test_no_match_passes(self) -> None:
        """Clean pipeline → no blocking, no warnings."""
        benchmark = _make_benchmark([
            BenchmarkExample(
                input="What is the capital of France?",
                expected="Paris",
                id="q1",
            ),
        ])
        source = '''
def run(input_data, primitives=None):
    return primitives.complete(f"Answer: {input_data}")
'''
        checker = LeakageChecker()
        result = checker.check(benchmark, source)
        assert result.blocked is False
        assert result.exact_matches == 0
        assert result.fuzzy_warnings == []

    def test_multiple_exact_matches(self) -> None:
        """Multiple benchmark examples embedded → exact_matches counts correctly."""
        benchmark = _make_benchmark([
            BenchmarkExample(
                input="What is the capital of France?",
                expected="Paris",
                id="q1",
            ),
            BenchmarkExample(
                input="What is the capital of Germany?",
                expected="Berlin",
                id="q2",
            ),
        ])
        source = '''
def run(input_data, primitives=None):
    lookup = {
        "What is the capital of France?": "Paris",
        "What is the capital of Germany?": "Berlin",
    }
    return lookup.get(input_data, "unknown")
'''
        checker = LeakageChecker()
        result = checker.check(benchmark, source)
        assert result.blocked is True
        assert result.exact_matches == 2


# ---------------------------------------------------------------------------
# Short example skip
# ---------------------------------------------------------------------------


class TestShortExampleSkip:
    def test_short_examples_not_flagged(self) -> None:
        """Short examples (both input and expected < 10 chars) are skipped."""
        benchmark = _make_benchmark([
            BenchmarkExample(input="hi", expected="hey", id="short1"),
        ])
        # Pipeline contains the short strings, but they should be skipped
        source = '''
def run(input_data, primitives=None):
    if input_data == "hi":
        return "hey"
    return "hello"
'''
        checker = LeakageChecker()
        result = checker.check(benchmark, source)
        assert result.blocked is False
        assert result.exact_matches == 0

    def test_one_long_value_still_checked(self) -> None:
        """If input is short but expected is long, example is still checked."""
        benchmark = _make_benchmark([
            BenchmarkExample(
                input="q",
                expected="This is a really long expected answer that should be checked",
                id="mixed1",
            ),
        ])
        source = '''
def run(input_data, primitives=None):
    return "This is a really long expected answer that should be checked"
'''
        checker = LeakageChecker()
        result = checker.check(benchmark, source)
        assert result.blocked is True
        assert result.exact_matches >= 1


# ---------------------------------------------------------------------------
# Non-string data
# ---------------------------------------------------------------------------


class TestNonStringData:
    def test_dict_input_serialized(self) -> None:
        """Dict/list benchmark data is serialized via json.dumps and checked."""
        data_input = {"question": "What is 2+2?", "context": "math"}
        benchmark = _make_benchmark([
            BenchmarkExample(input=data_input, expected="4", id="dict1"),
        ])
        # Pipeline embeds the JSON-serialized form
        import json

        serialized = json.dumps(data_input, sort_keys=True)
        source = f'''
def run(input_data, primitives=None):
    hardcoded = '{serialized}'
    return "4"
'''
        checker = LeakageChecker()
        result = checker.check(benchmark, source)
        assert result.blocked is True
        assert result.exact_matches >= 1

    def test_list_input_serialized(self) -> None:
        """List benchmark data is serialized and checked."""
        data_input = ["What is 2+2?", "math context here"]
        benchmark = _make_benchmark([
            BenchmarkExample(input=data_input, expected="4", id="list1"),
        ])
        import json

        serialized = json.dumps(data_input, sort_keys=True)
        source = f'''
def run(input_data, primitives=None):
    data = '{serialized}'
    return "4"
'''
        checker = LeakageChecker()
        result = checker.check(benchmark, source)
        assert result.blocked is True


# ---------------------------------------------------------------------------
# Fuzzy n-gram overlap
# ---------------------------------------------------------------------------


class TestFuzzyOverlap:
    def test_high_overlap_warns(self) -> None:
        """Pipeline sharing significant vocabulary triggers fuzzy warnings."""
        benchmark = _make_benchmark([
            BenchmarkExample(
                input="The quick brown fox jumps over the lazy dog near the river",
                expected="Yes, the fox jumped over the lazy dog by the river bank",
                id="overlap1",
            ),
        ])
        # Pipeline source reuses a lot of the same vocabulary
        source = '''
def run(input_data, primitives=None):
    # the quick brown fox jumps over the lazy dog near the river
    # the fox jumped over the lazy dog by the river bank
    context = "the quick brown fox jumps over the lazy dog near the river bank"
    return primitives.complete(f"{context} {input_data}")
'''
        checker = LeakageChecker(fuzzy_threshold=0.1)  # low threshold
        result = checker.check(benchmark, source)
        assert result.blocked is False  # Fuzzy never blocks
        assert len(result.fuzzy_warnings) > 0

    def test_no_overlap_no_warning(self) -> None:
        """Completely different vocabulary → no fuzzy warnings."""
        benchmark = _make_benchmark([
            BenchmarkExample(
                input="What is the capital of France?",
                expected="Paris is the capital",
                id="q1",
            ),
        ])
        source = '''
def run(input_data, primitives=None):
    system_prompt = "You are a helpful coding assistant for Python programs"
    return primitives.complete(f"{system_prompt}\\n{input_data}")
'''
        checker = LeakageChecker()
        result = checker.check(benchmark, source)
        assert result.fuzzy_warnings == []


# ---------------------------------------------------------------------------
# AST failure fallback
# ---------------------------------------------------------------------------


class TestASTFallback:
    def test_syntax_error_falls_back_to_regex(self) -> None:
        """Pipeline with syntax errors still detects embedded strings via regex."""
        benchmark = _make_benchmark([
            BenchmarkExample(
                input="What is the capital of France?",
                expected="Paris",
                id="q1",
            ),
        ])
        # Invalid Python but contains the target string
        source = '''
def run(input_data primitives=None):  # missing comma = SyntaxError
    answers = {"What is the capital of France?": "Paris"}
    return answers.get(input_data)
'''
        checker = LeakageChecker()
        result = checker.check(benchmark, source)
        assert result.blocked is True
        assert result.exact_matches >= 1


# ---------------------------------------------------------------------------
# Empty benchmark
# ---------------------------------------------------------------------------


class TestEmptyBenchmark:
    def test_empty_benchmark_passes(self) -> None:
        """Benchmark with no examples → clean pass."""
        benchmark = _make_benchmark([])
        source = '''
def run(input_data, primitives=None):
    return "hello"
'''
        checker = LeakageChecker()
        result = checker.check(benchmark, source)
        assert result.blocked is False
        assert result.exact_matches == 0
        assert result.fuzzy_warnings == []


# ---------------------------------------------------------------------------
# cost_usd
# ---------------------------------------------------------------------------


class TestCostTracking:
    def test_cost_always_zero(self) -> None:
        """cost_usd is 0.0 for mechanical checks."""
        benchmark = _make_benchmark([
            BenchmarkExample(
                input="What is the capital of France?",
                expected="Paris",
                id="q1",
            ),
        ])
        source = 'def run(input_data, primitives=None): return "hello"'
        checker = LeakageChecker()
        result = checker.check(benchmark, source)
        assert result.cost_usd == 0.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_tokenize(self) -> None:
        assert _tokenize("Hello, World! 123") == ["hello", "world", "123"]

    def test_ngrams(self) -> None:
        tokens = ["a", "b", "c", "d"]
        grams = _combined_ngrams(tokens)
        assert ("a", "b", "c") in grams
        assert ("b", "c", "d") in grams
        assert ("a", "b", "c", "d") in grams

    def test_jaccard_identical(self) -> None:
        s = {(1, 2, 3)}
        assert _jaccard(s, s) == 1.0

    def test_jaccard_disjoint(self) -> None:
        assert _jaccard({(1,)}, {(2,)}) == 0.0

    def test_jaccard_empty(self) -> None:
        assert _jaccard(set(), set()) == 0.0

    def test_ast_extraction(self) -> None:
        source = 'x = "hello"\ny = \'world\''
        literals = _extract_string_literals_ast(source)
        assert "hello" in literals
        assert "world" in literals

    def test_regex_extraction(self) -> None:
        source = 'x = "hello"\ny = \'world\''
        literals = _extract_string_literals_regex(source)
        assert "hello" in literals
        assert "world" in literals
