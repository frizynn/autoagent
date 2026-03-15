"""Tests for StateManager — atomic writes, lock protocol, init, round-trips."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from autoagent.state import (
    STARTER_PIPELINE,
    LockError,
    ProjectConfig,
    ProjectState,
    StateManager,
)


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """Return a fresh temporary directory to use as project root."""
    return tmp_path


@pytest.fixture()
def mgr(project_dir: Path) -> StateManager:
    """Return a StateManager pointed at a fresh temp directory."""
    return StateManager(project_dir)


# ---------------------------------------------------------------------------
# init_project
# ---------------------------------------------------------------------------


class TestInitProject:
    def test_creates_all_expected_files(self, mgr: StateManager) -> None:
        mgr.init_project(goal="test goal")

        assert mgr.aa_dir.is_dir()
        assert mgr.state_path.is_file()
        assert mgr.config_path.is_file()
        assert mgr.pipeline_path.is_file()
        assert mgr.archive_dir.is_dir()

        # Verify state.json content
        state = json.loads(mgr.state_path.read_text())
        assert state["version"] == 1
        assert state["current_iteration"] == 0
        assert state["phase"] == "initialized"

        # Verify config.json content
        config = json.loads(mgr.config_path.read_text())
        assert config["version"] == 1
        assert config["goal"] == "test goal"
        assert config["pipeline_path"] == "pipeline.py"

        # Verify pipeline.py is the starter template
        assert mgr.pipeline_path.read_text() == STARTER_PIPELINE

    def test_raises_on_existing_autoagent(self, mgr: StateManager) -> None:
        mgr.init_project()
        with pytest.raises(FileExistsError, match="(?i)already initialized"):
            mgr.init_project()

    def test_default_goal_is_empty(self, mgr: StateManager) -> None:
        mgr.init_project()
        config = mgr.read_config()
        assert config.goal == ""


# ---------------------------------------------------------------------------
# State round-trip
# ---------------------------------------------------------------------------


class TestStateRoundTrip:
    def test_write_read_returns_equal(self, mgr: StateManager) -> None:
        mgr.init_project()
        state = ProjectState(
            version=1,
            current_iteration=5,
            best_iteration_id="iter-003",
            total_cost_usd=1.23,
            phase="running",
            started_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-03-14T12:00:00+00:00",
        )
        mgr.write_state(state)
        loaded = mgr.read_state()
        assert loaded == state

    def test_from_dict_ignores_unknown_keys(self) -> None:
        data = {"version": 1, "phase": "done", "extra_field": True, "updated_at": "t"}
        state = ProjectState.from_dict(data)
        assert state.phase == "done"
        assert not hasattr(state, "extra_field")


# ---------------------------------------------------------------------------
# Config round-trip
# ---------------------------------------------------------------------------


class TestConfigRoundTrip:
    def test_write_read_returns_equal(self, mgr: StateManager) -> None:
        mgr.init_project()
        config = ProjectConfig(
            version=1,
            goal="improve accuracy",
            benchmark={"dataset_path": "/data/test.csv", "scoring_function": "f1"},
            budget_usd=10.0,
            pipeline_path="pipeline.py",
        )
        mgr.write_config(config)
        loaded = mgr.read_config()
        assert loaded == config

    def test_from_dict_ignores_unknown_keys(self) -> None:
        data = {"version": 1, "goal": "x", "unknown": 42}
        config = ProjectConfig.from_dict(data)
        assert config.goal == "x"


# ---------------------------------------------------------------------------
# Atomic write safety
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_temp_file_used_for_state_write(self, mgr: StateManager) -> None:
        """Verify that write_state creates a temp file and uses os.replace."""
        mgr.init_project()
        state = mgr.read_state()

        with mock.patch("autoagent.state.os.replace", wraps=os.replace) as mock_replace:
            mgr.write_state(state)
            mock_replace.assert_called_once()
            # First arg is the temp file, second is the target
            args = mock_replace.call_args[0]
            assert Path(args[1]) == mgr.state_path

    def test_temp_file_used_for_config_write(self, mgr: StateManager) -> None:
        """Verify that write_config creates a temp file and uses os.replace."""
        mgr.init_project()
        config = mgr.read_config()

        with mock.patch("autoagent.state.os.replace", wraps=os.replace) as mock_replace:
            mgr.write_config(config)
            mock_replace.assert_called_once()

    def test_crash_leaves_original_intact(self, mgr: StateManager) -> None:
        """Simulate a crash during write — original file should be unchanged."""
        mgr.init_project()
        original_state = mgr.read_state()

        # Make os.replace raise to simulate crash after temp write
        with mock.patch("autoagent.state.os.replace", side_effect=OSError("simulated crash")):
            with pytest.raises(OSError, match="simulated crash"):
                new_state = ProjectState(
                    current_iteration=99, updated_at="crash", phase="boom"
                )
                mgr.write_state(new_state)

        # Original file should be untouched
        assert mgr.read_state() == original_state

        # No temp files should be left behind
        tmp_files = list(mgr.aa_dir.glob("*.tmp"))
        assert tmp_files == []


# ---------------------------------------------------------------------------
# Lock protocol
# ---------------------------------------------------------------------------


class TestLockProtocol:
    def test_acquire_release_cycle(self, mgr: StateManager) -> None:
        mgr.init_project()
        mgr.acquire_lock()
        assert mgr.lock_path.exists()

        lock_data = json.loads(mgr.lock_path.read_text())
        assert lock_data["pid"] == os.getpid()
        assert "acquired_at" in lock_data

        mgr.release_lock()
        assert not mgr.lock_path.exists()

    def test_release_idempotent(self, mgr: StateManager) -> None:
        mgr.init_project()
        mgr.release_lock()  # no lock exists — should not raise
        mgr.acquire_lock()
        mgr.release_lock()
        mgr.release_lock()  # already released — should not raise

    def test_acquire_fails_when_held_by_live_process(self, mgr: StateManager) -> None:
        mgr.init_project()
        mgr.acquire_lock()
        # Current process holds the lock — a second acquire should fail
        with pytest.raises(LockError, match="Lock held by active process"):
            mgr.acquire_lock()
        mgr.release_lock()

    def test_stale_lock_with_dead_pid(self, mgr: StateManager) -> None:
        """Write a lock with a PID that doesn't exist, then acquire should succeed."""
        mgr.init_project()

        # Use a PID that's almost certainly dead
        dead_pid = _find_dead_pid()
        lock_data = {"pid": dead_pid, "acquired_at": "2020-01-01T00:00:00+00:00"}
        mgr.lock_path.write_text(json.dumps(lock_data), encoding="utf-8")

        # Should succeed — stale lock is overwritten
        mgr.acquire_lock()
        new_lock = json.loads(mgr.lock_path.read_text())
        assert new_lock["pid"] == os.getpid()
        mgr.release_lock()

    def test_corrupt_lock_file_overwritten(self, mgr: StateManager) -> None:
        mgr.init_project()
        mgr.lock_path.write_text("not json at all")
        mgr.acquire_lock()
        assert json.loads(mgr.lock_path.read_text())["pid"] == os.getpid()
        mgr.release_lock()


