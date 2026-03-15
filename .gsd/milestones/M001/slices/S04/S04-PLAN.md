# S04: Monotonic Archive

**Goal:** Every pipeline iteration is archived on disk with full metrics, pipeline diff, and rationale; archive is readable, queryable, and crash-safe.
**Demo:** Write 5+ iterations to the archive with keep/discard decisions, read them back with filtering by decision and sorting by metric.

## Must-Haves

- `ArchiveEntry` frozen dataclass with fields: iteration_id, timestamp, pipeline_diff, evaluation_result, rationale, decision, parent_iteration_id
- `Archive` class that reads/writes entries to `.autoagent/archive/`
- `Archive.add()` atomically writes entry JSON + pipeline snapshot; computes diff from parent
- `Archive.query()` filters by decision (keep/discard), sorts by metric, returns best/worst/recent
- Iteration ID derived from scanning existing archive files on disk (crash-recovery safe)
- On-disk format: `NNN-{keep|discard}.json` + `NNN-pipeline.py` (zero-padded, 3+ digits)
- Crash-safe writes via `_atomic_write_json` from `state.py`
- Nested deserialization of `EvaluationResult` → `ExampleResult` → `MetricsSnapshot` from stored JSON
- Monotonic append-only — no deletion or mutation of existing entries

## Verification

- `pytest tests/test_archive.py -v` — all tests pass covering:
  - Add entry and read it back with full field round-trip
  - Add 5+ entries with mixed keep/discard, query by decision
  - Sort entries by primary_score and cost_usd
  - Get best, worst, and recent entries
  - Iteration ID auto-increments from existing files
  - Pipeline diff computed correctly from parent snapshot
  - First iteration diffs against provided baseline
  - Nested EvaluationResult deserialization round-trip
  - Empty archive returns empty results for all queries
  - Corrupted or truncated JSON file produces a clear error with iteration ID context
- `from autoagent.archive import Archive, ArchiveEntry` — boundary contract importable

## Observability / Diagnostics

- Runtime signals: archive entries are self-describing JSON files with timestamp, iteration_id, and decision baked into filename
- Inspection surfaces: `ls .autoagent/archive/` shows chronological iterations with keep/discard at a glance; any entry is human-readable JSON
- Failure visibility: `ArchiveEntry.evaluation_result` preserves per-example errors; discarded iterations remain in archive with rationale

## Integration Closure

- Upstream surfaces consumed: `EvaluationResult`, `ExampleResult` from `evaluation.py`; `MetricsSnapshot` from `types.py`; `_atomic_write_json` from `state.py`
- New wiring introduced: none — `Archive` is a standalone module consumed by S05
- What remains: S05 wires `Archive` into the optimization loop; S06 adds crash recovery from archive state

## Tasks

- [x] **T01: Build Archive module with add, query, and serialization round-trip** `est:45m`
  - Why: This is the entire slice — single module + comprehensive tests
  - Files: `src/autoagent/archive.py`, `tests/test_archive.py`
  - Do: Implement `ArchiveEntry` dataclass and `Archive` class. `add()` writes entry JSON + pipeline.py snapshot atomically, computes unified diff from parent iteration's snapshot (or baseline for first). `query()` loads all entries with deserialization of nested `EvaluationResult`→`ExampleResult`→`MetricsSnapshot`, filters by decision, sorts by any metric field. Derive next iteration ID by scanning existing `NNN-*.json` filenames. Reuse `_atomic_write_json` from `state.py`. Write pipeline snapshots with same atomic temp+replace pattern. Build comprehensive test suite covering all must-haves.
  - Verify: `pytest tests/test_archive.py -v` — all pass; boundary import check passes
  - Done when: 5+ iterations can be written and read back with filtering, sorting, and correct diffs; all tests green

## Files Likely Touched

- `src/autoagent/archive.py`
- `tests/test_archive.py`
