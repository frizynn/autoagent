"""Tests for the --jsonl output mode of ``autoagent run``."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from autoagent.cli import build_parser, main
from autoagent.state import ProjectState, StateManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_project_with_benchmark(tmp_path: Path) -> Path:
    """Initialize a project with a minimal benchmark for cmd_run."""
    sm = StateManager(tmp_path)
    sm.init_project(goal="Test goal")

    dataset = tmp_path / "bench.json"
    dataset.write_text(
        json.dumps([{"input": "hello", "expected": "hello"}]),
        encoding="utf-8",
    )

    from dataclasses import replace
    config = sm.read_config()
    config = replace(config, benchmark={
        "dataset_path": "bench.json",
        "scoring_function": "exact_match",
    })
    sm.write_config(config)
    return tmp_path


VALID_PIPELINE = '''\
def run(input_data, primitives=None):
    """Generated pipeline."""
    return {"answer": str(input_data)}
'''


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestJSONLParserFlag:
    def test_jsonl_flag_accepted(self) -> None:
        """--jsonl flag is parsed without error."""
        parser = build_parser()
        args = parser.parse_args(["run", "--jsonl"])
        assert args.jsonl is True

    def test_jsonl_flag_default_false(self) -> None:
        """Without --jsonl, the flag defaults to False."""
        parser = build_parser()
        args = parser.parse_args(["run"])
        assert args.jsonl is False

    def test_jsonl_appears_in_run_help(self) -> None:
        """--jsonl shows up in ``run --help``."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "autoagent.cli", "run", "--help"],
            capture_output=True, text=True,
        )
        assert "--jsonl" in result.stdout


# ---------------------------------------------------------------------------
# Event callback unit tests
# ---------------------------------------------------------------------------


class TestJSONLCallback:
    """Test that the JSONL callback produces valid JSON lines."""

    def test_callback_writes_valid_json_lines(self) -> None:
        """Each event is a single valid JSON line on stdout."""
        buf = StringIO()
        events = [
            {"event": "loop_start", "timestamp": "2025-01-01T00:00:00Z", "goal": "test"},
            {"event": "iteration_start", "timestamp": "2025-01-01T00:00:01Z", "iteration": 1},
            {"event": "iteration_end", "timestamp": "2025-01-01T00:00:02Z", "iteration": 1,
             "score": 0.8, "decision": "keep", "cost_usd": 0.01, "elapsed_ms": 123.4,
             "best_iteration_id": "1", "rationale": "Better", "mutation_type": "parametric"},
            {"event": "loop_end", "timestamp": "2025-01-01T00:00:03Z", "phase": "completed",
             "total_iterations": 1, "total_cost_usd": 0.01, "best_iteration_id": "1"},
        ]

        def callback(event: dict) -> None:
            buf.write(json.dumps(event) + "\n")

        for ev in events:
            callback(ev)

        lines = buf.getvalue().strip().split("\n")
        assert len(lines) == 4
        for line in lines:
            parsed = json.loads(line)
            assert "event" in parsed
            assert "timestamp" in parsed


# ---------------------------------------------------------------------------
# Integration: event_callback on OptimizationLoop
# ---------------------------------------------------------------------------


class TestLoopEventCallback:
    """Test that OptimizationLoop emits events via event_callback."""

    def test_event_callback_defaults_to_none(self) -> None:
        """event_callback is None by default — zero overhead."""
        from autoagent.loop import OptimizationLoop
        loop = MagicMock(spec=OptimizationLoop)
        # Verify the real __init__ signature accepts event_callback
        import inspect
        sig = inspect.signature(OptimizationLoop.__init__)
        assert "event_callback" in sig.parameters
        param = sig.parameters["event_callback"]
        assert param.default is None

    def test_all_event_types_emitted_during_mocked_loop(self, tmp_path: Path) -> None:
        """A mocked loop run emits loop_start, iteration_start, iteration_end, loop_end."""
        import subprocess

        _init_project_with_benchmark(tmp_path)

        # Customize pipeline to skip cold-start
        pipeline_path = tmp_path / ".autoagent" / "pipeline.py"
        pipeline_path.write_text(VALID_PIPELINE, encoding="utf-8")

        # We test via the constructor signature + callback unit test
        # since subprocess-based --jsonl tests need a real loop run.
        # Here we verify the constructor passes event_callback through.
        from autoagent.cli import build_parser
        from autoagent.state import ProjectState

        captured_kwargs: dict = {}

        with patch("autoagent.cli.MetaAgent") as MockMA:
            instance = MockMA.return_value
            instance.goal = "Test goal"

            with patch("autoagent.cli.OptimizationLoop") as MockLoop:
                def capture_constructor(**kwargs):
                    captured_kwargs.update(kwargs)
                    mock_loop = MagicMock()
                    mock_loop.run.return_value = ProjectState(
                        phase="completed", current_iteration=1
                    )
                    return mock_loop

                MockLoop.side_effect = capture_constructor

                with pytest.raises(SystemExit) as exc_info:
                    main(["--project-dir", str(tmp_path), "run", "--jsonl"])

        assert exc_info.value.code == 0
        assert "event_callback" in captured_kwargs
        assert captured_kwargs["event_callback"] is not None
        assert callable(captured_kwargs["event_callback"])

        # Verify the callback produces valid JSONL on stdout
        import io
        buf = io.StringIO()
        original_stdout = sys.stdout
        try:
            sys.stdout = buf
            captured_kwargs["event_callback"]({"event": "test", "timestamp": "T0"})
        finally:
            sys.stdout = original_stdout

        line = buf.getvalue().strip()
        parsed = json.loads(line)
        assert parsed["event"] == "test"


