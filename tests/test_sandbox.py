"""Tests for SandboxRunner with mocked Docker subprocess calls."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from autoagent.sandbox import (
    SandboxResult,
    SandboxRunner,
    _deserialize_pipeline_result,
    serialize_pipeline_result,
)
from autoagent.types import ErrorInfo, MetricsSnapshot, PipelineResult


# ---------------------------------------------------------------------------
# SandboxResult frozen dataclass
# ---------------------------------------------------------------------------


class TestSandboxResult:
    def test_frozen(self):
        sr = SandboxResult(sandbox_used=True, container_id="abc123")
        with pytest.raises(AttributeError):
            sr.sandbox_used = False  # type: ignore[misc]

    def test_defaults(self):
        sr = SandboxResult(sandbox_used=False)
        assert sr.container_id is None
        assert sr.network_policy == "none"
        assert sr.fallback_reason is None
        assert sr.cost_usd == 0.0

    def test_all_fields(self):
        sr = SandboxResult(
            sandbox_used=True,
            container_id="abc123",
            network_policy="none",
            fallback_reason=None,
            cost_usd=0.01,
        )
        assert sr.sandbox_used is True
        assert sr.container_id == "abc123"


# ---------------------------------------------------------------------------
# SandboxRunner.available()
# ---------------------------------------------------------------------------


class TestAvailable:
    @patch("autoagent.sandbox.subprocess.run")
    @patch("autoagent.sandbox.shutil.which", return_value="/usr/bin/docker")
    def test_available_when_docker_present_and_daemon_running(self, mock_which, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "info"], returncode=0, stdout="", stderr=""
        )
        assert SandboxRunner.available() is True
        mock_which.assert_called_once_with("docker")
        mock_run.assert_called_once()

    @patch("autoagent.sandbox.shutil.which", return_value=None)
    def test_unavailable_no_binary(self, mock_which):
        assert SandboxRunner.available() is False
        mock_which.assert_called_once_with("docker")

    @patch("autoagent.sandbox.subprocess.run")
    @patch("autoagent.sandbox.shutil.which", return_value="/usr/bin/docker")
    def test_unavailable_daemon_not_running(self, mock_which, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "info"], returncode=1, stdout="", stderr="Cannot connect"
        )
        assert SandboxRunner.available() is False

    @patch("autoagent.sandbox.subprocess.run")
    @patch("autoagent.sandbox.shutil.which", return_value="/usr/bin/docker")
    def test_unavailable_timeout(self, mock_which, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker info", timeout=30)
        assert SandboxRunner.available() is False


# ---------------------------------------------------------------------------
# SandboxRunner.run() — Docker path
# ---------------------------------------------------------------------------

# A minimal successful container stdout
_CONTAINER_SUCCESS_OUTPUT = json.dumps({
    "output": "hello",
    "metrics": None,
    "success": True,
    "error": None,
    "duration_ms": 42.0,
})


def _make_completed(returncode=0, stdout="", stderr=""):
    """Helper to create CompletedProcess."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestRunWithDocker:
    """Test the Docker execution path with all subprocess calls mocked."""

    @patch("autoagent.sandbox.subprocess.run")
    @patch("autoagent.sandbox.shutil.which", return_value="/usr/bin/docker")
    def test_run_docker_full_lifecycle(self, mock_which, mock_run, tmp_path):
        """Verify docker create → cp (pipeline) → cp (harness) → start → exec → stop → rm sequence."""
        pipeline_file = tmp_path / "pipeline.py"
        pipeline_file.write_text("def run(input_data, primitives): return input_data")

        container_id = "abc123def456"

        # Sequence: info (available check), create, start, cp (pipeline), cp (harness), exec, stop, rm
        mock_run.side_effect = [
            _make_completed(0, "", ""),              # docker info
            _make_completed(0, container_id + "\n"),  # docker create
            _make_completed(0),                       # docker start
            _make_completed(0),                       # docker cp (pipeline)
            _make_completed(0),                       # docker cp (harness)
            _make_completed(0, _CONTAINER_SUCCESS_OUTPUT),  # docker exec
            _make_completed(0),                       # docker stop
            _make_completed(0),                       # docker rm
        ]

        runner = SandboxRunner()
        result = runner.run(pipeline_file, input_data="test")

        assert result.success is True
        assert result.output == "hello"
        assert result.duration_ms == 42.0

        # Verify lifecycle calls
        calls = mock_run.call_args_list
        # docker info
        assert calls[0][0][0][0:2] == ["docker", "info"]
        # docker create with --network=none
        create_args = calls[1][0][0]
        assert "docker" in create_args
        assert "create" in create_args
        assert "--network=none" in create_args
        # docker start
        assert calls[2][0][0][0:2] == ["docker", "start"]
        # docker cp calls
        assert calls[3][0][0][0:2] == ["docker", "cp"]
        assert calls[4][0][0][0:2] == ["docker", "cp"]
        # docker exec
        assert calls[5][0][0][0:2] == ["docker", "exec"]
        # docker stop
        assert "stop" in calls[6][0][0]
        # docker rm
        assert "rm" in calls[7][0][0]

        # SandboxResult metadata
        sr = runner.last_sandbox_result
        assert sr is not None
        assert sr.sandbox_used is True
        assert sr.container_id == container_id
        assert sr.network_policy == "none"

    @patch("autoagent.sandbox.subprocess.run")
    @patch("autoagent.sandbox.shutil.which", return_value="/usr/bin/docker")
    def test_docker_exec_failure(self, mock_which, mock_run, tmp_path):
        """docker exec returning non-zero → PipelineResult with error."""
        pipeline_file = tmp_path / "pipeline.py"
        pipeline_file.write_text("def run(i, p): return i")

        mock_run.side_effect = [
            _make_completed(0),                        # docker info
            _make_completed(0, "cid123\n"),             # docker create
            _make_completed(0),                         # docker start
            _make_completed(0),                         # docker cp (pipeline)
            _make_completed(0),                         # docker cp (harness)
            _make_completed(1, "", "exec error msg"),   # docker exec fails
            _make_completed(0),                         # docker stop
            _make_completed(0),                         # docker rm
        ]

        runner = SandboxRunner()
        result = runner.run(pipeline_file)

        assert result.success is False
        assert result.error is not None
        assert "SandboxExecError" in result.error.type
        assert "exec error msg" in result.error.message

    @patch("autoagent.sandbox.subprocess.run")
    @patch("autoagent.sandbox.shutil.which", return_value="/usr/bin/docker")
    def test_docker_create_failure(self, mock_which, mock_run, tmp_path):
        """docker create failure → SandboxError returned."""
        pipeline_file = tmp_path / "pipeline.py"
        pipeline_file.write_text("def run(i, p): return i")

        mock_run.side_effect = [
            _make_completed(0),                             # docker info
            _make_completed(1, "", "no space on device"),    # docker create fails
        ]

        runner = SandboxRunner()
        result = runner.run(pipeline_file)

        assert result.success is False
        assert result.error is not None
        assert result.error.type == "SandboxError"
        assert "no space on device" in result.error.message


