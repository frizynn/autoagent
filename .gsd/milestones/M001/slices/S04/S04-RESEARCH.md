# S04: Monotonic Archive — Research

**Date:** 2026-03-14

## Summary

S04 is low-risk infrastructure work with well-defined boundaries. The archive stores iteration entries as JSON files + pipeline snapshots on disk, provides query/filter capabilities, and serves as the history surface for S05's meta-agent. All upstream types (`EvaluationResult`, `MetricsSnapshot`, `PipelineResult`) serialize cleanly via `dataclasses.asdict()` — no custom serializers needed. Deserialization requires nested reconstruction (`EvaluationResult` contains `ExampleResult` list containing `MetricsSnapshot`), which lives in the archive module since the upstream frozen dataclasses shouldn't be modified.

The `StateManager` already creates `.autoagent/archive/` during `init_project()` and provides `_atomic_write_json` for crash-safe writes. The on-disk convention from the boundary map (`.autoagent/archive/NNN-{keep|discard}.json` + `NNN-pipeline.py`) gives human-readable, git-friendly, crash-recoverable storage. Pipeline diffs use stdlib `difflib.unified_diff` — no dependencies needed.

## Recommendation

Build a single `src/autoagent/archive.py` module with:
- `ArchiveEntry` frozen dataclass matching the boundary map contract
- `Archive` class that reads/writes from `.autoagent/archive/` directory
- `Archive.add()` — atomic write of entry JSON + pipeline snapshot, with diff computed from parent
- `Archive.query()` — filter by decision, sort by metric, get best/worst/recent helpers
- Deserialization helpers for `EvaluationResult` reconstruction from stored JSON
- Iteration ID derived from scanning existing files (no in-memory counter) for crash recovery

Reuse `_atomic_write_json` from `state.py` for crash-safe JSON writes. Pipeline `.py` snapshots use the same atomic temp-file + `os.replace` pattern.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Unified diffs | `difflib.unified_diff` (stdlib) | Standard, human-readable, no dependency |
| Crash-safe JSON writes | `_atomic_write_json` in `state.py` | Already proven in S02, same crash-safety guarantees |
| JSON serialization of dataclasses | `dataclasses.asdict` (stdlib) | All upstream types already use this pattern |

## Existing Code and Patterns

- `src/autoagent/state.py` — `_atomic_write_json()` helper for crash-safe writes via temp file + `os.replace`. `StateManager.archive_dir` property already points to `.autoagent/archive/`. Reuse the atomic write helper; archive dir is pre-created by `init_project()`.
- `src/autoagent/types.py` — `MetricsSnapshot` (frozen), `PipelineResult`, `ErrorInfo` — all have `.asdict()` methods. `MetricsSnapshot.timestamp` is a float (epoch), `custom_metrics` is `dict[str, Any]`.
- `src/autoagent/evaluation.py` — `EvaluationResult` (frozen) and `ExampleResult` (frozen) — both serialize via `dataclasses.asdict()`. No `from_dict` or `timestamp` field on `EvaluationResult` — archive entry adds its own timestamp.
- `tests/test_state.py` — Pattern: `tmp_path` fixture for project dir, `StateManager` as fixture, direct filesystem assertions. Follow the same pattern for archive tests.
- `src/autoagent/primitives.py` — `PrimitivesContext` namespace, not needed by archive (archive stores results, not execution context).

## Constraints

- **Zero runtime dependencies** — stdlib only (json, difflib, os, tempfile, pathlib, dataclasses). Consistent with D015, D016.
- **Frozen upstream types** — `EvaluationResult`, `ExampleResult`, `MetricsSnapshot` are frozen dataclasses in S01/S03. Cannot add `from_dict()` classmethods to them. Deserialization must live in the archive module.
- **Crash-safe writes** — Every write must be atomic (temp file + `os.replace`). A crash mid-write must not corrupt the archive. This is a hard requirement for R005.
- **Monotonic append-only** — Archive grows only. No deletion, no in-place mutation of existing entries (R004). Iteration IDs are sequential integers.
- **File naming convention** — `NNN-{keep|discard}.json` + `NNN-pipeline.py` per boundary map. NNN is zero-padded (3+ digits). Decision is baked into the filename for instant visual scanning.
- **Serialization round-trip** — `EvaluationResult` contains nested `ExampleResult` list, each with optional `MetricsSnapshot`. Deserialization must reconstruct the full object graph from plain dicts.

## Common Pitfalls

- **Iteration ID from filename parsing, not in-memory counter** — After a crash and restart, the next ID must be derived from scanning existing archive files. An in-memory counter that starts at 0 would overwrite existing entries. Parse `NNN` from filenames on load.
- **Pipeline diff against wrong parent** — The diff must be computed between the parent iteration's pipeline snapshot (or the baseline pipeline.py for the first iteration) and the current pipeline source. Using the wrong base produces meaningless diffs.
- **Nested dataclass deserialization** — `dataclasses.asdict()` recursively converts nested dataclasses to dicts, but reconstruction requires manually rebuilding `MetricsSnapshot` inside `ExampleResult` inside `EvaluationResult`. A generic `from_dict` won't work — need type-aware reconstruction.
- **Zero-padding width** — 3 digits (001-999) is enough for M001 but R016 mentions scale to 200+ iterations. Use at least 3 digits; consider dynamic width or fixed 4 digits if concerned about sorting past 999.

## Open Risks

- **Large archive query performance** — At 200+ iterations (R016 scope), scanning all JSON files for query() could be slow. Not a problem for M001 (target is 5-10 iterations), but the API should not preclude future optimization (e.g., index file). Low risk — defer to M002/R016.
- **Pipeline.py snapshot size** — If pipeline.py grows large, storing a full copy per iteration adds up. Not a real concern for M001 (pipelines are small), and the full snapshot is critical for crash recovery and direct execution.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Python dataclasses/JSON | n/a | stdlib — no skill needed |
| difflib | n/a | stdlib — no skill needed |

No external technologies or frameworks involved — this is pure stdlib Python work.

## Sources

- Boundary map in M001-ROADMAP.md — defines `ArchiveEntry` fields, on-disk format, and `Archive` API contract
- S01-SUMMARY.md — `MetricsSnapshot`, `PipelineResult` types and serialization patterns
- S03-SUMMARY.md — `EvaluationResult`, `ExampleResult` types and what they contain
- `src/autoagent/state.py` — `_atomic_write_json` implementation, `StateManager.archive_dir` property
- D003 decision — directory of JSON files + pipeline snapshots, human-readable, crash-recoverable
- R004 requirement — every attempt recorded, archive grows monotonically, never pruned
