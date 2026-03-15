"""Tests for TLA+ verification gate (TLAVerifier, VerificationResult)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from autoagent.primitives import MetricsCollector, MockLLM
from autoagent.verification import (
    TLAVerifier,
    VerificationResult,
    _is_complex_enough,
    _parse_tlc_output,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A pipeline source that's complex enough to NOT be skipped
COMPLEX_SOURCE = """\
import os
import json

def run(primitives):
    data = primitives.llm.complete("fetch data")
    if not data:
        raise ValueError("empty")
    for item in json.loads(data):
        if item.get("active"):
            result = primitives.llm.complete(f"process {item}")
            try:
                parsed = json.loads(result)
            except json.JSONDecodeError:
                continue
    return parsed
"""

# A trivially simple pipeline that should be skipped
SIMPLE_SOURCE = """\
def run(primitives):
    return primitives.llm.complete("hello")
"""

# Clean TLC output (no errors)
TLC_CLEAN_OUTPUT = """\
TLC2 Version 2.18
Starting...
Model checking completed. No error has been found.
Finished in 01s at (2026-01-01)
"""

# TLC output with an invariant violation
TLC_VIOLATION_OUTPUT = """\
TLC2 Version 2.18
Error: Invariant SafetyInvariant is violated.
Error: The behavior up to this point is:
State 1: <Initial predicate>
State 2: /\\ x = 0
"""

VALID_TLA_SPEC = """\
---- MODULE Pipeline ----
VARIABLES x
Init == x = 1
Next == x' = x + 1
Spec == Init /\\ [][Next]_x
SafetyInvariant == x > 0
====
"""


class SequentialMockLLM:
    """MockLLM that returns different responses on sequential calls."""

    def __init__(
        self,
        responses: list[str],
        cost_per_call: float = 0.01,
    ) -> None:
        self.responses = list(responses)
        self._call_index = 0
        self.prompts: list[str] = []
        # Provide a collector for cost tracking
        self.collector = MetricsCollector()
        self._cost_per_call = cost_per_call

    def complete(self, prompt: str, **kwargs: Any) -> str:
        self.prompts.append(prompt)
        idx = min(self._call_index, len(self.responses) - 1)
        self._call_index += 1
        # Record a snapshot for cost tracking
        from autoagent.types import MetricsSnapshot

        self.collector.record(
            MetricsSnapshot(
                latency_ms=1.0,
                tokens_in=10,
                tokens_out=20,
                cost_usd=self._cost_per_call,
                model="test",
                provider="test",
            )
        )
        return self.responses[idx]


def _make_subprocess_result(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> MagicMock:
    """Create a mock subprocess.CompletedProcess."""
    result = MagicMock()
    result.stdout = stdout
    result.stderr = stderr
    result.returncode = returncode
    return result


# ---------------------------------------------------------------------------
# VerificationResult contract
# ---------------------------------------------------------------------------


class TestVerificationResult:
    def test_frozen_dataclass(self):
        r = VerificationResult(passed=True)
        with pytest.raises(FrozenInstanceError):
            r.passed = False  # type: ignore[misc]

    def test_all_fields_present(self):
        r = VerificationResult(
            passed=False,
            violations=["Error: something"],
            spec_text="spec",
            attempts=2,
            cost_usd=0.05,
            skipped=False,
            skip_reason="",
        )
        assert r.passed is False
        assert r.violations == ["Error: something"]
        assert r.spec_text == "spec"
        assert r.attempts == 2
        assert r.cost_usd == 0.05
        assert r.skipped is False
        assert r.skip_reason == ""

    def test_defaults(self):
        r = VerificationResult(passed=True)
        assert r.violations == []
        assert r.spec_text == ""
        assert r.attempts == 0
        assert r.cost_usd == 0.0
        assert r.skipped is False
        assert r.skip_reason == ""


# ---------------------------------------------------------------------------
# Complexity threshold (_is_complex_enough)
# ---------------------------------------------------------------------------


class TestComplexityThreshold:
    def test_simple_pipeline_below_threshold(self):
        assert _is_complex_enough(SIMPLE_SOURCE) is False

    def test_complex_pipeline_above_threshold(self):
        assert _is_complex_enough(COMPLEX_SOURCE) is True

    def test_many_lines_no_control_flow(self):
        """10+ non-blank non-comment lines → complex even without keywords."""
        source = "\n".join(f"x{i} = {i}" for i in range(12))
        assert _is_complex_enough(source) is True

    def test_few_lines_with_control_flow(self):
        """Below 10 lines but has an `if` → complex."""
        source = "def run(p):\n    if p:\n        return 1\n"
        assert _is_complex_enough(source) is True

    def test_comments_and_blanks_excluded(self):
        """Comments and blank lines don't count toward LOC threshold."""
        source = "# comment\n\n# comment\ndef run(p):\n    return 1\n"
        assert _is_complex_enough(source) is False

    def test_def_run_line_not_counted_as_control_flow(self):
        """The `def run` line itself shouldn't trigger control-flow detection."""
        source = "def run(p):\n    return p.llm.complete('hi')\n"
        assert _is_complex_enough(source) is False


