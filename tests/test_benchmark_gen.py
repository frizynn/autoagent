"""Tests for BenchmarkGenerator — JSON extraction, validation, retry, error handling."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from autoagent.benchmark import Benchmark
from autoagent.benchmark_gen import (
    BenchmarkGenerator,
    GenerationResult,
    ValidationResult,
    _extract_json,
)
from autoagent.interview import SequenceMockLLM
from autoagent.state import STARTER_PIPELINE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_examples(n: int = 5, prefix: str = "test") -> list[dict]:
    """Generate n simple benchmark examples as dicts."""
    return [
        {"input": f"{prefix}_input_{i}", "expected": f"{prefix}_output_{i}", "id": f"{prefix}_{i}"}
        for i in range(n)
    ]


def _examples_json(n: int = 5, prefix: str = "test") -> str:
    """Generate n examples as a JSON string."""
    return json.dumps(_make_examples(n, prefix))


# ---------------------------------------------------------------------------
# JSON extraction tests
# ---------------------------------------------------------------------------


class TestExtractJson:
    """Tests for _extract_json — the LLM response parser."""

    def test_bare_json_array(self):
        """Bare JSON array parses correctly."""
        raw = json.dumps([{"input": "a", "expected": "b", "id": "1"}])
        result = _extract_json(raw)
        assert len(result) == 1
        assert result[0]["input"] == "a"

    def test_fenced_json_block(self):
        """JSON inside ```json ... ``` fences is extracted."""
        examples = _make_examples(3)
        raw = f"Here are the examples:\n\n```json\n{json.dumps(examples)}\n```\n\nDone."
        result = _extract_json(raw)
        assert len(result) == 3
        assert result[0]["input"] == "test_input_0"

    def test_fenced_block_no_language_tag(self):
        """JSON inside ``` ... ``` fences (no language tag) is extracted."""
        examples = _make_examples(2)
        raw = f"Output:\n\n```\n{json.dumps(examples)}\n```"
        result = _extract_json(raw)
        assert len(result) == 2

    def test_prose_wrapped_json(self):
        """JSON array embedded in prose is extracted via bracket detection."""
        examples = _make_examples(2)
        raw = f"Here are the evaluation examples:\n\n{json.dumps(examples)}\n\nThese cover the basics."
        result = _extract_json(raw)
        assert len(result) == 2

    def test_invalid_json_raises(self):
        """Non-parseable response raises ValueError."""
        with pytest.raises(ValueError, match="Could not extract JSON"):
            _extract_json("This is not JSON at all.")

    def test_json_object_not_array_raises(self):
        """A single JSON object (not array) raises ValueError."""
        with pytest.raises(ValueError, match="Could not extract JSON"):
            _extract_json('{"input": "a", "expected": "b"}')

    def test_empty_array(self):
        """Empty JSON array parses to empty list."""
        result = _extract_json("[]")
        assert result == []


# ---------------------------------------------------------------------------
# BenchmarkGenerator happy path
# ---------------------------------------------------------------------------


class TestBenchmarkGeneratorHappyPath:
    """Tests for successful benchmark generation."""

    def test_generate_returns_success(self):
        """Happy path: valid JSON from LLM → successful GenerationResult."""
        examples = _make_examples(5)
        llm = SequenceMockLLM([json.dumps(examples)])
        gen = BenchmarkGenerator(llm=llm, goal="Translate English to French")

        result = gen.generate(num_examples=5)

        assert result.success is True
        assert result.error is None
        assert len(result.examples) == 5
        assert result.scoring_function == "includes"
        assert result.validation.passed is True

    def test_generate_with_sample_data(self):
        """Sample data is included in the prompt sent to the LLM."""
        examples = _make_examples(3)
        llm = SequenceMockLLM([json.dumps(examples)])
        gen = BenchmarkGenerator(
            llm=llm,
            goal="Summarize text",
            sample_data=["The cat sat on the mat.", "A quick brown fox."],
        )

        result = gen.generate(num_examples=3)

        assert result.success is True
        # Verify sample data appeared in the prompt
        assert "The cat sat on the mat." in llm.prompts[0]
        assert "A quick brown fox." in llm.prompts[0]

    def test_generate_assigns_default_ids(self):
        """Examples without IDs get gen_N identifiers."""
        examples = [{"input": f"in_{i}", "expected": f"out_{i}"} for i in range(3)]
        llm = SequenceMockLLM([json.dumps(examples)])
        gen = BenchmarkGenerator(llm=llm, goal="Test goal")

        result = gen.generate(num_examples=3)

        assert result.success is True
        assert result.examples[0]["id"] == "gen_0"
        assert result.examples[2]["id"] == "gen_2"

    def test_generation_result_fields(self):
        """GenerationResult exposes all expected fields."""
        vr = ValidationResult(
            leakage_blocked=False,
            baseline_scores_identical=False,
            diversity_ratio=1.0,
            passed=True,
            details="All validation checks passed",
        )
        gr = GenerationResult(
            examples=[{"input": "a", "expected": "b"}],
            scoring_function="includes",
            validation=vr,
            cost_usd=0.01,
            success=True,
            error=None,
        )
        assert gr.success is True
        assert gr.validation.passed is True
        assert gr.validation.diversity_ratio == 1.0


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for the validation pipeline."""

    def test_validation_passes_clean_examples(self):
        """Clean, diverse examples pass all validation checks."""
        examples = _make_examples(5)
        llm = SequenceMockLLM([json.dumps(examples)])
        gen = BenchmarkGenerator(llm=llm, goal="Test goal")

        result = gen.generate(num_examples=5)

        assert result.validation.passed is True
        assert result.validation.leakage_blocked is False
        assert result.validation.baseline_scores_identical is False
        assert result.validation.diversity_ratio == 1.0

    def test_leakage_detection_blocks(self):
        """Examples containing STARTER_PIPELINE string literals trigger leakage blocking."""
        # Use an actual string literal from STARTER_PIPELINE (the module docstring)
        leaked_literal = (
            "Starter pipeline — replace with your own logic.\n\n"
            "This file is loaded by PipelineRunner via compile()+exec().\n"
            "It must define a module-level ``run(input_data, primitives)`` function\n"
            "that returns a dict.\n"
        )
        examples = [
            {"input": leaked_literal, "expected": "some output", "id": "leak_0"},
            {"input": "normal_input_1", "expected": "normal_output_1", "id": "normal_1"},
            {"input": "normal_input_2", "expected": "normal_output_2", "id": "normal_2"},
            {"input": "normal_input_3", "expected": "normal_output_3", "id": "normal_3"},
            {"input": "normal_input_4", "expected": "normal_output_4", "id": "normal_4"},
        ]
        llm = SequenceMockLLM([json.dumps(examples)])
        gen = BenchmarkGenerator(llm=llm, goal="Test goal")

        result = gen.generate(num_examples=5)

        assert result.validation.leakage_blocked is True
        assert result.validation.passed is False
        assert "Leakage" in (result.error or "")

    def test_diversity_check_fails_on_duplicates(self):
        """Duplicate inputs trigger diversity failure."""
        # All same input → diversity_ratio = 1/5 = 0.2
        examples = [
            {"input": "same_input", "expected": f"output_{i}", "id": f"dup_{i}"}
            for i in range(5)
        ]
        llm = SequenceMockLLM([json.dumps(examples)])
        gen = BenchmarkGenerator(llm=llm, goal="Test goal")

        result = gen.generate(num_examples=5)

        assert result.validation.baseline_scores_identical is True
        assert result.validation.diversity_ratio == pytest.approx(0.2)
        assert result.validation.passed is False
        assert "diversity" in (result.error or "").lower()

    def test_diversity_check_passes_at_threshold(self):
        """Exactly 80% unique inputs passes the diversity check."""
        # 4 unique out of 5 = 0.8
        examples = [
            {"input": f"unique_{i}", "expected": f"out_{i}", "id": f"ex_{i}"}
            for i in range(4)
        ]
        examples.append({"input": "unique_0", "expected": "out_dup", "id": "ex_4"})
        llm = SequenceMockLLM([json.dumps(examples)])
        gen = BenchmarkGenerator(llm=llm, goal="Test goal")

        result = gen.generate(num_examples=5)

        assert result.validation.diversity_ratio == pytest.approx(0.8)
        assert result.validation.baseline_scores_identical is False


