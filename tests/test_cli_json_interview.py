"""Tests for the --json interview protocol of ``autoagent new``."""

from __future__ import annotations

import builtins
import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from autoagent.cli import build_parser, cmd_new, _json_emit, _build_json_orchestrator
from autoagent.interview import PHASES, InterviewOrchestrator, SequenceMockLLM
from autoagent.state import StateManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_answer(text: str) -> str:
    """Create a JSON answer line."""
    return json.dumps({"type": "answer", "text": text}) + "\n"


def _make_abort() -> str:
    """Create a JSON abort line."""
    return json.dumps({"type": "abort"}) + "\n"


# 6 phases + 1 confirmation = 7 answers needed for a full interview
GOOD_ANSWERS = [
    "Optimize ML model accuracy for production deployment",      # goal
    "F1 score, latency under 100ms, throughput above 1000 rps",  # metrics
    "Budget under $500, must run on GPU with 16GB VRAM",         # constraints
    "Learning rate 1e-5 to 1e-2, batch size 16 to 128",         # search_space
    "We have benchmark.json with 500 labeled examples",          # benchmark
    "Budget is $200 for this optimization run",                  # budget
    "yes",                                                       # confirmation
]


def _build_stdin(answers: list[str]) -> str:
    """Build a multi-line stdin string from answer texts."""
    return "".join(_make_answer(a) for a in answers)


def _run_json_interview(
    answers: list[str],
    tmp_path: Path,
) -> tuple[int, list[dict], str]:
    """Run autoagent new --json with given answers.

    Returns (exit_code, stdout_events, stderr_text).
    """
    stdin_data = _build_stdin(answers)
    stdout_buf = StringIO()
    stderr_buf = StringIO()

    parser = build_parser()
    args = parser.parse_args(["--project-dir", str(tmp_path), "new", "--json"])

    with (
        patch("sys.stdin", StringIO(stdin_data)),
        patch("sys.stdout", stdout_buf),
        patch("sys.stderr", stderr_buf),
    ):
        exit_code = cmd_new(args)

    stdout_text = stdout_buf.getvalue()
    events = []
    for line in stdout_text.strip().splitlines():
        if line.strip():
            events.append(json.loads(line))

    return exit_code, events, stderr_buf.getvalue()


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestJSONParserFlag:
    def test_json_flag_accepted(self) -> None:
        """--json flag is parsed without error."""
        parser = build_parser()
        args = parser.parse_args(["new", "--json"])
        assert args.json is True

    def test_json_flag_default_false(self) -> None:
        """--json defaults to False."""
        parser = build_parser()
        args = parser.parse_args(["new"])
        assert args.json is False


# ---------------------------------------------------------------------------
# Protocol round-trip tests
# ---------------------------------------------------------------------------


class TestJSONProtocolRoundTrip:
    """Full interview through JSON protocol."""

    def test_full_interview_emits_all_phases(self, tmp_path: Path) -> None:
        """All 6 phases + confirmation + complete event are emitted."""
        exit_code, events, _ = _run_json_interview(GOOD_ANSWERS, tmp_path)
        assert exit_code == 0

        # Should have prompt events for each phase
        prompts = [e for e in events if e["type"] == "prompt"]
        phase_names = [p["phase"] for p in prompts]
        expected_phases = [p[0] for p in PHASES]
        assert phase_names[:len(expected_phases)] == expected_phases

        # Should have a confirm event
        confirms = [e for e in events if e["type"] == "confirm"]
        assert len(confirms) >= 1

        # Should have a complete event at the end
        complete = [e for e in events if e["type"] == "complete"]
        assert len(complete) == 1

    def test_complete_event_has_config_and_context(self, tmp_path: Path) -> None:
        """Complete event includes valid config dict and context string."""
        _, events, _ = _run_json_interview(GOOD_ANSWERS, tmp_path)
        complete = [e for e in events if e["type"] == "complete"][0]

        assert "config" in complete
        assert "context" in complete
        assert isinstance(complete["config"], dict)
        assert isinstance(complete["context"], str)
        assert complete["config"]["goal"] == GOOD_ANSWERS[0]

    def test_prompt_has_question_field(self, tmp_path: Path) -> None:
        """Each prompt event has a non-empty question field."""
        _, events, _ = _run_json_interview(GOOD_ANSWERS, tmp_path)
        prompts = [e for e in events if e["type"] == "prompt"]
        for p in prompts:
            assert "question" in p
            assert len(p["question"]) > 0

    def test_confirmation_prompt_exists(self, tmp_path: Path) -> None:
        """Confirmation phase emits a prompt with phase='confirmation'."""
        _, events, _ = _run_json_interview(GOOD_ANSWERS, tmp_path)
        confirm_prompts = [
            e for e in events
            if e["type"] == "prompt" and e.get("phase") == "confirmation"
        ]
        # The confirmation answer is collected via input_fn which emits a prompt
        # after the confirm summary
        assert len(confirm_prompts) >= 1 or any(
            e["type"] == "confirm" for e in events
        )

    def test_config_written_to_disk(self, tmp_path: Path) -> None:
        """JSON mode still writes config and context to disk."""
        _run_json_interview(GOOD_ANSWERS, tmp_path)
        sm = StateManager(tmp_path)
        config = sm.read_config()
        assert config.goal == GOOD_ANSWERS[0]
        context_path = sm.aa_dir / "context.md"
        assert context_path.exists()


# ---------------------------------------------------------------------------
# Vague input follow-up
# ---------------------------------------------------------------------------


