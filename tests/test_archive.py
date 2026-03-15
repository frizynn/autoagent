"""Tests for the monotonic archive module."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from autoagent.archive import Archive, ArchiveEntry, _evaluation_result_from_dict
from autoagent.evaluation import EvaluationResult, ExampleResult
from autoagent.types import MetricsSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_metrics(cost_usd: float = 0.01, latency_ms: float = 100.0) -> MetricsSnapshot:
    return MetricsSnapshot(
        latency_ms=latency_ms,
        tokens_in=50,
        tokens_out=30,
        cost_usd=cost_usd,
        model="test-model",
        provider="test",
        timestamp=time.time(),
    )


def _make_eval_result(
    primary_score: float = 0.8,
    cost_usd: float = 0.01,
    num_examples: int = 2,
) -> EvaluationResult:
    metrics = _make_metrics(cost_usd=cost_usd)
    examples = [
        ExampleResult(
            example_id=f"ex_{i}",
            score=primary_score,
            success=primary_score >= 1.0,
            error=None if primary_score >= 1.0 else "partial",
            duration_ms=50.0,
            metrics=_make_metrics(cost_usd=cost_usd / max(num_examples, 1)),
        )
        for i in range(num_examples)
    ]
    return EvaluationResult(
        primary_score=primary_score,
        per_example_results=examples,
        metrics=metrics,
        benchmark_id="test-bench",
        duration_ms=200.0,
        num_examples=num_examples,
        num_failures=0 if primary_score >= 1.0 else num_examples,
    )


PIPELINE_V1 = 'def run(x, p=None):\n    return {"echo": x}\n'
PIPELINE_V2 = 'def run(x, p=None):\n    return {"upper": x.upper()}\n'
PIPELINE_V3 = 'def run(x, p=None):\n    return {"lower": x.lower()}\n'
BASELINE = 'def run(x, p=None):\n    return {}\n'


@pytest.fixture
def archive(tmp_path: Path) -> Archive:
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    return Archive(archive_dir)


# ---------------------------------------------------------------------------
# Empty archive
# ---------------------------------------------------------------------------

class TestEmptyArchive:
    def test_len_zero(self, archive: Archive) -> None:
        assert len(archive) == 0

    def test_query_returns_empty(self, archive: Archive) -> None:
        assert archive.query() == []
        assert archive.query(decision="keep") == []

    def test_best_returns_none(self, archive: Archive) -> None:
        assert archive.best() is None

    def test_worst_returns_none(self, archive: Archive) -> None:
        assert archive.worst() is None

    def test_recent_returns_empty(self, archive: Archive) -> None:
        assert archive.recent() == []


# ---------------------------------------------------------------------------
# Add + get round-trip
# ---------------------------------------------------------------------------

class TestAddAndGet:
    def test_add_returns_entry_with_correct_fields(self, archive: Archive) -> None:
        er = _make_eval_result(primary_score=0.9, cost_usd=0.05)
        entry = archive.add(
            pipeline_source=PIPELINE_V1,
            evaluation_result=er,
            rationale="first try",
            decision="keep",
            baseline_source=BASELINE,
        )
        assert entry.iteration_id == 1
        assert entry.decision == "keep"
        assert entry.rationale == "first try"
        assert entry.parent_iteration_id is None
        assert entry.timestamp > 0
        assert entry.pipeline_diff != ""  # diff against baseline

    def test_get_round_trips_all_fields(self, archive: Archive) -> None:
        er = _make_eval_result(primary_score=0.75, cost_usd=0.02)
        added = archive.add(
            pipeline_source=PIPELINE_V1,
            evaluation_result=er,
            rationale="checking round-trip",
            decision="discard",
            baseline_source=BASELINE,
        )
        loaded = archive.get(added.iteration_id)
        assert loaded.iteration_id == added.iteration_id
        assert loaded.decision == "discard"
        assert loaded.rationale == "checking round-trip"
        assert loaded.evaluation_result["primary_score"] == 0.75
        assert loaded.timestamp == pytest.approx(added.timestamp, abs=0.01)

    def test_get_nonexistent_raises(self, archive: Archive) -> None:
        with pytest.raises(FileNotFoundError, match="iteration_id=999"):
            archive.get(999)

    def test_files_on_disk(self, archive: Archive) -> None:
        archive.add(
            pipeline_source=PIPELINE_V1,
            evaluation_result=_make_eval_result(),
            rationale="test",
            decision="keep",
            baseline_source=BASELINE,
        )
        files = sorted(f.name for f in archive.archive_dir.iterdir())
        assert "001-keep.json" in files
        assert "001-pipeline.py" in files

    def test_pipeline_snapshot_content(self, archive: Archive) -> None:
        archive.add(
            pipeline_source=PIPELINE_V1,
            evaluation_result=_make_eval_result(),
            rationale="test",
            decision="keep",
        )
        snapshot = (archive.archive_dir / "001-pipeline.py").read_text()
        assert snapshot == PIPELINE_V1

    def test_invalid_decision_raises(self, archive: Archive) -> None:
        with pytest.raises(ValueError, match="decision must be"):
            archive.add(
                pipeline_source=PIPELINE_V1,
                evaluation_result=_make_eval_result(),
                rationale="bad",
                decision="maybe",
            )


# ---------------------------------------------------------------------------
# Nested deserialization
# ---------------------------------------------------------------------------

class TestDeserialization:
    def test_evaluation_result_round_trip(self, archive: Archive) -> None:
        er = _make_eval_result(primary_score=0.85, cost_usd=0.03, num_examples=3)
        entry = archive.add(
            pipeline_source=PIPELINE_V1,
            evaluation_result=er,
            rationale="deser test",
            decision="keep",
        )

        loaded = archive.get(entry.iteration_id)
        reconstructed = loaded.evaluation_result_obj

        assert isinstance(reconstructed, EvaluationResult)
        assert reconstructed.primary_score == 0.85
        assert reconstructed.num_examples == 3
        assert len(reconstructed.per_example_results) == 3

        ex0 = reconstructed.per_example_results[0]
        assert isinstance(ex0, ExampleResult)
        assert ex0.example_id == "ex_0"
        assert isinstance(ex0.metrics, MetricsSnapshot)
        assert ex0.metrics.model == "test-model"

        assert isinstance(reconstructed.metrics, MetricsSnapshot)
        assert reconstructed.metrics.cost_usd == 0.03

    def test_evaluation_result_from_dict_with_none_metrics(self) -> None:
        d = {
            "primary_score": 0.5,
            "per_example_results": [
                {
                    "example_id": "x",
                    "score": 0.5,
                    "success": False,
                    "error": "fail",
                    "duration_ms": 10.0,
                    "metrics": None,
                }
            ],
            "metrics": None,
            "benchmark_id": "b",
            "duration_ms": 100.0,
            "num_examples": 1,
            "num_failures": 1,
        }
        result = _evaluation_result_from_dict(d)
        assert result.metrics is None
        assert result.per_example_results[0].metrics is None


# ---------------------------------------------------------------------------
# Multiple entries + query
# ---------------------------------------------------------------------------

class TestQueryAndFilter:
    def _populate(self, archive: Archive) -> list[ArchiveEntry]:
        """Add 5 entries with mixed decisions and varying scores."""
        entries = []
        scores = [0.5, 0.9, 0.3, 1.0, 0.7]
        costs = [0.05, 0.02, 0.08, 0.01, 0.04]
        decisions = ["discard", "keep", "discard", "keep", "keep"]

        prev_source = BASELINE
        parent_id = None
        for i, (score, cost, dec) in enumerate(zip(scores, costs, decisions)):
            source = f'def run(x, p=None):\n    return {{"v": {i}}}\n'
            entry = archive.add(
                pipeline_source=source,
                evaluation_result=_make_eval_result(primary_score=score, cost_usd=cost),
                rationale=f"iteration {i}",
                decision=dec,
                parent_iteration_id=parent_id,
                baseline_source=BASELINE if parent_id is None else None,
            )
            entries.append(entry)
            parent_id = entry.iteration_id
            prev_source = source
        return entries

    def test_len_reflects_count(self, archive: Archive) -> None:
        self._populate(archive)
        assert len(archive) == 5

    def test_query_all(self, archive: Archive) -> None:
        self._populate(archive)
        assert len(archive.query()) == 5

    def test_query_filter_keep(self, archive: Archive) -> None:
        self._populate(archive)
        keeps = archive.query(decision="keep")
        assert len(keeps) == 3
        assert all(e.decision == "keep" for e in keeps)

    def test_query_filter_discard(self, archive: Archive) -> None:
        self._populate(archive)
        discards = archive.query(decision="discard")
        assert len(discards) == 2
        assert all(e.decision == "discard" for e in discards)

    def test_sort_by_primary_score_ascending(self, archive: Archive) -> None:
        self._populate(archive)
        entries = archive.query(sort_by="primary_score", ascending=True)
        scores = [e.evaluation_result["primary_score"] for e in entries]
        assert scores == sorted(scores)

    def test_sort_by_primary_score_descending(self, archive: Archive) -> None:
        self._populate(archive)
        entries = archive.query(sort_by="primary_score", ascending=False)
        scores = [e.evaluation_result["primary_score"] for e in entries]
        assert scores == sorted(scores, reverse=True)

    def test_sort_by_cost_usd(self, archive: Archive) -> None:
        self._populate(archive)
        entries = archive.query(sort_by="cost_usd", ascending=True)
        costs = [e.evaluation_result["metrics"]["cost_usd"] for e in entries]
        assert costs == sorted(costs)

    def test_query_with_limit(self, archive: Archive) -> None:
        self._populate(archive)
        entries = archive.query(limit=2)
        assert len(entries) == 2

    def test_best(self, archive: Archive) -> None:
        self._populate(archive)
        best = archive.best()
        assert best is not None
        assert best.evaluation_result["primary_score"] == 1.0

    def test_worst(self, archive: Archive) -> None:
        self._populate(archive)
        worst = archive.worst()
        assert worst is not None
        assert worst.evaluation_result["primary_score"] == 0.3

    def test_recent(self, archive: Archive) -> None:
        self._populate(archive)
        recent = archive.recent(n=3)
        assert len(recent) == 3
        ids = [e.iteration_id for e in recent]
        assert ids == sorted(ids, reverse=True)
        assert ids[0] == 5  # most recent


# ---------------------------------------------------------------------------
# Iteration ID auto-increment
# ---------------------------------------------------------------------------

class TestIterationId:
    def test_sequential_ids(self, archive: Archive) -> None:
        for i in range(3):
            entry = archive.add(
                pipeline_source=PIPELINE_V1,
                evaluation_result=_make_eval_result(),
                rationale=f"iter {i}",
                decision="keep",
            )
            assert entry.iteration_id == i + 1

    def test_resumes_from_existing_files(self, tmp_path: Path) -> None:
        """Simulate crash recovery — pre-existing files should be respected."""
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()

        # Write fake entries for IDs 1-3
        for i in range(1, 4):
            (archive_dir / f"{str(i).zfill(3)}-keep.json").write_text(
                json.dumps({"iteration_id": i, "timestamp": 0, "pipeline_diff": "",
                            "evaluation_result": {}, "rationale": "", "decision": "keep"}),
                encoding="utf-8",
            )
            (archive_dir / f"{str(i).zfill(3)}-pipeline.py").write_text("", encoding="utf-8")

        archive = Archive(archive_dir)
        entry = archive.add(
            pipeline_source=PIPELINE_V1,
            evaluation_result=_make_eval_result(),
            rationale="after crash",
            decision="keep",
        )
        assert entry.iteration_id == 4


# ---------------------------------------------------------------------------
# Pipeline diff
# ---------------------------------------------------------------------------

class TestPipelineDiff:
    def test_first_iteration_diffs_against_baseline(self, archive: Archive) -> None:
        entry = archive.add(
            pipeline_source=PIPELINE_V1,
            evaluation_result=_make_eval_result(),
            rationale="first",
            decision="keep",
            baseline_source=BASELINE,
        )
        assert "---" in entry.pipeline_diff
        assert "+++" in entry.pipeline_diff
        assert "+    return {\"echo\": x}" in entry.pipeline_diff

    def test_diff_against_parent(self, archive: Archive) -> None:
        e1 = archive.add(
            pipeline_source=PIPELINE_V1,
            evaluation_result=_make_eval_result(),
            rationale="v1",
            decision="keep",
            baseline_source=BASELINE,
        )
        e2 = archive.add(
            pipeline_source=PIPELINE_V2,
            evaluation_result=_make_eval_result(),
            rationale="v2",
            decision="keep",
            parent_iteration_id=e1.iteration_id,
        )
        assert "upper" in e2.pipeline_diff
        assert "-    return {\"echo\": x}" in e2.pipeline_diff
        assert "+    return {\"upper\": x.upper()}" in e2.pipeline_diff

    def test_no_diff_when_identical(self, archive: Archive) -> None:
        e1 = archive.add(
            pipeline_source=PIPELINE_V1,
            evaluation_result=_make_eval_result(),
            rationale="v1",
            decision="keep",
        )
        e2 = archive.add(
            pipeline_source=PIPELINE_V1,
            evaluation_result=_make_eval_result(),
            rationale="same",
            decision="keep",
            parent_iteration_id=e1.iteration_id,
        )
        assert e2.pipeline_diff == ""


# ---------------------------------------------------------------------------
# Corrupted archive entry
# ---------------------------------------------------------------------------

class TestCorruptedEntry:
    def test_corrupted_json_raises_with_context(self, tmp_path: Path) -> None:
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        (archive_dir / "001-keep.json").write_text("not valid json{{{", encoding="utf-8")

        archive = Archive(archive_dir)
        with pytest.raises(ValueError, match="Corrupted archive entry 001-keep.json"):
            archive.query()


# ---------------------------------------------------------------------------
# ArchiveEntry dataclass
# ---------------------------------------------------------------------------

class TestArchiveEntry:
    def test_frozen(self) -> None:
        entry = ArchiveEntry(
            iteration_id=1,
            timestamp=time.time(),
            pipeline_diff="",
            evaluation_result={},
            rationale="test",
            decision="keep",
        )
        with pytest.raises(AttributeError):
            entry.decision = "discard"  # type: ignore[misc]

    def test_asdict_round_trip(self) -> None:
        entry = ArchiveEntry(
            iteration_id=1,
            timestamp=123.0,
            pipeline_diff="diff",
            evaluation_result={"primary_score": 0.5},
            rationale="test",
            decision="keep",
            parent_iteration_id=None,
        )
        d = entry.asdict()
        restored = ArchiveEntry.from_dict(d)
        assert restored == entry