# ---------------------------------------------------------------------------
# SandboxRunner.run() — fallback path
# ---------------------------------------------------------------------------


class TestFallback:
    @patch("autoagent.sandbox.shutil.which", return_value=None)
    def test_fallback_no_docker(self, mock_which, tmp_path):
        """When docker binary missing, delegate to PipelineRunner."""
        pipeline_file = tmp_path / "pipeline.py"
        pipeline_file.write_text("def run(input_data, primitives): return 'fallback_ok'")

        fallback = MagicMock()
        fallback.run.return_value = PipelineResult(
            output="fallback_ok", metrics=None, success=True
        )

        runner = SandboxRunner(fallback_runner=fallback)
        result = runner.run(pipeline_file, input_data="test")

        assert result.success is True
        assert result.output == "fallback_ok"
        fallback.run.assert_called_once()

        sr = runner.last_sandbox_result
        assert sr is not None
        assert sr.sandbox_used is False
        assert sr.fallback_reason is not None
        assert "not found" in sr.fallback_reason

    @patch("autoagent.sandbox.subprocess.run")
    @patch("autoagent.sandbox.shutil.which", return_value="/usr/bin/docker")
    def test_fallback_daemon_not_running(self, mock_which, mock_run, tmp_path):
        """When docker daemon not running, delegate to PipelineRunner."""
        pipeline_file = tmp_path / "pipeline.py"
        pipeline_file.write_text("def run(i, p): return i")

        mock_run.return_value = _make_completed(1, "", "daemon not running")

        fallback = MagicMock()
        fallback.run.return_value = PipelineResult(
            output="ok", metrics=None, success=True
        )

        runner = SandboxRunner(fallback_runner=fallback)
        result = runner.run(pipeline_file)

        assert result.success is True
        fallback.run.assert_called_once()
        assert runner.last_sandbox_result.fallback_reason == "docker daemon not running or not accessible"


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_roundtrip_success(self):
        original = PipelineResult(
            output={"key": "value"},
            metrics=MetricsSnapshot(
                latency_ms=100.0, tokens_in=10, tokens_out=20,
                cost_usd=0.01, model="gpt-4", provider="openai",
                timestamp=1234567890.0,
            ),
            success=True,
            duration_ms=150.0,
        )
        serialized = serialize_pipeline_result(original)
        deserialized = _deserialize_pipeline_result(serialized)

        assert deserialized.success is True
        assert deserialized.output == {"key": "value"}
        assert deserialized.duration_ms == 150.0
        assert deserialized.metrics is not None
        assert deserialized.metrics.latency_ms == 100.0
        assert deserialized.metrics.tokens_in == 10
        assert deserialized.metrics.cost_usd == 0.01
        assert deserialized.metrics.model == "gpt-4"

    def test_roundtrip_error(self):
        original = PipelineResult(
            output=None,
            metrics=None,
            success=False,
            error=ErrorInfo(
                type="RuntimeError",
                message="boom",
                traceback="Traceback...",
            ),
            duration_ms=5.0,
        )
        serialized = serialize_pipeline_result(original)
        deserialized = _deserialize_pipeline_result(serialized)

        assert deserialized.success is False
        assert deserialized.error is not None
        assert deserialized.error.type == "RuntimeError"
        assert deserialized.error.message == "boom"
        assert deserialized.error.traceback == "Traceback..."

    def test_roundtrip_no_metrics_no_error(self):
        original = PipelineResult(
            output="simple", metrics=None, success=True
        )
        serialized = serialize_pipeline_result(original)
        deserialized = _deserialize_pipeline_result(serialized)

        assert deserialized.success is True
        assert deserialized.output == "simple"
        assert deserialized.metrics is None
        assert deserialized.error is None