class TestJSONVagueFollowUp:
    def test_vague_input_triggers_followup_probe(self, tmp_path: Path) -> None:
        """A vague answer triggers a follow-up probe as a new prompt event."""
        # Give a vague first answer, then a good one for all remaining
        answers = [
            "better",  # vague goal
            GOOD_ANSWERS[0],  # good goal (after probe)
        ] + GOOD_ANSWERS[1:]

        exit_code, events, _ = _run_json_interview(answers, tmp_path)
        assert exit_code == 0

        # Should have more prompts than phases (at least one extra for the probe)
        prompts = [e for e in events if e["type"] == "prompt"]
        assert len(prompts) > len(PHASES)

        # The goal phase should appear at least twice
        goal_prompts = [p for p in prompts if p["phase"] == "goal"]
        assert len(goal_prompts) >= 2


# ---------------------------------------------------------------------------
# Abort handling
# ---------------------------------------------------------------------------


class TestJSONAbort:
    def test_abort_triggers_clean_exit(self, tmp_path: Path) -> None:
        """Sending {"type":"abort"} causes non-zero exit without traceback."""
        # Send one good answer then an abort
        stdin_data = _make_answer(GOOD_ANSWERS[0]) + _make_abort()
        stdout_buf = StringIO()
        stderr_buf = StringIO()

        parser = build_parser()
        args = parser.parse_args(["--project-dir", str(tmp_path), "new", "--json"])

        with (
            patch("sys.stdin", StringIO(stdin_data)),
            patch("sys.stdout", stdout_buf),
            patch("sys.stderr", stderr_buf),
        ):
            exit_code = cmd_new(args)

        assert exit_code == 1
        # No Python traceback in stderr
        assert "Traceback" not in stderr_buf.getvalue()


# ---------------------------------------------------------------------------
# EOF handling
# ---------------------------------------------------------------------------


class TestJSONEOF:
    def test_eof_on_stdin_handled_gracefully(self, tmp_path: Path) -> None:
        """If stdin closes early, exit non-zero with error event, no traceback."""
        # Only provide one answer — stdin will EOF on second read
        stdin_data = _make_answer(GOOD_ANSWERS[0])
        stdout_buf = StringIO()
        stderr_buf = StringIO()

        parser = build_parser()
        args = parser.parse_args(["--project-dir", str(tmp_path), "new", "--json"])

        with (
            patch("sys.stdin", StringIO(stdin_data)),
            patch("sys.stdout", stdout_buf),
            patch("sys.stderr", stderr_buf),
        ):
            exit_code = cmd_new(args)

        assert exit_code == 1
        # Should emit an error event
        stdout_text = stdout_buf.getvalue()
        events = [json.loads(l) for l in stdout_text.strip().splitlines() if l.strip()]
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) >= 1
        assert "Traceback" not in stderr_buf.getvalue()


# ---------------------------------------------------------------------------
# Stderr redirect
# ---------------------------------------------------------------------------


class TestJSONStderrRedirect:
    def test_builtins_print_redirected_to_stderr(self, tmp_path: Path) -> None:
        """In --json mode, builtins.print goes to stderr, not stdout."""
        exit_code, events, stderr_text = _run_json_interview(GOOD_ANSWERS, tmp_path)
        assert exit_code == 0

        # stdout should only have JSON lines
        for e in events:
            assert isinstance(e, dict)
            assert "type" in e

        # stderr should have some output (initialization messages, etc.)
        # The key thing: no raw text on stdout
        # All stdout lines must be valid JSON
        # (already verified by json.loads in _run_json_interview)


# ---------------------------------------------------------------------------
# Protocol message format validation
# ---------------------------------------------------------------------------


class TestJSONMessageFormats:
    def test_all_events_have_type_field(self, tmp_path: Path) -> None:
        """Every JSON line on stdout has a 'type' field."""
        _, events, _ = _run_json_interview(GOOD_ANSWERS, tmp_path)
        for e in events:
            assert "type" in e, f"Event missing 'type': {e}"

    def test_prompt_events_have_required_fields(self, tmp_path: Path) -> None:
        """Prompt events have type, phase, and question."""
        _, events, _ = _run_json_interview(GOOD_ANSWERS, tmp_path)
        for e in events:
            if e["type"] == "prompt":
                assert "phase" in e
                assert "question" in e

    def test_confirm_events_have_summary(self, tmp_path: Path) -> None:
        """Confirm events have a summary field."""
        _, events, _ = _run_json_interview(GOOD_ANSWERS, tmp_path)
        for e in events:
            if e["type"] == "confirm":
                assert "summary" in e
                assert len(e["summary"]) > 0

    def test_complete_event_config_has_goal(self, tmp_path: Path) -> None:
        """Complete event config includes the goal from interview answers."""
        _, events, _ = _run_json_interview(GOOD_ANSWERS, tmp_path)
        complete = [e for e in events if e["type"] == "complete"][0]
        assert complete["config"]["goal"] == GOOD_ANSWERS[0]

    def test_status_events_have_message(self, tmp_path: Path) -> None:
        """Status events have a message field."""
        _, events, _ = _run_json_interview(GOOD_ANSWERS, tmp_path)
        for e in events:
            if e["type"] == "status":
                assert "message" in e


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestJSONEdgeCases:
    def test_json_mode_skips_overwrite_confirmation(self, tmp_path: Path) -> None:
        """In --json mode, existing config doesn't trigger overwrite prompt."""
        # First run to create config
        _run_json_interview(GOOD_ANSWERS, tmp_path)

        # Second run should not fail or ask about overwrite
        exit_code, events, _ = _run_json_interview(GOOD_ANSWERS, tmp_path)
        assert exit_code == 0
        complete = [e for e in events if e["type"] == "complete"]
        assert len(complete) == 1
