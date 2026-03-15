---
id: S04
parent: M001
milestone: M001
provides:
  - ArchiveEntry frozen dataclass with iteration_id, timestamp, pipeline_diff, evaluation_result, rationale, decision, parent_iteration_id
  - Archive class with add/get/query/best/worst/recent and atomic writes
  - Nested deserialization helpers for EvaluationResult→ExampleResult→MetricsSnapshot
  - Pipeline diff computation via difflib.unified_diff from parent or baseline
requires:
  - slice: S01
    provides: MetricsSnapshot, PipelineResult types
  - slice: S03
    provides: EvaluationResult, ExampleResult types
  - slice: S02
    provides: _atomic_write_json from state.py
affects:
  - S05
key_files:
  - src/autoagent/archive.py
  - tests/test_archive.py
key_decisions:
  - evaluation_result stored as dict in ArchiveEntry for JSON compatibility; reconstructed via evaluation_result_obj property on demand
  - _atomic_write_text helper parallels _atomic_write_json for pipeline snapshots
  - Corrupted JSON entries raise ValueError with filename context rather than silently skipping
patterns_established:
  - Manual nested deserialization for frozen dataclasses without from_dict() — pattern for reconstructing EvaluationResult→ExampleResult→MetricsSnapshot
  - Pipeline diffs via difflib.unified_diff with parent/baseline resolution
observability_surfaces:
  - Archive entries are self-describing JSON files with iteration_id, timestamp, decision baked into filename (NNN-{keep|discard}.json)
  - ls .autoagent/archive/ shows chronological iterations with keep/discard at a glance
  - Corrupted entries produce ValueError with filename for diagnosis
drill_down_paths:
  - .gsd/milestones/M001/slices/S04/tasks/T01-SUMMARY.md
duration: 15m
verification_result: passed
completed_at: 2026-03-14
---

# S04: Monotonic Archive

**Complete monotonic archive with atomic writes, query/filter/sort, pipeline diffs, and nested deserialization — 32 tests passing, 137 total suite green.**

## What Happened

Built `src/autoagent/archive.py` as a single-module implementation covering the entire slice scope:

- `ArchiveEntry` frozen dataclass with all boundary map fields plus `asdict()`/`from_dict()` serialization and `evaluation_result_obj` property for on-demand reconstruction of upstream types
- Three deserialization helpers (`_metrics_snapshot_from_dict`, `_example_result_from_dict`, `_evaluation_result_from_dict`) for round-tripping frozen upstream types through JSON
- `Archive` class with `add()` (atomic JSON + pipeline.py writes, unified diff computation from parent or baseline), `get()`, `query()` (filter by decision, sort by any metric field, limit), `best()`/`worst()`/`recent()`, `__len__()`
- `_atomic_write_text()` for pipeline snapshots, reusing `_atomic_write_json` from `state.py` for entry JSON
- Iteration ID derived from scanning `NNN-*.json` filenames on disk — crash-recovery safe
- On-disk format: `NNN-{keep|discard}.json` + `NNN-pipeline.py` with zero-padded 3+ digit IDs

## Verification

- `pytest tests/test_archive.py -v` — 32/32 passed
- `python -c "from autoagent.archive import Archive, ArchiveEntry"` — boundary contract importable
- `pytest tests/ -v` — 137/137 passed, zero regressions
- All 11 slice-level verification checks confirmed passing (see S04-PLAN.md)

## Requirements Advanced

- R004 (Monotonic Archive) — Full archive implementation with metrics, diffs, rationale, and monotonic append-only constraint. Ready for validation once wired into live loop (S05).

## Requirements Validated

- None — R004 needs live loop integration (S05) to fully validate.

## New Requirements Surfaced

- None

## Requirements Invalidated or Re-scoped

- None

## Deviations

None.

## Known Limitations

- Archive has no compression/summarization for large iteration counts — deferred to M002/S01 per R016
- No pruning or cleanup — monotonic by design, but unbounded growth at scale

## Follow-ups

- S05 wires Archive into the optimization loop (Archive.add() after each evaluation, Archive.query() for meta-agent context)
- S06 adds crash recovery from archive state (reconstruct loop position from archive entries on disk)

## Files Created/Modified

- `src/autoagent/archive.py` — Complete archive module with ArchiveEntry, Archive, deserialization helpers
- `tests/test_archive.py` — 32 tests covering all must-haves including corruption diagnostics

## Forward Intelligence

### What the next slice should know
- `Archive(path)` takes the `.autoagent/archive/` directory path. Call `archive.add(pipeline_code, evaluation_result, rationale, decision, parent_iteration_id, baseline_code)` to write an entry. The `baseline_code` param is only needed for the first iteration (diff against initial pipeline.py).
- `archive.query(decision="keep", sort_by="primary_score", ascending=False, limit=5)` gets top-5 kept iterations by score — useful for meta-agent context.
- `evaluation_result` is stored as a dict in JSON; use `entry.evaluation_result_obj` to get the reconstructed `EvaluationResult` instance.

### What's fragile
- Deserialization helpers manually reconstruct frozen dataclasses — if upstream types (MetricsSnapshot, ExampleResult, EvaluationResult) add new fields, the helpers need updating. No automatic schema migration.

### Authoritative diagnostics
- `ls .autoagent/archive/` — filename encodes iteration ID and decision; any entry is human-readable JSON
- `Archive(path).query()` — if this raises ValueError, the message includes the corrupted filename

### What assumptions changed
- None — slice delivered exactly as planned.
