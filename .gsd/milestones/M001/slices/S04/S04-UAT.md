# S04: Monotonic Archive — UAT

**Milestone:** M001
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: Archive is a pure data module with no UI, no network, no runtime services. All behavior is exercised through unit tests against the filesystem.

## Preconditions

- Python 3.11+ with project installed in dev mode (`.venv/bin/python -m pytest` works)
- No running services required
- Tests create their own temp directories — no manual setup needed

## Smoke Test

```bash
.venv/bin/python -m pytest tests/test_archive.py -v
# Expected: 32/32 passed
```

## Test Cases

### 1. Add entry and round-trip all fields

1. Create an `Archive` pointing at a temp directory
2. Call `archive.add()` with known pipeline code, evaluation result, rationale="test", decision="keep", parent_iteration_id=None, baseline_code="original"
3. Call `archive.get(1)` to retrieve the entry
4. **Expected:** All fields match — iteration_id=1, decision="keep", rationale="test", pipeline_diff contains unified diff, evaluation_result round-trips with correct primary_score, per-example metrics, and timestamps

### 2. Five iterations with mixed decisions and query filtering

1. Add 5 entries: iterations 1-3 as "keep", iterations 4-5 as "discard"
2. `archive.query(decision="keep")` → exactly 3 entries
3. `archive.query(decision="discard")` → exactly 2 entries
4. `archive.query()` → all 5 entries
5. **Expected:** Filtering returns correct subsets, all entries deserialize cleanly

### 3. Sort by primary_score and cost_usd

1. Add 5 entries with varying primary_score (0.1, 0.9, 0.5, 0.3, 0.7) and cost values
2. `archive.query(sort_by="primary_score", ascending=False)` → scores in descending order
3. `archive.query(sort_by="cost_usd", ascending=True)` → costs in ascending order
4. **Expected:** Sort order is correct for both metric fields

### 4. Best, worst, and recent helpers

1. Add 5 entries with different primary_scores
2. `archive.best()` → entry with highest primary_score
3. `archive.worst()` → entry with lowest primary_score
4. `archive.recent(n=2)` → last 2 entries by iteration_id
5. **Expected:** Each helper returns the correct entry/entries

### 5. Iteration ID auto-increment from existing files

1. Manually create files `001-keep.json` and `002-discard.json` in archive dir (valid JSON)
2. Create an `Archive` pointing at that directory
3. Add a new entry
4. **Expected:** New entry gets iteration_id=3, files are `003-keep.json` + `003-pipeline.py`

### 6. Pipeline diff from baseline and parent

1. Add first entry with baseline_code="line1\nline2\n" and pipeline_code="line1\nline3\n"
2. **Expected:** pipeline_diff contains unified diff showing line2→line3
3. Add second entry (parent_iteration_id=1) with pipeline_code="line1\nline4\n"
4. **Expected:** pipeline_diff shows diff against iteration 1's snapshot (line3→line4), not baseline

### 7. Nested EvaluationResult deserialization

1. Add entry with EvaluationResult containing ExampleResults with MetricsSnapshot (latency_ms, tokens_in, tokens_out, cost_usd, custom_metrics)
2. Retrieve via `archive.get()`
3. Access `entry.evaluation_result_obj`
4. **Expected:** Returns fully reconstructed EvaluationResult with nested ExampleResult and MetricsSnapshot instances, not raw dicts

### 8. Boundary contract import

1. Run: `from autoagent.archive import Archive, ArchiveEntry`
2. **Expected:** No ImportError — these are the exact symbols S05 will consume

## Edge Cases

### Empty archive returns empty for all queries

1. Create Archive on empty directory
2. Call `query()`, `best()`, `worst()`, `recent()`
3. **Expected:** `query()` → empty list, `best()`/`worst()` → None, `recent()` → empty list, `len(archive)` → 0

### Corrupted JSON produces clear error

1. Write a file `001-keep.json` with invalid JSON content ("not json")
2. Call `archive.get(1)`
3. **Expected:** Raises `ValueError` with message containing the filename "001-keep.json" for diagnosis

### Frozen ArchiveEntry prevents mutation

1. Create an ArchiveEntry
2. Attempt to set `entry.rationale = "modified"`
3. **Expected:** Raises `FrozenInstanceError` — entries are immutable after creation

## Failure Signals

- Any test in `test_archive.py` failing
- `ImportError` on `from autoagent.archive import Archive, ArchiveEntry`
- Archive files not appearing on disk after `add()`
- Deserialization returning raw dicts instead of typed objects from `evaluation_result_obj`
- Missing or incorrect pipeline diffs

## Requirements Proved By This UAT

- R004 (Monotonic Archive) — Every attempt recorded with full metrics, diffs, rationale; archive grows monotonically, never pruned. Partial proof: archive module works correctly in isolation. Full proof requires live loop integration (S05).

## Not Proven By This UAT

- R004 live integration — archive wired into optimization loop (S05)
- R005 crash recovery from archive state — reconstructing loop position (S06)
- R016 archive compression at scale — deferred to M002/S01

## Notes for Tester

All test cases are already implemented in `tests/test_archive.py` (32 tests). Running `pytest tests/test_archive.py -v` exercises every case listed above. The UAT is effectively automated — no manual steps needed beyond running the test suite.
