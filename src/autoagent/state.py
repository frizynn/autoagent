"""StateManager — disk state layer for .autoagent/ project directory.

Owns reading/writing state.json and config.json atomically,
PID-based lock files for exclusive access, and project initialization.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectState:
    """Current loop state persisted in state.json."""

    version: int = 1
    current_iteration: int = 0
    best_iteration_id: str | None = None
    total_cost_usd: float = 0.0
    phase: str = "initialized"
    started_at: str | None = None
    updated_at: str = ""

    def asdict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for JSON encoding."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectState:
        """Deserialize from a plain dict, ignoring unknown keys."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass(frozen=True)
class ProjectConfig:
    """Project configuration persisted in config.json."""

    version: int = 1
    goal: str = ""
    benchmark: dict[str, Any] = field(default_factory=lambda: {
        "dataset_path": "",
        "scoring_function": "",
    })
    budget_usd: float | None = None
    pipeline_path: str = "pipeline.py"
    search_space: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    metric_priorities: list[str] = field(default_factory=list)

    def asdict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for JSON encoding."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectConfig:
        """Deserialize from a plain dict, ignoring unknown keys."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# Starter pipeline template
# ---------------------------------------------------------------------------

STARTER_PIPELINE = '''\
"""Starter pipeline — replace with your own logic.

