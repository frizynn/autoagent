"""Monotonic archive — stores every pipeline iteration on disk.

Each iteration produces two files in ``.autoagent/archive/``:
- ``NNN-{keep|discard}.json`` — full entry with metrics, diff, rationale
- ``NNN-pipeline.py`` — verbatim pipeline source snapshot

The archive is append-only: no deletion, no mutation of existing entries.
Iteration IDs are derived by scanning existing filenames so they survive
crashes and restarts.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from autoagent.evaluation import EvaluationResult, ExampleResult
from autoagent.state import _atomic_write_json
from autoagent.types import MetricsSnapshot


# ---------------------------------------------------------------------------
# Deserialization helpers
# ---------------------------------------------------------------------------

def _metrics_snapshot_from_dict(d: dict[str, Any] | None) -> MetricsSnapshot | None:
    """Reconstruct a ``MetricsSnapshot`` from a plain dict (or None)."""
    if d is None:
        return None
    return MetricsSnapshot(
        latency_ms=d["latency_ms"],
        tokens_in=d["tokens_in"],
        tokens_out=d["tokens_out"],
        cost_usd=d["cost_usd"],
        model=d.get("model", ""),
        provider=d.get("provider", ""),
        timestamp=d.get("timestamp", 0.0),
        custom_metrics=d.get("custom_metrics", {}),
    )


def _example_result_from_dict(d: dict[str, Any]) -> ExampleResult:
    """Reconstruct an ``ExampleResult`` from a plain dict."""
    return ExampleResult(
        example_id=d["example_id"],
        score=d["score"],
        success=d["success"],
        error=d.get("error"),
        duration_ms=d.get("duration_ms", 0.0),
        metrics=_metrics_snapshot_from_dict(d.get("metrics")),
    )


def _evaluation_result_from_dict(d: dict[str, Any]) -> EvaluationResult:
    """Reconstruct an ``EvaluationResult`` with nested types from a plain dict."""
    per_example = [_example_result_from_dict(ex) for ex in d["per_example_results"]]
    return EvaluationResult(
        primary_score=d["primary_score"],
        per_example_results=per_example,
        metrics=_metrics_snapshot_from_dict(d.get("metrics")),
        benchmark_id=d["benchmark_id"],
        duration_ms=d["duration_ms"],
        num_examples=d["num_examples"],
        num_failures=d["num_failures"],
    )


# ---------------------------------------------------------------------------
# ArchiveEntry
# ---------------------------------------------------------------------------

_ENTRY_FILENAME_RE = re.compile(r"^(\d+)-(keep|discard)\.json$")
_PIPELINE_FILENAME_RE = re.compile(r"^(\d+)-pipeline\.py$")


@dataclass(frozen=True)
class ArchiveEntry:
    """A single archived iteration — immutable once written.

    ``evaluation_result`` is stored as a dict for JSON compatibility but
    can be accessed as a reconstructed ``EvaluationResult`` via
    ``evaluation_result_obj``.
    """

    iteration_id: int
    timestamp: float
    pipeline_diff: str
    evaluation_result: dict[str, Any]
    rationale: str
    decision: str  # "keep" or "discard"
    parent_iteration_id: int | None = None
    mutation_type: str | None = None
    tla_verification: dict[str, Any] | None = None
    pareto_evaluation: dict[str, Any] | None = None
    leakage_check: dict[str, Any] | None = None

    def asdict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for JSON encoding."""
        return asdict(self)

    @property
    def evaluation_result_obj(self) -> EvaluationResult:
        """Reconstruct the full ``EvaluationResult`` object graph."""
        return _evaluation_result_from_dict(self.evaluation_result)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ArchiveEntry:
        """Deserialize from a plain dict."""
        return cls(
            iteration_id=d["iteration_id"],
            timestamp=d["timestamp"],
            pipeline_diff=d["pipeline_diff"],
            evaluation_result=d["evaluation_result"],
            rationale=d["rationale"],
            decision=d["decision"],
            parent_iteration_id=d.get("parent_iteration_id"),
            mutation_type=d.get("mutation_type"),
            tla_verification=d.get("tla_verification"),
            pareto_evaluation=d.get("pareto_evaluation"),
            leakage_check=d.get("leakage_check"),
        )


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

