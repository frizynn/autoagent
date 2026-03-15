"""Tests for stagnation detection and mutation classification."""

from __future__ import annotations

import pytest

from autoagent.archive import ArchiveEntry
from autoagent.strategy import analyze_strategy, classify_mutation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    iteration_id: int,
    score: float = 0.5,
    pipeline_diff: str = "",
    mutation_type: str | None = None,
    decision: str = "keep",
) -> ArchiveEntry:
    """Create a minimal ArchiveEntry for strategy testing."""
    return ArchiveEntry(
        iteration_id=iteration_id,
        timestamp=1000.0 + iteration_id,
        pipeline_diff=pipeline_diff,
        evaluation_result={
            "primary_score": score,
            "per_example_results": [],
            "benchmark_id": "test",
            "duration_ms": 100.0,
            "num_examples": 1,
            "num_failures": 0,
        },
        rationale="test",
        decision=decision,
        mutation_type=mutation_type,
    )


# ---------------------------------------------------------------------------
# classify_mutation
# ---------------------------------------------------------------------------


class TestClassifyMutation:
    """Tests for classify_mutation()."""

    def test_empty_diff(self):
        assert classify_mutation("") == "parametric"

    def test_whitespace_only_diff(self):
        assert classify_mutation("   \n  \n") == "parametric"

    def test_new_function_def(self):
        diff = """\
@@ -1,3 +1,6 @@
 def run(input_data, primitives=None):
+    result = helper(input_data)
+    return result
+
+def helper(data):
+    return data.upper()
"""
        assert classify_mutation(diff) == "structural"

    def test_new_import(self):
        diff = """\
@@ -1,2 +1,3 @@
+import json
 def run(input_data, primitives=None):
     return {"answer": "hello"}
"""
        assert classify_mutation(diff) == "structural"

    def test_new_from_import(self):
        diff = """\
@@ -1,2 +1,3 @@
+from typing import Any
 def run(input_data, primitives=None):
     return {"answer": "hello"}
"""
        assert classify_mutation(diff) == "structural"

    def test_control_flow_change(self):
        diff = """\
@@ -1,3 +1,5 @@
 def run(input_data, primitives=None):
+    if not input_data:
+        return {"answer": "empty"}
     return {"answer": "hello"}
"""
        assert classify_mutation(diff) == "structural"

    def test_primitives_call(self):
        diff = """\
@@ -1,3 +1,4 @@
 def run(input_data, primitives=None):
+    result = primitives.llm_call("summarize", input_data)
     return {"answer": "hello"}
"""
        assert classify_mutation(diff) == "structural"

    def test_removed_function_def(self):
        diff = """\
@@ -1,6 +1,3 @@
 def run(input_data, primitives=None):
-    result = helper(input_data)
-    return result
-
-def helper(data):
-    return data.upper()
+    return {"answer": "hello"}
"""
        assert classify_mutation(diff) == "structural"

    def test_string_change_is_parametric(self):
        diff = """\
@@ -1,3 +1,3 @@
 def run(input_data, primitives=None):
-    return {"answer": "hello"}
+    return {"answer": "goodbye"}
"""
        assert classify_mutation(diff) == "parametric"

    def test_number_change_is_parametric(self):
        diff = """\
@@ -1,3 +1,3 @@
 def run(input_data, primitives=None):
-    threshold = 0.5
+    threshold = 0.7
     return {"answer": "hello"}
"""
        assert classify_mutation(diff) == "parametric"

    def test_variable_rename_is_parametric(self):
        diff = """\
@@ -1,3 +1,3 @@
 def run(input_data, primitives=None):
-    result = "hello"
+    output = "hello"
     return {"answer": output}
"""
        assert classify_mutation(diff) == "parametric"

    def test_for_loop_is_structural(self):
        diff = """\
@@ -1,3 +1,4 @@
 def run(input_data, primitives=None):
-    result = process(input_data)
+    for item in input_data:
+        result = process(item)
     return {"answer": result}
"""
        assert classify_mutation(diff) == "structural"


# ---------------------------------------------------------------------------
# analyze_strategy
# ---------------------------------------------------------------------------