# ---------------------------------------------------------------------------
# TLC output parsing
# ---------------------------------------------------------------------------


class TestParseTlcOutput:
    def test_clean_output(self):
        assert _parse_tlc_output(TLC_CLEAN_OUTPUT, "") == []

    def test_error_lines(self):
        violations = _parse_tlc_output(TLC_VIOLATION_OUTPUT, "")
        assert any("Error:" in v for v in violations)

    def test_invariant_violation(self):
        output = "Invariant SafetyInvariant is violated"
        violations = _parse_tlc_output(output, "")
        assert any("Invariant" in v for v in violations)

    def test_combined_stdout_stderr(self):
        violations = _parse_tlc_output("", "Error: something bad")
        assert violations == ["Error: something bad"]


# ---------------------------------------------------------------------------
# TLAVerifier.available()
# ---------------------------------------------------------------------------


class TestAvailability:
    @patch("autoagent.verification.shutil.which", return_value="/usr/bin/java")
    def test_available_when_java_found(self, mock_which):
        assert TLAVerifier.available() is True
        mock_which.assert_called_with("java")

    @patch("autoagent.verification.shutil.which", return_value=None)
    def test_unavailable_when_no_java(self, mock_which):
        assert TLAVerifier.available() is False


# ---------------------------------------------------------------------------
# TLAVerifier.verify() — successful verification
# ---------------------------------------------------------------------------


class TestVerifySuccess:
    @patch("autoagent.verification.subprocess.run")
    @patch("autoagent.verification.shutil.which", return_value="/usr/bin/java")
    def test_pass_on_clean_tlc(self, mock_which, mock_run):
        mock_run.return_value = _make_subprocess_result(stdout=TLC_CLEAN_OUTPUT)
        llm = SequentialMockLLM([VALID_TLA_SPEC])
        verifier = TLAVerifier(llm=llm, max_attempts=3)

        result = verifier.verify(COMPLEX_SOURCE)

        assert result.passed is True
        assert result.violations == []
        assert result.attempts == 1
        assert result.skipped is False
        assert result.spec_text == VALID_TLA_SPEC

    @patch("autoagent.verification.subprocess.run")
    @patch("autoagent.verification.shutil.which", return_value="/usr/bin/java")
    def test_tlc_called_with_correct_args(self, mock_which, mock_run):
        mock_run.return_value = _make_subprocess_result(stdout=TLC_CLEAN_OUTPUT)
        llm = SequentialMockLLM([VALID_TLA_SPEC])
        verifier = TLAVerifier(llm=llm, tlc_jar_path="/path/to/tla2tools.jar")

        verifier.verify(COMPLEX_SOURCE)

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "java"
        assert cmd[1] == "-cp"
        assert cmd[2] == "/path/to/tla2tools.jar"
        assert cmd[3] == "tlc2.TLC"
        assert cmd[4].endswith(".tla")


# ---------------------------------------------------------------------------
# TLAVerifier.verify() — failed verification
# ---------------------------------------------------------------------------