# ---------------------------------------------------------------------------
# Retry logic tests
# ---------------------------------------------------------------------------


class TestRetryLogic:
    """Tests for JSON parse retry on malformed responses."""

    def test_retry_on_malformed_json_succeeds(self):
        """First response is garbage, second is valid → success."""
        examples = _make_examples(3)
        llm = SequenceMockLLM([
            "Sorry, here is some text that is not JSON",
            json.dumps(examples),
        ])
        gen = BenchmarkGenerator(llm=llm, goal="Test retry")

        result = gen.generate(num_examples=3)

        assert result.success is True
        assert llm.call_count == 2
        # Second prompt should be the retry instruction
        assert "valid JSON" in llm.prompts[1]

    def test_retry_exhausted_returns_error(self):
        """Both attempts return garbage → error result."""
        llm = SequenceMockLLM([
            "This is not JSON",
            "Still not JSON",
        ])
        gen = BenchmarkGenerator(llm=llm, goal="Test retry exhaustion")

        result = gen.generate(num_examples=3)

        assert result.success is False
        assert result.error is not None
        assert "failed after 2 attempts" in result.error.lower()
        assert result.examples == []

    def test_no_retry_on_valid_first_response(self):
        """Valid first response → only 1 LLM call."""
        examples = _make_examples(3)
        llm = SequenceMockLLM([json.dumps(examples)])
        gen = BenchmarkGenerator(llm=llm, goal="Test single call")

        result = gen.generate(num_examples=3)

        assert result.success is True
        assert llm.call_count == 1


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error result construction."""

    def test_missing_keys_returns_error(self):
        """Examples missing 'input' or 'expected' produce error result."""
        bad_examples = [{"input": "a"}, {"input": "b", "expected": "c"}]
        llm = SequenceMockLLM([json.dumps(bad_examples)])
        gen = BenchmarkGenerator(llm=llm, goal="Test missing keys")

        result = gen.generate(num_examples=2)

        assert result.success is False
        assert "missing required keys" in (result.error or "").lower()

    def test_error_result_structure(self):
        """Failed result has success=False, error string, empty examples."""
        llm = SequenceMockLLM(["not json"])
        gen = BenchmarkGenerator(llm=llm, goal="Test error structure")

        result = gen.generate(num_examples=3)

        assert result.success is False
        assert result.error is not None
        assert isinstance(result.error, str)
        assert result.examples == []
        assert result.scoring_function == "includes"


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Tests for Benchmark.from_file() compatibility."""

    def test_generated_examples_roundtrip_through_file(self):
        """Generated examples can be written to JSON and loaded via Benchmark.from_file()."""
        examples = _make_examples(5)
        llm = SequenceMockLLM([json.dumps(examples)])
        gen = BenchmarkGenerator(llm=llm, goal="Test round-trip")

        result = gen.generate(num_examples=5)
        assert result.success is True

        # Write to temp file and load
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(result.examples, f)
            temp_path = f.name

        try:
            loaded = Benchmark.from_file(temp_path, scoring_function="includes")
            assert len(loaded.examples) == 5
            assert loaded.examples[0].input == "test_input_0"
            assert loaded.examples[0].expected == "test_output_0"
            assert loaded.examples[0].id == "test_0"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_roundtrip_preserves_all_fields(self):
        """Round-trip preserves input, expected, and id for all examples."""
        examples = [
            {"input": "Hello world", "expected": "Bonjour le monde", "id": "greeting"},
            {"input": "How are you?", "expected": "Comment allez-vous?", "id": "question"},
        ]
        llm = SequenceMockLLM([json.dumps(examples)])
        gen = BenchmarkGenerator(llm=llm, goal="Translate English to French")

        result = gen.generate(num_examples=2)
        assert result.success is True

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(result.examples, f)
            temp_path = f.name

        try:
            loaded = Benchmark.from_file(temp_path, scoring_function="includes")
            assert loaded.examples[0].input == "Hello world"
            assert loaded.examples[0].expected == "Bonjour le monde"
            assert loaded.examples[0].id == "greeting"
            assert loaded.examples[1].input == "How are you?"
            assert loaded.examples[1].expected == "Comment allez-vous?"
            assert loaded.examples[1].id == "question"
        finally:
            Path(temp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Import verification
# ---------------------------------------------------------------------------


class TestImports:
    """Verify public API is importable."""

    def test_import_generator_and_result(self):
        """Public types are importable from benchmark_gen module."""
        from autoagent.benchmark_gen import BenchmarkGenerator, GenerationResult

        assert BenchmarkGenerator is not None
        assert GenerationResult is not None

    def test_import_validation_result(self):
        """ValidationResult is importable."""
        from autoagent.benchmark_gen import ValidationResult

        assert ValidationResult is not None
