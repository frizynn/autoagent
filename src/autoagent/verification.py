"""TLA+ formal verification gate for pipeline proposals.

Generates TLA+ specifications from pipeline source via LLM, runs the TLC
model checker, and retries with genefication on spec errors. Provides
graceful degradation when Java/TLC is unavailable (D043) and skips trivial
pipelines below a complexity threshold (D047).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protocols — keep self-contained, no imports from loop.py or archive.py
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProtocol(Protocol):
    """Structural interface for language-model primitives."""

    def complete(self, prompt: str, **kwargs: Any) -> str: ...


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of a TLA+ verification attempt.

    Fields:
        passed: True if TLC found no violations (or verification was skipped).
        violations: Error strings extracted from TLC output.
        spec_text: The final TLA+ spec text that was checked (empty if skipped).
        attempts: Number of generate-check rounds executed.
        cost_usd: Cumulative LLM cost across all genefication attempts.
        skipped: True if verification was skipped (e.g. complexity threshold).
        skip_reason: Human-readable reason for skipping, empty if not skipped.
    """

    passed: bool
    violations: list[str] = field(default_factory=list)
    spec_text: str = ""
    attempts: int = 0
    cost_usd: float = 0.0
    skipped: bool = False
    skip_reason: str = ""


# ---------------------------------------------------------------------------
# Complexity threshold (D047)
# ---------------------------------------------------------------------------

_CONTROL_FLOW_KW = re.compile(r"\b(if|for|while|try)\b")
_DEF_RUN_RE = re.compile(r"^\s*def\s+run\b")


def _is_complex_enough(source: str) -> bool:
    """Return True if the source is complex enough to warrant TLA+ verification.

    Skips verification when *both*:
    - Fewer than 10 non-blank, non-comment lines
    - No control-flow keywords (if/for/while/try) outside the top-level ``def run``
    """
    lines = source.splitlines()

    # Count meaningful lines
    meaningful = 0
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            meaningful += 1

    if meaningful >= 10:
        return True

    # Check for control-flow keywords outside the `def run` line itself
    for line in lines:
        stripped = line.strip()
        if _DEF_RUN_RE.match(stripped):
            continue
        if _CONTROL_FLOW_KW.search(stripped):
            return True

    return False


# ---------------------------------------------------------------------------
# TLC output parsing
# ---------------------------------------------------------------------------

_TLC_ERROR_RE = re.compile(r"^Error:.*", re.MULTILINE)
_TLC_INVARIANT_RE = re.compile(r"Invariant\s+\S+\s+is violated", re.MULTILINE)


def _parse_tlc_output(stdout: str, stderr: str) -> list[str]:
    """Extract violation messages from TLC stdout/stderr."""
    combined = stdout + "\n" + stderr
    violations: list[str] = []

    for match in _TLC_ERROR_RE.finditer(combined):
        violations.append(match.group(0).strip())

    for match in _TLC_INVARIANT_RE.finditer(combined):
        text = match.group(0).strip()
        if text not in violations:
            violations.append(text)

    return violations


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_GENERATE_PROMPT = """\
You are a formal verification expert. Given the following Python pipeline source code, \
generate a TLA+ specification that models its core behavior. The spec should include \
safety invariants that must hold during execution.

Return ONLY the TLA+ spec text, no markdown fences or commentary.

Pipeline source:
```python
{source}
```"""

_GENEFICATION_PROMPT = """\
The TLA+ spec you generated has errors when checked by TLC. \
Fix the spec to resolve the following errors. Return ONLY the corrected TLA+ spec text.

Original spec:
```tla
{spec}
```

TLC errors:
{errors}"""


# ---------------------------------------------------------------------------
# TLAVerifier
# ---------------------------------------------------------------------------

# Default TLC subprocess timeout in seconds
_TLC_TIMEOUT_SECONDS = 60