class TestVerifyFailure:
    @patch("autoagent.verification.subprocess.run")
    @patch("autoagent.verification.shutil.which", return_value="/usr/bin/java")
    def test_fail_on_invariant_violation(self, mock_which, mock_run):
        mock_run.return_value = _make_subprocess_result(
            stdout=TLC_VIOLATION_OUTPUT
        )
        llm = SequentialMockLLM([VALID_TLA_SPEC] * 3)
        verifier = TLAVerifier(llm=llm, max_attempts=3)

        result = verifier.verify(COMPLEX_SOURCE)

        assert result.passed is False
        assert len(result.violations) > 0
        assert result.attempts == 3


# ---------------------------------------------------------------------------
# Genefication recovery
# ---------------------------------------------------------------------------


class TestGeneficationRecovery:
    @patch("autoagent.verification.subprocess.run")
    @patch("autoagent.verification.shutil.which", return_value="/usr/bin/java")
    def test_recovery_on_second_attempt(self, mock_which, mock_run):
        """First TLC run fails, LLM fixes the spec, second TLC run passes."""
        mock_run.side_effect = [
            # Attempt 1: violation
            _make_subprocess_result(stdout=TLC_VIOLATION_OUTPUT),
            # Attempt 2: clean
            _make_subprocess_result(stdout=TLC_CLEAN_OUTPUT),
        ]
        llm = SequentialMockLLM(
            ["bad spec", "fixed spec"],
            cost_per_call=0.02,
        )
        verifier = TLAVerifier(llm=llm, max_attempts=3)

        result = verifier.verify(COMPLEX_SOURCE)

        assert result.passed is True
        assert result.attempts == 2
        assert result.spec_text == "fixed spec"
        # LLM was called twice
        assert len(llm.prompts) == 2
        # Second prompt should reference the errors (genefication)
        assert "errors" in llm.prompts[1].lower() or "fix" in llm.prompts[1].lower()

    @patch("autoagent.verification.subprocess.run")
    @patch("autoagent.verification.shutil.which", return_value="/usr/bin/java")
    def test_recovery_on_third_attempt(self, mock_which, mock_run):
        """Fails twice, succeeds on third."""
        mock_run.side_effect = [
            _make_subprocess_result(stdout=TLC_VIOLATION_OUTPUT),
            _make_subprocess_result(stdout=TLC_VIOLATION_OUTPUT),
            _make_subprocess_result(stdout=TLC_CLEAN_OUTPUT),
        ]
        llm = SequentialMockLLM(["v1", "v2", "v3"])
        verifier = TLAVerifier(llm=llm, max_attempts=3)

        result = verifier.verify(COMPLEX_SOURCE)

        assert result.passed is True
        assert result.attempts == 3


# ---------------------------------------------------------------------------
# Complexity skip
# ---------------------------------------------------------------------------


class TestComplexitySkip:
    def test_simple_pipeline_skipped(self):
        llm = SequentialMockLLM(["should not be called"])
        verifier = TLAVerifier(llm=llm)

        result = verifier.verify(SIMPLE_SOURCE)

        assert result.passed is True
        assert result.skipped is True
        assert "complexity" in result.skip_reason.lower()
        assert result.attempts == 0
        assert len(llm.prompts) == 0  # LLM never called


# ---------------------------------------------------------------------------
# All attempts exhausted
# ---------------------------------------------------------------------------


class TestAllAttemptsExhausted:
    @patch("autoagent.verification.subprocess.run")
    @patch("autoagent.verification.shutil.which", return_value="/usr/bin/java")
    def test_three_failures_returns_not_passed(self, mock_which, mock_run):
        mock_run.return_value = _make_subprocess_result(
            stdout=TLC_VIOLATION_OUTPUT
        )
        llm = SequentialMockLLM(["spec1", "spec2", "spec3"])
        verifier = TLAVerifier(llm=llm, max_attempts=3)

        result = verifier.verify(COMPLEX_SOURCE)

        assert result.passed is False
        assert result.attempts == 3
        assert len(result.violations) > 0
        assert result.spec_text == "spec3"  # last attempted spec


# ---------------------------------------------------------------------------
# Cost accumulation
# ---------------------------------------------------------------------------