# ---------------------------------------------------------------------------
# Container reuse (multiple examples, one container)
# ---------------------------------------------------------------------------


class TestContainerReuse:
    @patch("autoagent.sandbox.subprocess.run")
    @patch("autoagent.sandbox.shutil.which", return_value="/usr/bin/docker")
    def test_single_create_per_run(self, mock_which, mock_run, tmp_path):
        """One run() call = one docker create, even with the harness doing multiple execs.

        The current design creates one container per run() call. Multiple examples
        within a single iteration are handled by the harness, not by multiple
        exec calls from the host. Verify we see exactly one create and one exec.
        """
        pipeline_file = tmp_path / "pipeline.py"
        pipeline_file.write_text("def run(i, p): return i")

        mock_run.side_effect = [
            _make_completed(0),                        # docker info
            _make_completed(0, "cid_reuse\n"),          # docker create (one!)
            _make_completed(0),                         # docker start
            _make_completed(0),                         # docker cp (pipeline)
            _make_completed(0),                         # docker cp (harness)
            _make_completed(0, _CONTAINER_SUCCESS_OUTPUT),  # docker exec
            _make_completed(0),                         # docker stop
            _make_completed(0),                         # docker rm
        ]

        runner = SandboxRunner()
        result = runner.run(pipeline_file)

        assert result.success is True

        # Count docker create calls
        create_calls = [
            c for c in mock_run.call_args_list
            if len(c[0]) > 0 and "create" in c[0][0]
        ]
        assert len(create_calls) == 1

    @patch("autoagent.sandbox.subprocess.run")
    @patch("autoagent.sandbox.shutil.which", return_value="/usr/bin/docker")
    def test_cleanup_always_called(self, mock_which, mock_run, tmp_path):
        """Container cleanup (stop + rm) called even when exec fails."""
        pipeline_file = tmp_path / "pipeline.py"
        pipeline_file.write_text("def run(i, p): return i")

        mock_run.side_effect = [
            _make_completed(0),                   # docker info
            _make_completed(0, "cid_cleanup\n"),   # docker create
            _make_completed(0),                    # docker start
            _make_completed(0),                    # docker cp (pipeline)
            _make_completed(0),                    # docker cp (harness)
            _make_completed(1, "", "exec boom"),   # docker exec fails
            _make_completed(0),                    # docker stop
            _make_completed(0),                    # docker rm
        ]

        runner = SandboxRunner()
        result = runner.run(pipeline_file)

        assert result.success is False

        # Verify stop and rm were called
        call_cmds = [c[0][0] for c in mock_run.call_args_list]
        stop_calls = [c for c in call_cmds if "stop" in c]
        rm_calls = [c for c in call_cmds if "rm" in c]
        assert len(stop_calls) == 1
        assert len(rm_calls) == 1


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------


def test_import_clean():
    """Verify clean import of public API."""
    from autoagent.sandbox import SandboxRunner, SandboxResult  # noqa: F811
    assert SandboxRunner is not None
    assert SandboxResult is not None