class TLAVerifier:
    """Generates TLA+ specs via LLM and verifies them with the TLC model checker.

    Supports genefication: on TLC failure, re-prompts the LLM with the errors
    up to ``max_attempts`` total rounds (D048).

    Args:
        llm: An object satisfying :class:`LLMProtocol`.
        max_attempts: Maximum generate-check rounds (default 3, per D048).
        tlc_jar_path: Explicit path to ``tla2tools.jar``. Falls back to
            ``TLC_JAR_PATH`` env var, then ``tla2tools.jar`` in cwd.
        tlc_timeout: Subprocess timeout in seconds for each TLC invocation.
    """

    def __init__(
        self,
        llm: LLMProtocol,
        max_attempts: int = 3,
        tlc_jar_path: str | None = None,
        tlc_timeout: int = _TLC_TIMEOUT_SECONDS,
    ) -> None:
        self.llm = llm
        self.max_attempts = max_attempts
        self.tlc_jar_path = (
            tlc_jar_path
            or os.environ.get("TLC_JAR_PATH")
            or "tla2tools.jar"
        )
        self.tlc_timeout = tlc_timeout

    # -- availability check (D043) ------------------------------------------

    @staticmethod
    def available() -> bool:
        """Return True if Java is on PATH (required to run TLC).

        Does not check for the jar file — that is validated at verify() time.
        """
        return shutil.which("java") is not None

    # -- main entry point ---------------------------------------------------

    def verify(self, source: str) -> VerificationResult:
        """Run TLA+ verification on pipeline *source*.

        Returns a :class:`VerificationResult` with outcome, violations,
        cost, and attempt count.
        """
        # (a) Complexity threshold (D047)
        if not _is_complex_enough(source):
            reason = "Below complexity threshold (< 10 LOC, no control flow)"
            logger.info("TLA+ verification skipped: %s", reason)
            return VerificationResult(
                passed=True,
                skipped=True,
                skip_reason=reason,
            )

        # Check availability
        if not self.available():
            reason = "Java not available on PATH"
            logger.warning("TLA+ verification skipped: %s", reason)
            return VerificationResult(
                passed=True,
                skipped=True,
                skip_reason=reason,
            )

        cumulative_cost = 0.0
        spec_text = ""
        violations: list[str] = []

        for attempt in range(1, self.max_attempts + 1):
            # (b/f) Generate or fix spec via LLM
            if attempt == 1:
                prompt = _GENERATE_PROMPT.format(source=source)
            else:
                prompt = _GENEFICATION_PROMPT.format(
                    spec=spec_text,
                    errors="\n".join(violations),
                )

            spec_text = self.llm.complete(prompt)

            # Track cost if the LLM exposes it via MetricsSnapshot pattern
            cumulative_cost += self._extract_llm_cost()

            # (c) Write spec to temp file
            # (d) Run TLC
            violations = self._run_tlc(spec_text)

            if not violations:
                logger.info(
                    "TLA+ verification passed on attempt %d/%d (source: %d chars)",
                    attempt,
                    self.max_attempts,
                    len(source),
                )
                return VerificationResult(
                    passed=True,
                    spec_text=spec_text,
                    attempts=attempt,
                    cost_usd=cumulative_cost,
                )

            logger.info(
                "TLA+ verification failed on attempt %d/%d: %d violation(s)",
                attempt,
                self.max_attempts,
                len(violations),
            )

        # (g) All attempts exhausted
        logger.info(
            "TLA+ verification failed after %d attempts: %s",
            self.max_attempts,
            violations,
        )
        return VerificationResult(
            passed=False,
            violations=violations,
            spec_text=spec_text,
            attempts=self.max_attempts,
            cost_usd=cumulative_cost,
        )

    # -- internal helpers ---------------------------------------------------

    def _run_tlc(self, spec_text: str) -> list[str]:
        """Write *spec_text* to a temp file and run TLC. Return violations."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".tla", delete=False
        ) as f:
            f.write(spec_text)
            spec_path = f.name

        try:
            result = subprocess.run(
                ["java", "-cp", self.tlc_jar_path, "tlc2.TLC", spec_path],
                capture_output=True,
                text=True,
                timeout=self.tlc_timeout,
            )
            return _parse_tlc_output(result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            return [f"Error: TLC timed out after {self.tlc_timeout}s"]
        except FileNotFoundError:
            return ["Error: Java binary not found"]
        finally:
            try:
                os.unlink(spec_path)
            except OSError:
                pass

    def _extract_llm_cost(self) -> float:
        """Extract cost from the last LLM call if the LLM tracks it.

        Works with MockLLM and any LLM that has a ``collector`` with
        ``snapshots``. Returns 0.0 if unavailable.
        """
        collector = getattr(self.llm, "collector", None)
        if collector is None:
            return 0.0
        snapshots = getattr(collector, "snapshots", [])
        if not snapshots:
            return 0.0
        return snapshots[-1].cost_usd