class Archive:
    """Monotonic archive of pipeline iterations stored on disk.

    Files live under *archive_dir*:

    - ``NNN-{keep|discard}.json`` — serialized :class:`ArchiveEntry`
    - ``NNN-pipeline.py`` — verbatim pipeline source snapshot

    Where NNN is a zero-padded (3+ digit) iteration ID.
    """

    def __init__(self, archive_dir: Path | str) -> None:
        self._dir = Path(archive_dir)

    @property
    def archive_dir(self) -> Path:
        return self._dir

    # -- ID management -----------------------------------------------------

    def _next_iteration_id(self) -> int:
        """Derive next iteration ID by scanning existing filenames.

        Returns max existing ID + 1, or 1 if the directory is empty.
        """
        max_id = 0
        if self._dir.exists():
            for name in os.listdir(self._dir):
                m = _ENTRY_FILENAME_RE.match(name)
                if m:
                    max_id = max(max_id, int(m.group(1)))
        return max_id + 1

    # -- write -------------------------------------------------------------

    def add(
        self,
        pipeline_source: str,
        evaluation_result: EvaluationResult,
        rationale: str,
        decision: str,
        parent_iteration_id: int | None = None,
        baseline_source: str | None = None,
        mutation_type: str | None = None,
        tla_verification: dict[str, Any] | None = None,
        pareto_evaluation: dict[str, Any] | None = None,
        leakage_check: dict[str, Any] | None = None,
    ) -> ArchiveEntry:
        """Archive one iteration atomically.

        Writes ``NNN-pipeline.py`` (source snapshot) and
        ``NNN-{decision}.json`` (entry with diff, metrics, rationale).

        Parameters
        ----------
        pipeline_source:
            Current pipeline source code to snapshot.
        evaluation_result:
            Full evaluation result (will be serialized via ``asdict``).
        rationale:
            Human/agent-readable explanation for the decision.
        decision:
            ``"keep"`` or ``"discard"``.
        parent_iteration_id:
            ID of the parent iteration (for computing diff). ``None`` for
            the first iteration.
        baseline_source:
            Pipeline source to diff against when there's no parent
            (first iteration). Ignored if parent_iteration_id is set.
        """
        if decision not in ("keep", "discard"):
            raise ValueError(f"decision must be 'keep' or 'discard', got {decision!r}")

        self._dir.mkdir(parents=True, exist_ok=True)

        iteration_id = self._next_iteration_id()
        pad = max(3, len(str(iteration_id)))
        id_str = str(iteration_id).zfill(pad)

        # Compute diff from parent snapshot or baseline
        if parent_iteration_id is not None:
            parent_pad = max(3, len(str(parent_iteration_id)))
            parent_pipeline = self._dir / f"{str(parent_iteration_id).zfill(parent_pad)}-pipeline.py"
            if parent_pipeline.exists():
                old_source = parent_pipeline.read_text(encoding="utf-8")
            else:
                old_source = ""
        elif baseline_source is not None:
            old_source = baseline_source
        else:
            old_source = ""

        diff_lines = list(difflib.unified_diff(
            old_source.splitlines(keepends=True),
            pipeline_source.splitlines(keepends=True),
            fromfile="parent/pipeline.py",
            tofile="current/pipeline.py",
        ))
        pipeline_diff = "".join(diff_lines)

        # Write pipeline snapshot atomically
        pipeline_path = self._dir / f"{id_str}-pipeline.py"
        _atomic_write_text(pipeline_path, pipeline_source)

        # Build entry
        entry = ArchiveEntry(
            iteration_id=iteration_id,
            timestamp=time.time(),
            pipeline_diff=pipeline_diff,
            evaluation_result=asdict(evaluation_result),
            rationale=rationale,
            decision=decision,
            parent_iteration_id=parent_iteration_id,
            mutation_type=mutation_type,
            tla_verification=tla_verification,
            pareto_evaluation=pareto_evaluation,
            leakage_check=leakage_check,
        )

        # Write entry JSON atomically
        entry_path = self._dir / f"{id_str}-{decision}.json"
        _atomic_write_json(entry_path, entry.asdict())

        return entry

    # -- read --------------------------------------------------------------

    def get(self, iteration_id: int) -> ArchiveEntry:
        """Load a single entry by iteration ID.

        Raises ``FileNotFoundError`` if the entry doesn't exist.
        """
        pad = max(3, len(str(iteration_id)))
        id_str = str(iteration_id).zfill(pad)

        # Try both decisions
        for decision in ("keep", "discard"):
            path = self._dir / f"{id_str}-{decision}.json"
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return ArchiveEntry.from_dict(data)

        raise FileNotFoundError(
            f"No archive entry with iteration_id={iteration_id} "
            f"in {self._dir}"
        )

    def _load_all(self) -> list[ArchiveEntry]:
        """Load all archive entries from disk."""
        entries: list[ArchiveEntry] = []
        if not self._dir.exists():
            return entries

        for name in sorted(os.listdir(self._dir)):
            m = _ENTRY_FILENAME_RE.match(name)
            if m:
                path = self._dir / name
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    entries.append(ArchiveEntry.from_dict(data))
                except (json.JSONDecodeError, KeyError) as exc:
                    raise ValueError(
                        f"Corrupted archive entry {name}: {exc}"
                    ) from exc

        return entries

    # -- query -------------------------------------------------------------

    def query(
        self,
        decision: str | None = None,
        sort_by: str | None = None,
        ascending: bool = True,
        limit: int | None = None,
    ) -> list[ArchiveEntry]:
        """Query archive entries with optional filtering and sorting.

        Parameters
        ----------
        decision:
            Filter to ``"keep"`` or ``"discard"`` entries only.
        sort_by:
            Sort by a field in the evaluation result (e.g. ``"primary_score"``,
            ``"cost_usd"``). Metrics fields are looked up in
            ``evaluation_result["metrics"]``.
        ascending:
            Sort order. Default is ascending (lowest first).
        limit:
            Maximum number of entries to return.
        """
        entries = self._load_all()

        if decision is not None:
            entries = [e for e in entries if e.decision == decision]

        if sort_by is not None:
            entries.sort(
                key=lambda e: _extract_sort_key(e, sort_by),
                reverse=not ascending,
            )

        if limit is not None:
            entries = entries[:limit]

        return entries

    def best(self, metric: str = "primary_score") -> ArchiveEntry | None:
        """Return the entry with the highest value for *metric*."""
        entries = self.query(sort_by=metric, ascending=False, limit=1)
        return entries[0] if entries else None

    def worst(self, metric: str = "primary_score") -> ArchiveEntry | None:
        """Return the entry with the lowest value for *metric*."""
        entries = self.query(sort_by=metric, ascending=True, limit=1)
        return entries[0] if entries else None

    def recent(self, n: int = 5) -> list[ArchiveEntry]:
        """Return the *n* most recent entries (by iteration ID, newest first)."""
        entries = self._load_all()
        entries.sort(key=lambda e: e.iteration_id, reverse=True)
        return entries[:n]

    def __len__(self) -> int:
        """Count entries without loading them."""
        if not self._dir.exists():
            return 0
        return sum(
            1 for name in os.listdir(self._dir)
            if _ENTRY_FILENAME_RE.match(name)
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_sort_key(entry: ArchiveEntry, field_name: str) -> float:
    """Extract a numeric sort key from an archive entry.

    Looks up *field_name* first in the top-level evaluation_result dict,
    then in the nested metrics dict.
    """
    er = entry.evaluation_result
    if field_name in er:
        return float(er[field_name])
    metrics = er.get("metrics")
    if metrics and field_name in metrics:
        return float(metrics[field_name])
    return 0.0


def _atomic_write_text(path: Path, content: str) -> None:
    """Write *content* to *path* atomically via temp file + os.replace."""
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
        try:
            os.unlink(fd.name)
        except OSError:
            pass
        raise
