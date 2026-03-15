---
estimated_steps: 5
estimated_files: 2
---

# T01: Build Archive module with add, query, and serialization round-trip

**Slice:** S04 — Monotonic Archive
**Milestone:** M001

## Description

Build `src/autoagent/archive.py` with `ArchiveEntry` frozen dataclass and `Archive` class. The archive stores iterations as JSON + pipeline snapshots in `.autoagent/archive/`, supports querying by decision and sorting by metrics, and handles nested deserialization of upstream types. Write comprehensive tests proving the boundary contract.

## Steps

1. Create `ArchiveEntry` frozen dataclass with fields from boundary map: `iteration_id` (int), `timestamp` (float), `pipeline_diff` (str), `evaluation_result` (EvaluationResult as dict for storage), `rationale` (str), `decision` (str: "keep"/"discard"), `parent_iteration_id` (int | None). Add `asdict()` for serialization.

2. Implement deserialization helpers: `_evaluation_result_from_dict()` that reconstructs `EvaluationResult` with nested `ExampleResult` list, each containing optional `MetricsSnapshot`. These are frozen dataclasses without `from_dict()`, so reconstruction is manual.

3. Implement `Archive` class:
   - `__init__(archive_dir: Path)` — stores path, no eager loading
   - `_next_iteration_id()` — scan `NNN-*.json` filenames, return max+1 (or 1 if empty)
   - `add(pipeline_source: str, evaluation_result: EvaluationResult, rationale: str, decision: str, parent_iteration_id: int | None = None, baseline_source: str | None = None)` — compute diff from parent's `NNN-pipeline.py` (or baseline_source for first iteration), write `NNN-pipeline.py` atomically, write `NNN-{decision}.json` atomically via `_atomic_write_json`, return `ArchiveEntry`
   - `get(iteration_id: int)` — load single entry by ID
   - `query(decision: str | None = None, sort_by: str | None = None, ascending: bool = True, limit: int | None = None)` — load all entries, filter, sort, limit
   - `best(metric: str = "primary_score")`, `worst(metric: str)`, `recent(n: int)` — convenience helpers
   - `__len__()` — count entries without loading

4. Write pipeline snapshots using same atomic temp+replace pattern as `_atomic_write_json`. Compute diffs with `difflib.unified_diff`.

5. Write `tests/test_archive.py` with tests covering: empty archive, add+get round-trip with full field verification, nested EvaluationResult deserialization, 5+ entries with mixed decisions, query filtering by decision, sort by primary_score and cost_usd, best/worst/recent helpers, iteration ID auto-increment from existing files, pipeline diff correctness, first iteration with baseline diff.

## Must-Haves

- [ ] `ArchiveEntry` frozen dataclass with all boundary map fields
- [ ] `Archive.add()` writes JSON + pipeline.py atomically
- [ ] `Archive.query()` filters by decision and sorts by metric
- [ ] `best()`, `worst()`, `recent()` convenience methods work
- [ ] Iteration ID derived from scanning filenames (not in-memory counter)
- [ ] Pipeline diff computed via `difflib.unified_diff` from parent snapshot
- [ ] Nested `EvaluationResult` → `ExampleResult` → `MetricsSnapshot` deserialization round-trips
- [ ] On-disk format: `NNN-{keep|discard}.json` + `NNN-pipeline.py`
- [ ] Crash-safe writes via `_atomic_write_json`
- [ ] Monotonic: no deletion or mutation APIs

## Verification

- `pytest tests/test_archive.py -v` — all tests pass
- `python -c "from autoagent.archive import Archive, ArchiveEntry; print('boundary ok')"` — imports clean
- Full test suite: `pytest tests/ -v` — no regressions

## Observability Impact

- Signals added: each archive entry is a self-describing JSON file with iteration_id, timestamp, decision
- How a future agent inspects: `ls .autoagent/archive/` for overview; read any `NNN-*.json` for full detail
- Failure state exposed: `evaluation_result` in each entry preserves per-example errors and metrics

## Inputs

- `src/autoagent/types.py` — `MetricsSnapshot` (frozen dataclass with `asdict()`)
- `src/autoagent/evaluation.py` — `EvaluationResult`, `ExampleResult` (frozen dataclasses)
- `src/autoagent/state.py` — `_atomic_write_json()` helper for crash-safe writes
- S04-RESEARCH.md — deserialization strategy, pitfalls, constraints

## Expected Output

- `src/autoagent/archive.py` — complete Archive module with ArchiveEntry dataclass, Archive class, deserialization helpers
- `tests/test_archive.py` — comprehensive test suite (10+ tests) covering all must-haves