class TestCostAccumulation:
    @patch("autoagent.verification.subprocess.run")
    @patch("autoagent.verification.shutil.which", return_value="/usr/bin/java")
    def test_cost_accumulated_across_attempts(self, mock_which, mock_run):
        mock_run.side_effect = [
            _make_subprocess_result(stdout=TLC_VIOLATION_OUTPUT),
            _make_subprocess_result(stdout=TLC_CLEAN_OUTPUT),
        ]
        llm = SequentialMockLLM(["v1", "v2"], cost_per_call=0.05)
        verifier = TLAVerifier(llm=llm, max_attempts=3)

        result = verifier.verify(COMPLEX_SOURCE)

        assert result.passed is True
        assert result.attempts == 2
        assert result.cost_usd == pytest.approx(0.10)  # 2 calls × 0.05

    @patch("autoagent.verification.subprocess.run")
    @patch("autoagent.verification.shutil.which", return_value="/usr/bin/java")
    def test_cost_on_single_pass(self, mock_which, mock_run):
        mock_run.return_value = _make_subprocess_result(stdout=TLC_CLEAN_OUTPUT)
        llm = SequentialMockLLM(["spec"], cost_per_call=0.03)
        verifier = TLAVerifier(llm=llm, max_attempts=3)

        result = verifier.verify(COMPLEX_SOURCE)

        assert result.cost_usd == pytest.approx(0.03)


# ---------------------------------------------------------------------------
# Unavailable (Java not on PATH)
# ---------------------------------------------------------------------------


class TestUnavailableGracefulDegradation:
    @patch("autoagent.verification.shutil.which", return_value=None)
    def test_skips_when_java_unavailable(self, mock_which):
        llm = SequentialMockLLM(["should not be called"])
        verifier = TLAVerifier(llm=llm)

        result = verifier.verify(COMPLEX_SOURCE)

        assert result.passed is True
        assert result.skipped is True
        assert "java" in result.skip_reason.lower()
        assert result.attempts == 0
        assert len(llm.prompts) == 0


# ---------------------------------------------------------------------------
# TLC subprocess edge cases
# ---------------------------------------------------------------------------


class TestTlcSubprocess:
    @patch("autoagent.verification.subprocess.run")
    @patch("autoagent.verification.shutil.which", return_value="/usr/bin/java")
    def test_timeout_treated_as_violation(self, mock_which, mock_run):
        import subprocess as sp

        mock_run.side_effect = sp.TimeoutExpired(cmd="java", timeout=60)
        llm = SequentialMockLLM(["spec"] * 3)
        verifier = TLAVerifier(llm=llm, max_attempts=3, tlc_timeout=60)

        result = verifier.verify(COMPLEX_SOURCE)

        assert result.passed is False
        assert any("timed out" in v.lower() for v in result.violations)

    @patch("autoagent.verification.subprocess.run")
    @patch("autoagent.verification.shutil.which", return_value="/usr/bin/java")
    def test_tlc_jar_path_from_env(self, mock_which, mock_run):
        mock_run.return_value = _make_subprocess_result(stdout=TLC_CLEAN_OUTPUT)
        llm = SequentialMockLLM([VALID_TLA_SPEC])

        with patch.dict("os.environ", {"TLC_JAR_PATH": "/custom/tla2tools.jar"}):
            verifier = TLAVerifier(llm=llm)
            assert verifier.tlc_jar_path == "/custom/tla2tools.jar"


# ---------------------------------------------------------------------------
# Module isolation check
# ---------------------------------------------------------------------------


class TestModuleIsolation:
    def test_no_loop_import(self):
        """verification.py must not import from loop.py."""
        import importlib
        import inspect

        mod = importlib.import_module("autoagent.verification")
        source = inspect.getsource(mod)
        assert "from autoagent.loop" not in source
        assert "import autoagent.loop" not in source

    def test_no_archive_import(self):
        """verification.py must not import from archive.py."""
        import importlib
        import inspect

        mod = importlib.import_module("autoagent.verification")
        source = inspect.getsource(mod)
        assert "from autoagent.archive" not in source
        assert "import autoagent.archive" not in source
