"""BenchmarkGenerator — produces evaluation benchmarks from goal descriptions via LLM.

Takes a goal string, optional sample data, and an LLMProtocol instance.
Prompts the LLM to generate {input, expected, id} examples as JSON,
parses the response (handling markdown fences and prose wrapping),
validates via leakage checking and input diversity, and returns a
structured GenerationResult.
"""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from autoagent.benchmark import Benchmark
from autoagent.leakage import LeakageChecker
from autoagent.primitives import LLMProtocol
from autoagent.state import STARTER_PIPELINE


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of benchmark validation checks.

    Fields:
        leakage_blocked: True if leakage checker found exact matches in STARTER_PIPELINE.
        baseline_scores_identical: True if all generated inputs are identical (no discriminating power).
        diversity_ratio: Fraction of unique inputs over total examples.
        passed: True if all validation gates passed.
        details: Human-readable summary of validation outcome.
    """

    leakage_blocked: bool = False
    baseline_scores_identical: bool = False
    diversity_ratio: float = 1.0
    passed: bool = True
    details: str = ""


@dataclass(frozen=True)
class GenerationResult:
    """Outcome of BenchmarkGenerator.generate().

    Fields:
        examples: List of {input, expected, id} dicts on success; empty on failure.
        scoring_function: Name of the scoring function for the generated benchmark.
        validation: Structured validation result with leakage/diversity/format details.
        cost_usd: Estimated LLM cost for generation (0.0 if not tracked).
        success: True if generation + validation passed.
        error: Structured error string on failure; None on success.
    """

    examples: list[dict[str, Any]] = field(default_factory=list)
    scoring_function: str = "includes"
    validation: ValidationResult = field(default_factory=ValidationResult)
    cost_usd: float = 0.0
    success: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# JSON extraction from LLM responses
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n(.*?)```",
    re.DOTALL,
)


def _extract_json(response: str) -> list[dict[str, Any]]:
    """Extract a JSON array of objects from an LLM response.

    Handles:
    - Markdown fenced blocks (```json ... ``` or ``` ... ```)
    - Bare JSON arrays
    - Prose-wrapped JSON (strips non-JSON text)

    Raises ValueError if no valid JSON array can be extracted.
    """
    # Try fenced blocks first
    fence_match = _JSON_FENCE_RE.search(response)
    if fence_match:
        block = fence_match.group(1).strip()
        try:
            data = json.loads(block)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    # Try parsing the full response as JSON
    stripped = response.strip()
    try:
        data = json.loads(stripped)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Try to find a JSON array in the response by locating [ ... ]
    bracket_start = stripped.find("[")
    bracket_end = stripped.rfind("]")
    if bracket_start != -1 and bracket_end > bracket_start:
        candidate = stripped[bracket_start : bracket_end + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Could not extract JSON array from LLM response ({len(response)} chars). "
        f"Response starts with: {response[:120]!r}"
    )


# ---------------------------------------------------------------------------
# BenchmarkGenerator
# ---------------------------------------------------------------------------


class BenchmarkGenerator:
    """Generates evaluation benchmarks from goal descriptions via LLM.

    Args:
        llm: LLMProtocol instance for generating examples.
        goal: The optimization goal description.
        sample_data: Optional list of sample data strings to include as context.
    """

    MAX_ATTEMPTS = 2

    def __init__(
        self,
        llm: LLMProtocol,
        goal: str,
        sample_data: list[str] | None = None,
    ) -> None:
        self.llm = llm
        self.goal = goal
        self.sample_data = sample_data

    def generate(self, num_examples: int = 10) -> GenerationResult:
        """Generate a benchmark with validation.

        Makes up to MAX_ATTEMPTS LLM calls to produce valid JSON examples.
        Validates the result for leakage, diversity, and format compatibility.

        Returns a GenerationResult with success=True on valid generation,
        or success=False with error details on failure.
        """
        prompt = self._build_prompt(num_examples)
        cost_usd = 0.0
        examples: list[dict[str, Any]] | None = None
        last_error: str | None = None

        for attempt in range(self.MAX_ATTEMPTS):
            if attempt == 0:
                response = self.llm.complete(prompt)
            else:
                # Retry with explicit JSON-only instruction
                retry_prompt = (
                    "Your previous response could not be parsed as valid JSON. "
                    "Please output ONLY a valid JSON array of objects with "
                    '"input", "expected", and "id" keys. '
                    "No markdown fences, no explanation, just the JSON array."
                )
                response = self.llm.complete(retry_prompt)

            try:
                examples = _extract_json(response)
                last_error = None
                break
            except ValueError as exc:
                last_error = f"Attempt {attempt + 1}: {exc}"
                examples = None

        if examples is None:
            return GenerationResult(
                cost_usd=cost_usd,
                error=f"JSON extraction failed after {self.MAX_ATTEMPTS} attempts. {last_error}",
            )

        # Validate required keys and normalize
        for i, ex in enumerate(examples):
            if not isinstance(ex, dict) or "input" not in ex or "expected" not in ex:
                return GenerationResult(
                    cost_usd=cost_usd,
                    error=f"Example {i} missing required keys 'input' and 'expected': {ex!r}",
                )
            if "id" not in ex:
                ex["id"] = f"gen_{i}"

        # Run validation
        validation = self._validate(examples)

        if not validation.passed:
            return GenerationResult(
                examples=examples,
                validation=validation,
                cost_usd=cost_usd,
                error=f"Validation failed: {validation.details}",
            )

        return GenerationResult(
            examples=examples,
            scoring_function="includes",
            validation=validation,
            cost_usd=cost_usd,
            success=True,
        )

    def _build_prompt(self, num_examples: int) -> str:
        """Build the generation prompt following meta_agent.py section pattern."""
        sections: list[str] = []

        # Section 1: Task
        sections.append(
            "## Task\n\n"
            f"Generate exactly {num_examples} evaluation examples for the following goal. "
            "Each example must be a JSON object with three keys:\n"
            '- "input": the test input (string or structured data)\n'
            '- "expected": the expected correct output (must differ from input)\n'
            '- "id": a short descriptive identifier for the example\n\n'
            "Output a JSON array of these objects. No markdown fences, no explanation — "
            "just the raw JSON array."
        )

        # Section 2: Goal
        sections.append(f"## Goal\n\n{self.goal}")

        # Section 3: Sample data (optional)
        if self.sample_data:
            sample_text = "\n".join(f"- {s}" for s in self.sample_data)
            sections.append(
                f"## Sample Data\n\n"
                f"Use these as reference for the kind of data the pipeline processes:\n\n"
                f"{sample_text}"
            )

        # Section 4: Constraints
        sections.append(
            "## Constraints\n\n"
            "1. The expected output must DIFFER from the input in every example.\n"
            "2. Each input should be unique — avoid duplicate or near-duplicate inputs.\n"
            "3. Examples should be realistic and representative of the goal.\n"
            "4. IDs should be short, descriptive, and unique (e.g., 'simple_greeting', 'edge_case_empty').\n"
            "5. Output ONLY the JSON array — no surrounding text."
        )

        return "\n\n".join(sections)

    def _validate(self, examples: list[dict[str, Any]]) -> ValidationResult:
        """Run validation checks on generated examples.

        Checks:
        1. Leakage: examples shouldn't contain STARTER_PIPELINE literals
        2. Diversity: unique inputs >= 80% of total
        3. Format: required keys present
        4. Round-trip: examples load via Benchmark.from_file()
        """
        issues: list[str] = []

        # Check required keys
        for i, ex in enumerate(examples):
            if "input" not in ex or "expected" not in ex:
                issues.append(f"Example {i} missing required keys")

        if issues:
            return ValidationResult(
                passed=False,
                details="; ".join(issues),
            )

        # Build a Benchmark for leakage checking
        benchmark = Benchmark.from_file.__func__  # type: ignore[attr-defined]
        # Construct Benchmark directly to avoid file I/O for leakage check
        from autoagent.benchmark import BenchmarkExample

        benchmark_examples = [
            BenchmarkExample(
                input=ex["input"],
                expected=ex["expected"],
                id=ex.get("id", f"gen_{i}"),
            )
            for i, ex in enumerate(examples)
        ]
        benchmark_obj = Benchmark(
            examples=benchmark_examples,
            scorer=lambda o, e: None,  # Not used for leakage check
            scoring_function_name="includes",
        )

        # Leakage check against STARTER_PIPELINE
        checker = LeakageChecker()
        leakage_result = checker.check(benchmark_obj, STARTER_PIPELINE)
        leakage_blocked = leakage_result.blocked

        if leakage_blocked:
            issues.append(
                f"Leakage detected: {leakage_result.exact_matches} exact matches "
                f"with STARTER_PIPELINE source"
            )

        # Diversity check
        unique_inputs = len(set(str(ex["input"]) for ex in examples))
        diversity_ratio = unique_inputs / len(examples) if examples else 0.0
        baseline_scores_identical = diversity_ratio < 0.8

        if baseline_scores_identical:
            issues.append(
                f"Low input diversity: {diversity_ratio:.2f} "
                f"(need >= 0.80, got {unique_inputs}/{len(examples)} unique)"
            )

        # Round-trip check: write to temp file, load via Benchmark.from_file()
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as f:
                json.dump(examples, f)
                temp_path = f.name

            loaded = Benchmark.from_file(temp_path, scoring_function="includes")
            if len(loaded.examples) != len(examples):
                issues.append(
                    f"Round-trip mismatch: wrote {len(examples)}, loaded {len(loaded.examples)}"
                )
        except Exception as exc:
            issues.append(f"Round-trip failed: {exc}")
        finally:
            Path(temp_path).unlink(missing_ok=True)

        passed = not issues
        details = "; ".join(issues) if issues else "All validation checks passed"

        return ValidationResult(
            leakage_blocked=leakage_blocked,
            baseline_scores_identical=baseline_scores_identical,
            diversity_ratio=diversity_ratio,
            passed=passed,
            details=details,
        )
