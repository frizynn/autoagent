---
id: T01
parent: S04
milestone: M001
provides:
  - ArchiveEntry frozen dataclass with full boundary map fields
  - Archive class with add/get/query/best/worst/recent
  - Nested EvaluationResult deserialization helpers
  - Atomic writes for JSON entries and pipeline snapshots
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
duration: 15m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Build Archive module with add, query, and serialization round-trip

**Built complete monotonic archive with atomic writes, query/filter/sort, pipeline diffs, and nested deserialization — 32 tests all passing.**

## What Happened

Implemented `src/autoagent/archive.py` with:
- `ArchiveEntry` frozen dataclass with all boundary map fields + `asdict()`/`from_dict()`/`evaluation_result_obj` property
- Deserialization helpers (`_metrics_snapshot_from_dict`, `_example_result_from_dict`, `_evaluation_result_from_dict`) for manual reconstruction of frozen upstream types
- `Archive` class with `add()` (atomic JSON + pipeline.py writes, diff computation), `get()`, `query()` (filter by decision, sort by any metric), `best()`/`worst()`/`recent()`, `__len__()`
- `_atomic_write_text()` for pipeline snapshots, reusing `_atomic_write_json` from `state.py` for entry JSON
- Iteration ID derived from scanning `NNN-*.json` filenames — crash-recovery safe
- Pipeline diffs computed via `difflib.unified_diff` from parent snapshot or baseline

Test suite covers all must-haves: empty archive, add+get round-trip, nested deserialization with None metrics, 5-entry query with mixed decisions, sort by primary_score and cost_usd, best/worst/recent, iteration ID auto-increment from existing files, pipeline diff from baseline and parent, corrupted JSON error reporting, frozen enforcement, asdict round-trip.

## Verification

- `pytest tests/test_archive.py -v` — 32/32 passed
- `python -c "from autoagent.archive import Archive, ArchiveEntry; print('boundary ok')"` — clean import
- `pytest tests/ -v` — 137/137 passed, zero regressions

Slice-level verification checks passing:
- ✅ Add entry and read it back with full field round-trip
- ✅ Add 5+ entries with mixed keep/discard, query by decision
- ✅ Sort entries by primary_score and cost_usd
- ✅ Get best, worst, and recent entries
- ✅ Iteration ID auto-increments from existing files
- ✅ Pipeline diff computed correctly from parent snapshot
- ✅ First iteration diffs against provided baseline
- ✅ Nested EvaluationResult deserialization round-trip
- ✅ Empty archive returns empty results for all queries
- ✅ Corrupted or truncated JSON file produces a clear error with iteration ID context
- ✅ Boundary contract importable

## Diagnostics

- `ls .autoagent/archive/` — shows all iterations chronologically with keep/discard decision in filename
- Read any `NNN-{keep|discard}.json` for full entry details including evaluation_result with per-example errors
- `Archive(path).query()` loads and filters all entries; corrupted files raise `ValueError` with filename

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/archive.py` — Complete archive module with ArchiveEntry, Archive, deserialization helpers
- `tests/test_archive.py` — 32 tests covering all must-haves including corruption diagnostics
- `.gsd/milestones/M001/slices/S04/S04-PLAN.md` — Added diagnostic verification step (pre-flight fix)