class TestAnalyzeStrategy:
    """Tests for analyze_strategy()."""

    def test_empty_entries(self):
        assert analyze_strategy([]) == ""

    def test_single_entry(self):
        entries = [_make_entry(1, score=0.5)]
        assert analyze_strategy(entries) == ""

    def test_improving_sequence_no_signal(self):
        """Steadily improving scores → no stagnation signal."""
        entries = [
            _make_entry(i, score=0.1 * i)
            for i in range(10, 0, -1)  # newest-first
        ]
        result = analyze_strategy(entries)
        # Should be empty or just a parameter tuning suggestion
        assert "plateaued" not in result

    def test_plateau_triggers_signal(self):
        """5+ iterations at same score → stagnation signal."""
        # Best score is 0.8 at the oldest position, then plateau at 0.5
        entries = [_make_entry(i, score=0.5) for i in range(10, 0, -1)]
        # Make the oldest one the best
        entries[-1] = _make_entry(1, score=0.8)

        result = analyze_strategy(entries, plateau_threshold=5)
        assert "plateaued" in result.lower()
        assert "9" in result  # 9 entries plateaued (all except the best)

    def test_short_plateau_no_signal(self):
        """Fewer than threshold iterations at same score → no signal."""
        # 3 entries at 0.5, then one at 0.8 (best), then improving
        entries = [
            _make_entry(5, score=0.5),
            _make_entry(4, score=0.5),
            _make_entry(3, score=0.5),
            _make_entry(2, score=0.8),  # best
            _make_entry(1, score=0.6),
        ]
        result = analyze_strategy(entries, plateau_threshold=5)
        assert "plateaued" not in result

    def test_all_parametric_during_plateau_suggests_structural(self):
        """Plateau with all parametric mutations → suggest structural changes."""
        entries = [
            _make_entry(i, score=0.5, mutation_type="parametric")
            for i in range(10, 0, -1)
        ]
        entries[-1] = _make_entry(1, score=0.8, mutation_type="parametric")

        result = analyze_strategy(entries, plateau_threshold=5)
        assert "structural" in result.lower()
        assert "parametric" in result.lower()

    def test_all_structural_during_plateau_suggests_parametric(self):
        """Plateau with all structural mutations → suggest parameter tuning."""
        entries = [
            _make_entry(i, score=0.5, mutation_type="structural")
            for i in range(10, 0, -1)
        ]
        entries[-1] = _make_entry(1, score=0.8, mutation_type="structural")

        result = analyze_strategy(entries, plateau_threshold=5)
        assert "parameter" in result.lower() or "tuning" in result.lower()

    def test_extended_plateau_stronger_signal(self):
        """8+ iterations plateau with mixed types → fundamentally different approach."""
        entries = [
            _make_entry(
                i,
                score=0.5,
                mutation_type="structural" if i % 2 == 0 else "parametric",
            )
            for i in range(10, 0, -1)
        ]
        # Put the best score at the oldest position within the window
        entries[-1] = _make_entry(1, score=0.8, mutation_type="structural")

        result = analyze_strategy(entries, window=10, plateau_threshold=5)
        assert "plateaued" in result.lower()
        # Extended plateau with mixed → should mention fundamentally
        assert "fundamental" in result.lower() or "rethink" in result.lower()

    def test_fallback_to_diff_classification(self):
        """Entries without mutation_type → falls back to classify_mutation(pipeline_diff)."""
        structural_diff = "+def helper(x):\n+    return x\n"
        parametric_diff = "-    threshold = 0.5\n+    threshold = 0.7\n"

        entries = [
            _make_entry(i, score=0.5, pipeline_diff=parametric_diff)
            for i in range(8, 0, -1)
        ]
        entries[-1] = _make_entry(1, score=0.8, pipeline_diff=structural_diff)

        result = analyze_strategy(entries, plateau_threshold=5)
        # Mostly parametric diffs → should suggest structural changes
        assert "structural" in result.lower()

    def test_window_larger_than_entries(self):
        """Window=10 but only 3 entries → uses all entries, no crash."""
        entries = [
            _make_entry(3, score=0.5),
            _make_entry(2, score=0.5),
            _make_entry(1, score=0.5),
        ]
        result = analyze_strategy(entries, window=10)
        # Only 3 entries, plateau_threshold=5 (default) → no plateau signal
        assert "plateaued" not in result

    def test_all_identical_scores(self):
        """All identical scores → zero variance, full plateau."""
        entries = [_make_entry(i, score=0.5) for i in range(10, 0, -1)]
        result = analyze_strategy(entries, plateau_threshold=5)
        # All same score — best is at any position, plateau_len depends on
        # how we count "not improved over best" (equal isn't an improvement).
        # With all scores equal, none is < best, so plateau_len = 0.
        # This is correct — if every iteration ties the best, there's no
        # plateau in the "failing to improve" sense.
        assert "plateaued" not in result

    def test_signal_includes_diagnostic_numbers(self):
        """Plateau signal includes plateau length and diversity ratio."""
        entries = [
            _make_entry(i, score=0.5, mutation_type="parametric")
            for i in range(10, 0, -1)
        ]
        entries[-1] = _make_entry(1, score=0.8, mutation_type="parametric")

        result = analyze_strategy(entries, plateau_threshold=5)
        # Must include plateau count
        assert "9" in result
        # Must include variance
        assert "variance" in result.lower()
        # Must include structural ratio
        assert "0%" in result or "structural ratio" in result

    def test_signal_length_within_bounds(self):
        """Signals should be compact, ~200-500 chars."""
        entries = [
            _make_entry(i, score=0.5, mutation_type="parametric")
            for i in range(10, 0, -1)
        ]
        entries[-1] = _make_entry(1, score=0.8, mutation_type="parametric")

        result = analyze_strategy(entries, plateau_threshold=5)
        assert len(result) > 0
        assert len(result) <= 600  # allow some slack

    def test_improving_with_high_structural_ratio_suggests_tuning(self):
        """Improving scores with mostly structural changes → suggest tuning."""
        entries = [
            _make_entry(i, score=0.1 * i, mutation_type="structural")
            for i in range(6, 0, -1)
        ]
        result = analyze_strategy(entries, plateau_threshold=5)
        assert "tuning" in result.lower() or "parameter" in result.lower()
