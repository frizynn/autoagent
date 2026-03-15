"""Evaluation harness — scores pipeline.py against test cases.

Usage:
    python prepare.py eval                 # evaluate pipeline.py
    python prepare.py eval --pipeline X    # evaluate a specific file

This is a TEMPLATE. Users copy and customize it for their problem.
The toy problem here is string transformation: given an input string,
produce a specific output string. The scoring is exact match ratio.

DO NOT MODIFY THIS FILE DURING EXPERIMENTS.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Test cases — the ground truth
# ---------------------------------------------------------------------------

TEST_CASES: list[dict[str, Any]] = [
    {"input": "hello", "expected": "HELLO"},
    {"input": "world", "expected": "WORLD"},
    {"input": "foo bar", "expected": "FOO BAR"},
    {"input": "autoagent", "expected": "AUTOAGENT"},
    {"input": "test 123", "expected": "TEST 123"},
    {"input": "mixed Case", "expected": "MIXED CASE"},
    {"input": "", "expected": ""},
    {"input": "a", "expected": "A"},
    {"input": "ALREADY UPPER", "expected": "ALREADY UPPER"},
    {"input": "hello world 2026", "expected": "HELLO WORLD 2026"},
    {"input": "  spaces  ", "expected": "  SPACES  "},
    {"input": "café", "expected": "CAFÉ"},
    {"input": "naïve résumé", "expected": "NAÏVE RÉSUMÉ"},
    {"input": "123 numbers 456", "expected": "123 NUMBERS 456"},
    {"input": "UPPER lower MiXeD", "expected": "UPPER LOWER MIXED"},
    {"input": "special!@#chars", "expected": "SPECIAL!@#CHARS"},
    {"input": "tab\there", "expected": "TAB\tHERE"},
    {"input": "new\nline", "expected": "NEW\nLINE"},
    {"input": "a b c d e f", "expected": "A B C D E F"},
    {"input": "the quick brown fox", "expected": "THE QUICK BROWN FOX"},
]


# ---------------------------------------------------------------------------
# Pipeline loader
# ---------------------------------------------------------------------------

def load_pipeline(path: str = "pipeline.py") -> Any:
    """Load pipeline.py and return its module."""
    p = Path(path).resolve()
    if not p.exists():
        print(f"Error: {path} not found", file=sys.stderr)
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("pipeline", str(p))
    if spec is None or spec.loader is None:
        print(f"Error: could not load {path}", file=sys.stderr)
        sys.exit(1)

    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        print(f"Error loading pipeline: {exc}", file=sys.stderr)
        sys.exit(1)

    if not hasattr(mod, "run"):
        print(f"Error: {path} must define a run(input_data, context) function", file=sys.stderr)
        sys.exit(1)

    return mod


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

def evaluate(pipeline_path: str = "pipeline.py") -> dict[str, Any]:
    """Run all test cases and return scoring results."""
    mod = load_pipeline(pipeline_path)

    passed = 0
    failed = 0
    errors: list[str] = []

    start = time.monotonic()

    for i, case in enumerate(TEST_CASES):
        try:
            result = mod.run(case["input"], context=None)
            # Accept dict with "output" key or raw string
            if isinstance(result, dict):
                output = result.get("output", result.get("result", str(result)))
            else:
                output = result

            if str(output) == str(case["expected"]):
                passed += 1
            else:
                failed += 1
                if len(errors) < 5:  # Show first 5 errors
                    errors.append(
                        f"  case {i}: input={case['input']!r} "
                        f"expected={case['expected']!r} got={output!r}"
                    )
        except Exception as exc:
            failed += 1
            if len(errors) < 5:
                errors.append(f"  case {i}: input={case['input']!r} error={exc}")

    elapsed_ms = (time.monotonic() - start) * 1000
    total = len(TEST_CASES)
    score = passed / total if total > 0 else 0.0

    return {
        "score": score,
        "total_examples": total,
        "passed": passed,
        "failed": failed,
        "duration_ms": round(elapsed_ms, 1),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python prepare.py eval [--pipeline path]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "eval":
        pipeline_path = "pipeline.py"
        if "--pipeline" in sys.argv:
            idx = sys.argv.index("--pipeline")
            if idx + 1 < len(sys.argv):
                pipeline_path = sys.argv[idx + 1]

        result = evaluate(pipeline_path)

        # Output in parseable format
        print(f"score: {result['score']:.4f}")
        print(f"total_examples: {result['total_examples']}")
        print(f"passed: {result['passed']}")
        print(f"failed: {result['failed']}")
        print(f"duration_ms: {result['duration_ms']}")

        if result["errors"]:
            print("\nFirst failures:")
            for err in result["errors"]:
                print(err)
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python prepare.py eval")
        sys.exit(1)


if __name__ == "__main__":
    main()
