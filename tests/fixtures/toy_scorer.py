"""Custom scorer fixture for testing file-based scorer resolution.

Exports a ``score(output, expected)`` function that returns a ScoringResult.
This scorer checks if the string representation of the output contains
the expected value (case-insensitive).
"""

from autoagent.benchmark import ScoringResult


def score(output, expected) -> ScoringResult:
    """Case-insensitive substring match scorer."""
    output_str = str(output).lower()
    expected_str = str(expected).lower()
    if expected_str in output_str:
        return ScoringResult(score=1.0)
    return ScoringResult(score=0.0)
