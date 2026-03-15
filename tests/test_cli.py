"""Integration tests for the autoagent CLI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from autoagent.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_cli(*args: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run the CLI as a subprocess and return the result."""
    return subprocess.run(
        [sys.executable, "-m", "autoagent.cli", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_creates_project(self, tmp_path: Path) -> None:
        result = run_cli("--project-dir", str(tmp_path), "init")
        assert result.returncode == 0
        assert "Initialized" in result.stdout

        aa_dir = tmp_path / ".autoagent"
        assert aa_dir.is_dir()
        assert (aa_dir / "state.json").is_file()
        assert (aa_dir / "config.json").is_file()
        assert (aa_dir / "pipeline.py").is_file()
        assert (aa_dir / "archive").is_dir()

    def test_init_refuses_reinit(self, tmp_path: Path) -> None:
        # First init succeeds
        r1 = run_cli("--project-dir", str(tmp_path), "init")
        assert r1.returncode == 0

        # Second init fails
        r2 = run_cli("--project-dir", str(tmp_path), "init")
        assert r2.returncode == 1
        assert "already initialized" in r2.stderr


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_after_init(self, tmp_path: Path) -> None:
        run_cli("--project-dir", str(tmp_path), "init")
        result = run_cli("--project-dir", str(tmp_path), "status")
        assert result.returncode == 0
        assert "initialized" in result.stdout
        assert "Current iteration: 0" in result.stdout

    def test_status_uninitialized(self, tmp_path: Path) -> None:
        result = run_cli("--project-dir", str(tmp_path), "status")
        assert result.returncode == 1
        assert "no autoagent project found" in result.stderr


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRun:
    def test_run_no_benchmark_configured(self, tmp_path: Path) -> None:
        """Run fails gracefully when no benchmark is configured."""
        run_cli("--project-dir", str(tmp_path), "init")
        result = run_cli("--project-dir", str(tmp_path), "run")
        assert result.returncode == 1
        assert "no benchmark dataset_path configured" in result.stderr

    def test_run_uninitialized(self, tmp_path: Path) -> None:
        result = run_cli("--project-dir", str(tmp_path), "run")
        assert result.returncode == 1
        assert "no autoagent project found" in result.stderr

    def test_run_max_iterations_help(self) -> None:
        """--max-iterations appears in run help."""
        result = run_cli("run", "--help")
        assert result.returncode == 0
        assert "--max-iterations" in result.stdout


# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------


class TestHelp:
    def test_help_shows_subcommands(self) -> None:
        result = run_cli("--help")
        assert result.returncode == 0
        assert "init" in result.stdout
        assert "status" in result.stdout
        assert "run" in result.stdout


# ---------------------------------------------------------------------------
# --project-dir flag
# ---------------------------------------------------------------------------


class TestProjectDir:
    def test_project_dir_flag(self, tmp_path: Path) -> None:
        """--project-dir routes all commands to the specified directory."""
        subdir = tmp_path / "nested" / "project"
        subdir.mkdir(parents=True)

        r1 = run_cli("--project-dir", str(subdir), "init")
        assert r1.returncode == 0
        assert (subdir / ".autoagent" / "state.json").is_file()

        r2 = run_cli("--project-dir", str(subdir), "status")
        assert r2.returncode == 0
        assert "initialized" in r2.stdout


# ---------------------------------------------------------------------------
# Direct main() calls (no subprocess)
# ---------------------------------------------------------------------------


class TestMainDirect:
    def test_main_no_command_shows_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "autoagent" in captured.out

    def test_main_init_direct(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--project-dir", str(tmp_path), "init"])
        assert exc_info.value.code == 0
        assert (tmp_path / ".autoagent" / "state.json").is_file()