# ---------------------------------------------------------------------------
# is_initialized
# ---------------------------------------------------------------------------


class TestIsInitialized:
    def test_false_for_empty_dir(self, mgr: StateManager) -> None:
        assert mgr.is_initialized() is False

    def test_true_after_init(self, mgr: StateManager) -> None:
        mgr.init_project()
        assert mgr.is_initialized() is True

    def test_false_if_state_missing(self, mgr: StateManager) -> None:
        mgr.init_project()
        mgr.state_path.unlink()
        assert mgr.is_initialized() is False

    def test_false_if_config_missing(self, mgr: StateManager) -> None:
        mgr.init_project()
        mgr.config_path.unlink()
        assert mgr.is_initialized() is False

    def test_false_if_pipeline_missing(self, mgr: StateManager) -> None:
        mgr.init_project()
        mgr.pipeline_path.unlink()
        assert mgr.is_initialized() is False


# ---------------------------------------------------------------------------
# Starter pipeline loadability
# ---------------------------------------------------------------------------


class TestStarterPipeline:
    def test_defines_run_function(self) -> None:
        """Starter pipeline must define run() that returns a dict."""
        namespace: dict[str, object] = {}
        exec(compile(STARTER_PIPELINE, "<pipeline>", "exec"), namespace)
        assert callable(namespace["run"])

    def test_run_returns_dict(self) -> None:
        namespace: dict[str, object] = {}
        exec(compile(STARTER_PIPELINE, "<pipeline>", "exec"), namespace)
        result = namespace["run"]("hello")
        assert isinstance(result, dict)
        assert result == {"echo": "hello"}

    def test_run_accepts_primitives_arg(self) -> None:
        """run() must accept optional primitives arg for PipelineRunner compat."""
        namespace: dict[str, object] = {}
        exec(compile(STARTER_PIPELINE, "<pipeline>", "exec"), namespace)
        result = namespace["run"]("data", None)
        assert result == {"echo": "data"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_dead_pid() -> int:
    """Find a PID that is not currently in use."""
    # Start high to avoid colliding with real processes
    for pid in range(99990, 99999):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return pid
        except PermissionError:
            continue
    # Fallback — extremely unlikely to reach here
    return 99999
