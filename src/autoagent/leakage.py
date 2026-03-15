"""Data leakage detection for pipeline source against benchmark examples.

Two detection tiers (D046):
- **Exact-match blocking:** AST string literal extraction from pipeline source,
  compared against serialized benchmark examples. Blocks the iteration.
- **Fuzzy n-gram warnings:** Word-level (3,4)-gram Jaccard overlap between
  pipeline source and benchmark examples. Warns only, never blocks.

Self-contained module — imports nothing from loop.py, archive.py, cli.py, or state.py.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from autoagent.benchmark import Benchmark

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LeakageResult:
    """Outcome of a leakage check.

    Fields:
        blocked: True if exact matches were found — iteration must be discarded.
        exact_matches: Count of benchmark values found verbatim in pipeline source.
        fuzzy_warnings: Per-example warnings for high n-gram overlap.
        cost_usd: LLM cost (0.0 for mechanical checks — forward-compatible).
    """

    blocked: bool
    exact_matches: int = 0
    fuzzy_warnings: list[str] = field(default_factory=list)
    cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# String literal extraction
# ---------------------------------------------------------------------------

_QUOTED_STRING_RE = re.compile(
    r'"""(.*?)"""|'
    r"'''(.*?)'''|"
    r'"((?:[^"\\]|\\.)*)"|'
    r"'((?:[^'\\]|\\.)*)'",
    re.DOTALL,
)


def _extract_string_literals_ast(source: str) -> set[str]:
    """Extract all string literal values from Python source via AST."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        logger.warning(
            "AST parse failed (%s), falling back to regex string extraction",
            exc,
        )
        return _extract_string_literals_regex(source)

    literals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.add(node.value)
    return literals


def _extract_string_literals_regex(source: str) -> set[str]:
    """Fallback: extract quoted strings from source via regex."""
    literals: set[str] = set()
    for match in _QUOTED_STRING_RE.finditer(source):
        # Groups: 1=triple-double, 2=triple-single, 3=double, 4=single
        value = match.group(1) or match.group(2) or match.group(3) or match.group(4)
        if value is not None:
            literals.add(value)
    return literals


# ---------------------------------------------------------------------------
# N-gram helpers
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"\w+")


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase words."""
    return _WORD_RE.findall(text.lower())


def _ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    """Extract n-grams as a set of tuples."""
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def _combined_ngrams(tokens: list[str]) -> set[tuple[str, ...]]:
    """Extract combined (3,4)-grams."""
    return _ngrams(tokens, 3) | _ngrams(tokens, 4)


def _jaccard(a: set[Any], b: set[Any]) -> float:
    """Jaccard similarity: |intersection| / |union|. Returns 0.0 if both empty."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_value(value: Any) -> list[str]:
    """Produce string representations of a benchmark value for comparison.

    Returns both ``json.dumps(value, sort_keys=True)`` and ``str(value)``
    to catch different embedding styles.
    """
    representations: list[str] = []
    try:
        representations.append(json.dumps(value, sort_keys=True))
    except (TypeError, ValueError):
        pass
    representations.append(str(value))
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for r in representations:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


def _is_short(value: Any) -> bool:
    """Return True if the string representation of *value* is shorter than 10 chars."""
    return len(str(value)) < 10


# ---------------------------------------------------------------------------
# LeakageChecker
# ---------------------------------------------------------------------------


class LeakageChecker:
    """Detects data leakage between benchmark examples and pipeline source.

    Args:
        fuzzy_threshold: Jaccard similarity threshold for fuzzy n-gram
            warnings (default 0.3). Values above this trigger a warning
            but never block.
    """

    def __init__(self, fuzzy_threshold: float = 0.3) -> None:
        self.fuzzy_threshold = fuzzy_threshold

    def check(self, benchmark: Benchmark, pipeline_source: str) -> LeakageResult:
        """Check *pipeline_source* for leakage of *benchmark* examples.

        Returns a :class:`LeakageResult` with blocking decision and warnings.
        """
        if not benchmark.examples:
            logger.info("Leakage check: no benchmark examples, passing")
            return LeakageResult(blocked=False)

        # --- Exact-match detection ---
        source_literals = _extract_string_literals_ast(pipeline_source)
        exact_matches = 0

        for ex in benchmark.examples:
            # Skip short examples for exact match
            if _is_short(ex.input) and _is_short(ex.expected):
                logger.debug(
                    "Skipping short example %s for exact match", ex.id
                )
                continue

            # Build target strings from both input and expected
            targets: list[str] = []
            targets.extend(_serialize_value(ex.input))
            targets.extend(_serialize_value(ex.expected))

            for target in targets:
                if target in source_literals:
                    exact_matches += 1
                    logger.debug(
                        "Exact match found for example %s: %r",
                        ex.id,
                        target[:80],
                    )
                    break  # Count once per example

        # --- Fuzzy n-gram detection ---
        source_tokens = _tokenize(pipeline_source)
        source_ngrams = _combined_ngrams(source_tokens)
        fuzzy_warnings: list[str] = []

        for ex in benchmark.examples:
            # Build text from example for n-gram extraction
            example_text = f"{ex.input} {ex.expected}"
            example_tokens = _tokenize(str(example_text))
            example_ngrams = _combined_ngrams(example_tokens)

            if not example_ngrams:
                continue

            similarity = _jaccard(source_ngrams, example_ngrams)
            logger.debug(
                "Fuzzy check example %s: Jaccard=%.3f (threshold=%.3f)",
                ex.id,
                similarity,
                self.fuzzy_threshold,
            )

            if similarity > self.fuzzy_threshold:
                fuzzy_warnings.append(
                    f"Example {ex.id}: n-gram overlap {similarity:.2f} "
                    f"exceeds threshold {self.fuzzy_threshold:.2f}"
                )

        blocked = exact_matches > 0

        logger.info(
            "Leakage check: blocked=%s, exact_matches=%d, fuzzy_warnings=%d",
            blocked,
            exact_matches,
            len(fuzzy_warnings),
        )

        return LeakageResult(
            blocked=blocked,
            exact_matches=exact_matches,
            fuzzy_warnings=fuzzy_warnings,
            cost_usd=0.0,
        )