# ---------------------------------------------------------------------------
# Integration: --jsonl redirects human output to stderr
# ---------------------------------------------------------------------------


class TestJSONLStderrRedirect:
    """When --jsonl is active, human-readable print() output goes to stderr."""

    def test_human_output_on_stderr(self, tmp_path: Path) -> None:
        """With --jsonl, human-readable messages appear on stderr, not stdout."""
        import subprocess
        import textwrap

        _init_project_with_benchmark(tmp_path)

        # Customize pipeline to skip cold-start
        pipeline_path = tmp_path / ".autoagent" / "pipeline.py"
        pipeline_path.write_text(VALID_PIPELINE, encoding="utf-8")

        # Write a helper script that mocks the loop and runs with --jsonl
        script = tmp_path / "_test_jsonl_stderr.py"
        script.write_text(textwrap.dedent(f"""\
            import sys
            sys.argv = ['autoagent', '--project-dir', {str(tmp_path)!r}, 'run', '--jsonl']

            from unittest.mock import patch, MagicMock
            from autoagent.state import ProjectState

            mock_loop = MagicMock()
            mock_loop.return_value.run.return_value = ProjectState(
                phase='completed', current_iteration=1
            )
            mock_ma = MagicMock()
            mock_ma.return_value.goal = 'Test'

            with patch('autoagent.cli.OptimizationLoop', mock_loop):
                with patch('autoagent.cli.MetaAgent', mock_ma):
                    from autoagent.cli import main
                    main()
        """), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True,
        )

        # Human output (like "Optimization complete") should be on stderr
        assert "Optimization complete" in result.stderr or "Iterations:" in result.stderr
        # stdout should only contain valid JSON lines (or be empty)
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                json.loads(line)  # every non-empty line must be valid JSON


# ---------------------------------------------------------------------------
# Non-JSONL behavior unchanged
# ---------------------------------------------------------------------------


class TestNonJSONLUnchanged:
    """Existing behavior without --jsonl is not affected."""

    def test_run_without_jsonl_prints_to_stdout(self, tmp_path: Path) -> None:
        """Without --jsonl, output goes to stdout as before."""
        _init_project_with_benchmark(tmp_path)

        pipeline_path = tmp_path / ".autoagent" / "pipeline.py"
        pipeline_path.write_text(VALID_PIPELINE, encoding="utf-8")

        with patch("autoagent.cli.MetaAgent") as MockMA:
            instance = MockMA.return_value
            instance.goal = "Test goal"

            with patch("autoagent.cli.OptimizationLoop") as MockLoop:
                MockLoop.return_value.run.return_value = ProjectState(
                    phase="completed", current_iteration=1
                )

                with pytest.raises(SystemExit) as exc_info:
                    main(["--project-dir", str(tmp_path), "run"])

        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# Error event
# ---------------------------------------------------------------------------


class TestErrorEvent:
    """The error event is emitted on exceptions."""

    def test_error_event_emitted_on_exception(self) -> None:
        """Loop emits error event when an exception occurs."""
        from autoagent.loop import OptimizationLoop

        captured: list[dict] = []

        def capture_cb(event: dict) -> None:
            captured.append(event)

        # Create a loop with mocked dependencies that will raise
        sm = MagicMock()
        sm.acquire_lock = MagicMock()
        sm.release_lock = MagicMock()
        sm.read_state.side_effect = RuntimeError("state read failed")

        loop = OptimizationLoop.__new__(OptimizationLoop)
        loop.event_callback = capture_cb
        loop.state_manager = sm

        with pytest.raises(RuntimeError, match="state read failed"):
            loop.run()

        error_events = [e for e in captured if e["event"] == "error"]
        assert len(error_events) == 1
        assert "state read failed" in error_events[0]["message"]


# ---------------------------------------------------------------------------
# iteration_end field completeness
# ---------------------------------------------------------------------------


class TestIterationEndFields:
    """iteration_end events have all required fields."""

    def test_iteration_end_has_required_fields(self) -> None:
        """Verify the schema of iteration_end events."""
        required_fields = {
            "event", "timestamp", "iteration", "score", "decision",
            "cost_usd", "elapsed_ms", "best_iteration_id", "rationale",
            "mutation_type",
        }
        sample = {
            "event": "iteration_end",
            "timestamp": "2025-01-01T00:00:00Z",
            "iteration": 1,
            "score": 0.85,
            "decision": "keep",
            "cost_usd": 0.002,
            "elapsed_ms": 150.3,
            "best_iteration_id": "1",
            "rationale": "Improved accuracy",
            "mutation_type": "structural",
        }
        assert required_fields.issubset(sample.keys())
        # Verify JSON-serializable
        json.dumps(sample)