This file is loaded by PipelineRunner via compile()+exec().
It must define a module-level ``run(input_data, primitives)`` function
that returns a dict.
"""


def run(input_data, primitives=None):
    """Process *input_data* and return a result dict.

    Parameters
    ----------
    input_data : Any
        The input payload provided by the runner.
    primitives : PrimitivesContext | None
        Optional primitives for LLM calls, embeddings, etc.

    Returns
    -------
    dict
        Must be JSON-serializable.
    """
    return {"echo": input_data}
'''


# ---------------------------------------------------------------------------
# StateManager
# ---------------------------------------------------------------------------


class LockError(RuntimeError):
    """Raised when the state lock cannot be acquired."""


class StateManager:
    """Manages the ``.autoagent/`` project directory.

    Parameters
    ----------
    project_dir : Path | str
        Root directory of the project (parent of ``.autoagent/``).
    experiment : str | None
        Experiment name. When set, all paths resolve under
        ``.autoagent/experiments/<experiment>/`` instead of ``.autoagent/``.
    """

    AUTOAGENT_DIR = ".autoagent"
    STATE_FILE = "state.json"
    CONFIG_FILE = "config.json"
    LOCK_FILE = "state.lock"
    ARCHIVE_DIR = "archive"
    PIPELINE_FILE = "pipeline.py"
    EXPERIMENTS_DIR = "experiments"
    EXPERIMENTS_REGISTRY = "experiments.json"

    def __init__(self, project_dir: Path | str, experiment: str | None = None) -> None:
        self.project_dir = Path(project_dir).resolve()
        self._aa_dir = self.project_dir / self.AUTOAGENT_DIR
        self._experiment = experiment

    # -- paths -------------------------------------------------------------

    @property
    def aa_dir(self) -> Path:
        return self._aa_dir

    @property
    def _data_dir(self) -> Path:
        """Root for state/config/archive — experiment subdir or aa_dir."""
        if self._experiment:
            return self._aa_dir / self.EXPERIMENTS_DIR / self._experiment
        return self._aa_dir

    @property
    def state_path(self) -> Path:
        return self._data_dir / self.STATE_FILE

    @property
    def config_path(self) -> Path:
        return self._data_dir / self.CONFIG_FILE

    @property
    def lock_path(self) -> Path:
        return self._data_dir / self.LOCK_FILE

    @property
    def archive_dir(self) -> Path:
        return self._data_dir / self.ARCHIVE_DIR

    @property
    def pipeline_path(self) -> Path:
        return self._data_dir / self.PIPELINE_FILE

    @property
    def experiments_dir(self) -> Path:
        return self._aa_dir / self.EXPERIMENTS_DIR

    @property
    def experiments_registry_path(self) -> Path:
        return self._aa_dir / self.EXPERIMENTS_REGISTRY

    @property
    def experiment(self) -> str | None:
        return self._experiment

    # -- init --------------------------------------------------------------

    def init_project(self, goal: str = "") -> None:
        """Create the project directory with initial files.

        For experiments, creates ``.autoagent/experiments/<name>/``.
        For legacy mode, creates ``.autoagent/`` with flat layout.

        Raises
        ------
        FileExistsError
            If the target directory already exists.
        """
        data_dir = self._data_dir
        if data_dir.exists():
            raise FileExistsError(
                f"Already initialized: {data_dir}"
            )

        # Ensure parent .autoagent/ exists
        self._aa_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / self.ARCHIVE_DIR).mkdir()

        now = _now_iso()
        state = ProjectState(updated_at=now)
        config = ProjectConfig(goal=goal)

        (data_dir / self.STATE_FILE).write_text(
            json.dumps(state.asdict(), indent=2) + "\n", encoding="utf-8"
        )
        (data_dir / self.CONFIG_FILE).write_text(
            json.dumps(config.asdict(), indent=2) + "\n", encoding="utf-8"
        )
        (data_dir / self.PIPELINE_FILE).write_text(STARTER_PIPELINE, encoding="utf-8")

        # Update experiments registry if this is an experiment
        if self._experiment:
            self._register_experiment(self._experiment, goal)

    # -- read / write ------------------------------------------------------

    def read_state(self) -> ProjectState:
        """Read and deserialize ``state.json``."""
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        return ProjectState.from_dict(data)

    def write_state(self, state: ProjectState) -> None:
        """Atomically write ``state.json`` via temp file + os.replace."""
        _atomic_write_json(self.state_path, state.asdict())

    def read_config(self) -> ProjectConfig:
        """Read and deserialize ``config.json``."""
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        return ProjectConfig.from_dict(data)

    def write_config(self, config: ProjectConfig) -> None:
        """Atomically write ``config.json`` via temp file + os.replace."""
        _atomic_write_json(self.config_path, config.asdict())

    # -- lock protocol -----------------------------------------------------

    def acquire_lock(self) -> None:
        """Acquire an exclusive lock by writing PID + timestamp to ``state.lock``.

        If a lock file exists with a dead PID, it is treated as stale and
        replaced.  If the PID is still alive, :class:`LockError` is raised.
        """
        if self.lock_path.exists():
            try:
                lock_data = json.loads(
                    self.lock_path.read_text(encoding="utf-8")
                )
                pid = lock_data.get("pid")
                if pid is not None and _pid_alive(pid):
                    raise LockError(
                        f"Lock held by active process {pid} "
                        f"(acquired {lock_data.get('acquired_at', '?')})"
                    )
                # Stale lock — fall through and overwrite.
            except (json.JSONDecodeError, KeyError):
                pass  # Corrupt lock file — overwrite.

        lock_data = {
            "pid": os.getpid(),
            "acquired_at": _now_iso(),
        }
        self.lock_path.write_text(
            json.dumps(lock_data, indent=2) + "\n", encoding="utf-8"
        )

    def release_lock(self) -> None:
        """Remove ``state.lock`` if it exists."""
        self.lock_path.unlink(missing_ok=True)

    # -- query -------------------------------------------------------------

    def is_initialized(self) -> bool:
        """Return True if the data directory exists with required files."""
        d = self._data_dir
        return (
            d.is_dir()
            and (d / self.STATE_FILE).is_file()
            and (d / self.CONFIG_FILE).is_file()
            and (d / self.PIPELINE_FILE).is_file()
        )

    # -- experiment management ---------------------------------------------

    def _register_experiment(self, name: str, goal: str = "") -> None:
        """Add an experiment to the registry."""
        registry = self._read_registry()
        experiments = registry.get("experiments", [])
        # Don't duplicate
        if not any(e["name"] == name for e in experiments):
            experiments.append({
                "name": name,
                "goal": goal,
                "created_at": _now_iso(),
            })
        registry["experiments"] = experiments
        registry["active"] = name
        _atomic_write_json(self.experiments_registry_path, registry)

    def _read_registry(self) -> dict[str, Any]:
        """Read the experiments registry, or return empty default."""
        if self.experiments_registry_path.exists():
            try:
                return json.loads(
                    self.experiments_registry_path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError):
                pass
        return {"active": None, "experiments": []}

    def list_experiments(self) -> list[dict[str, Any]]:
        """List all experiments with their state summaries."""
        registry = self._read_registry()
        result = []
        for exp_info in registry.get("experiments", []):
            name = exp_info["name"]
            exp_sm = StateManager(self.project_dir, experiment=name)
            summary: dict[str, Any] = {
                "name": name,
                "goal": exp_info.get("goal", ""),
                "created_at": exp_info.get("created_at", ""),
                "active": registry.get("active") == name,
            }
            if exp_sm.is_initialized():
                try:
                    state = exp_sm.read_state()
                    config = exp_sm.read_config()
                    summary["phase"] = state.phase
                    summary["iteration"] = state.current_iteration
                    summary["best_iteration_id"] = state.best_iteration_id
                    summary["total_cost_usd"] = state.total_cost_usd
                    summary["goal"] = config.goal or summary["goal"]
                except Exception:
                    summary["phase"] = "error"
            result.append(summary)
        return result

    def get_active_experiment(self) -> str | None:
        """Return the name of the currently active experiment."""
        registry = self._read_registry()
        return registry.get("active")

    def set_active_experiment(self, name: str) -> None:
        """Set the active experiment."""
        registry = self._read_registry()
        experiments = registry.get("experiments", [])
        if not any(e["name"] == name for e in experiments):
            raise ValueError(f"Experiment '{name}' not found")
        registry["active"] = name
        _atomic_write_json(self.experiments_registry_path, registry)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _pid_alive(pid: int) -> bool:
    """Check whether *pid* refers to a running process."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it — still alive.
        return True
    return True


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write *data* as JSON to *path* atomically.

    Writes to a temp file in the same directory, then uses ``os.replace``
    for an atomic rename.  This prevents partial/corrupt files on crash.
    """
    content = json.dumps(data, indent=2) + "\n"
    fd = tempfile.NamedTemporaryFile(
        mode="w",
        dir=path.parent,
        suffix=".tmp",
        delete=False,
        encoding="utf-8",
    )
    try:
        fd.write(content)
        fd.flush()
        os.fsync(fd.fileno())
        fd.close()
        os.replace(fd.name, path)
    except BaseException:
        fd.close()
        # Clean up temp file on failure.
        try:
            os.unlink(fd.name)
        except OSError:
            pass
        raise
