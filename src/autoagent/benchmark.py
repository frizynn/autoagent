"""Benchmark loading and scoring for AutoAgent evaluation."""

from __future__ import annotations

import importlib.util
import json
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class BenchmarkExample:
    """Single benchmark example with input, expected output, and identifier."""

    input: Any
    expected: Any
    id: str = ""


@dataclass(frozen=True)
class ScoringResult:
    """Result of scoring a single example."""

    score: float
    error: str | None = None


# ---------------------------------------------------------------------------
# Built-in scorers
# ---------------------------------------------------------------------------

def _exact_match(output: Any, expected: Any) -> ScoringResult:
    """Score 1.0 if str(output) == str(expected), else 0.0."""
    return ScoringResult(score=1.0 if str(output) == str(expected) else 0.0)


def _includes(output: Any, expected: Any) -> ScoringResult:
    """Score 1.0 if str(expected) is a substring of str(output), else 0.0."""
    return ScoringResult(score=1.0 if str(expected) in str(output) else 0.0)


ScorerFn = Callable[[Any, Any], ScoringResult]

BUILT_IN_SCORERS: dict[str, ScorerFn] = {
    "exact_match": _exact_match,
    "includes": _includes,
}


# ---------------------------------------------------------------------------
# Benchmark class
# ---------------------------------------------------------------------------

class Benchmark:
    """A benchmark dataset with associated scoring function.

    Load from a JSON file containing an array of ``{"input": ..., "expected": ...}``
    objects. Optionally each object can have an ``"id"`` field; otherwise IDs are
    generated as ``"example_0"``, ``"example_1"``, etc.

    The scoring function is resolved from either:
    - A built-in name (``"exact_match"``, ``"includes"``)
    - A path to a ``.py`` file exporting a ``score(output, expected) -> ScoringResult`` function
    """

    def __init__(
        self,
        examples: list[BenchmarkExample],
        scorer: ScorerFn,
        source_path: str = "",
        scoring_function_name: str = "",
    ) -> None:
        self.examples = examples
        self.scorer = scorer
        self.source_path = source_path
        self.scoring_function_name = scoring_function_name

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        scoring_function: str = "exact_match",
    ) -> Benchmark:
        """Load a benchmark from a JSON file and resolve the scoring function.

        Parameters
        ----------
        path:
            Path to a JSON file containing an array of example objects.
        scoring_function:
            Either a built-in scorer name (``"exact_match"``, ``"includes"``)
            or a filesystem path to a ``.py`` file that exports
            ``score(output, expected) -> ScoringResult``.

        Raises
        ------
        FileNotFoundError
            If the JSON file or custom scorer file does not exist.
        ValueError
            If the JSON is invalid or the scorer name is unknown.
        """
        resolved = Path(path).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Benchmark file not found: {resolved}")

        try:
            raw = resolved.read_text(encoding="utf-8")
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in benchmark file {resolved}: {exc}") from exc

        if not isinstance(data, list):
            raise ValueError(
                f"Benchmark JSON must be an array of objects, got {type(data).__name__}"
            )

        examples: list[BenchmarkExample] = []
        for i, item in enumerate(data):
            if not isinstance(item, dict) or "input" not in item or "expected" not in item:
                raise ValueError(
                    f"Benchmark example {i} must be an object with 'input' and 'expected' keys"
                )
            examples.append(BenchmarkExample(
                input=item["input"],
                expected=item["expected"],
                id=item.get("id", f"example_{i}"),
            ))

        scorer = cls._resolve_scorer(scoring_function)

        return cls(
            examples=examples,
            scorer=scorer,
            source_path=str(resolved),
            scoring_function_name=scoring_function,
        )

    @staticmethod
    def _resolve_scorer(scoring_function: str) -> ScorerFn:
        """Resolve a scoring function from a name or file path."""
        # Check built-in scorers first
        if scoring_function in BUILT_IN_SCORERS:
            return BUILT_IN_SCORERS[scoring_function]

        # Try as a file path
        scorer_path = Path(scoring_function).resolve()
        if scorer_path.suffix == ".py" and scorer_path.is_file():
            return _load_scorer_from_file(scorer_path)

        # If it looks like a path but doesn't exist
        if "/" in scoring_function or scoring_function.endswith(".py"):
            raise FileNotFoundError(
                f"Custom scorer file not found: {scorer_path}"
            )

        # Unknown built-in name
        available = ", ".join(sorted(BUILT_IN_SCORERS.keys()))
        raise ValueError(
            f"Unknown scoring function '{scoring_function}'. "
            f"Available built-in scorers: {available}. "
            f"Or provide a path to a .py file with a score(output, expected) function."
        )


def _load_scorer_from_file(path: Path) -> ScorerFn:
    """Load a scorer function from a .py file.

    The file must export a ``score(output, expected)`` callable that returns
    a :class:`ScoringResult`.
    """
    source = path.read_text(encoding="utf-8")
    code = compile(source, str(path), "exec")
    module = types.ModuleType(f"_autoagent_scorer_{path.stem}")
    module.__file__ = str(path)
    exec(code, module.__dict__)  # noqa: S102

    score_fn = getattr(module, "score", None)
    if score_fn is None or not callable(score_fn):
        raise ValueError(
            f"Scorer file {path} must export a callable 'score(output, expected)' function"
        )

    return score_fn
