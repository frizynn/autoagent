---
id: T01
parent: S03
milestone: M004
provides:
  - ReportResult frozen dataclass with markdown and summary fields
  - Four composable section functions (trajectory, architectures, cost, recommendations)
  - cmd_report CLI command writing .autoagent/report.md
  - Comprehensive test coverage for report generation and CLI wiring
key_files:
  - src/autoagent/report.py
  - src/autoagent/cli.py
  - tests/test_report.py
key_decisions:
  - Section functions are module-level private functions (not a class) for simplicity and composability
  - Cost breakdown reads gate costs directly from ArchiveEntry.tla_verification and leakage_check dicts rather than re-computing
  - _recommendations delegates to analyze_strategy() rather than duplicating stagnation logic
patterns_established:
  - Report sections are composable string-returning functions that can be called independently for targeted inspection
observability_surfaces:
  - .autoagent/report.md on disk after cmd_report
  - ReportResult.summary printed to stdout for terminal/wrapper consumption
  - cmd_report returns exit code 1 with stderr message when project not initialized
duration: 20m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Build ReportGenerator module and wire autoagent report CLI

**Built report.py with composable section functions, wired `autoagent report` CLI, and wrote 25 unit/CLI tests — all passing with no regressions (468 total).**

## What Happened

Created `src/autoagent/report.py` with:
- `ReportResult` frozen dataclass (`markdown`, `summary`)
- `_score_trajectory()` — best-score progression table, improvement rate, phase detection (exploring/converging/stagnated)
- `_top_architectures()` — top-K kept entries sorted by score with mutation type and rationale; gracefully handles all-discarded
- `_cost_breakdown()` — total from ProjectState, per-iteration table with eval/TLA+/leakage costs, gate cost subtotals
- `_recommendations()` — delegates to `analyze_strategy()` for stagnation signals, computes budget remaining
- `generate_report()` — composes header + all sections, handles empty archive with "no data" report

Wired `cmd_report` in `cli.py` following the existing pattern: reads state/config/archive, calls `generate_report()`, writes `.autoagent/report.md`, prints summary to stdout. Returns 1 with stderr on uninitialized project.

Added `report` subparser to `build_parser()` and dispatch entry.

## Verification

- `pytest tests/test_report.py -v` — 25/25 passed
- `pytest tests/ -q` — 468 passed, 0 failures (baseline was 443)
- Slice-level: `pytest tests/test_report.py -v` passes ✓
- Slice-level: `pytest tests/ -q` shows no regressions ✓
- Slice-level: `cmd_report` returns exit code 1 with stderr when project not initialized ✓
- Slice-level: `pytest tests/test_end_to_end.py -v` — not yet created (T02)

## Diagnostics

- Run `autoagent --project-dir <dir> report` to generate report and inspect `.autoagent/report.md`
- Each section function (`_score_trajectory`, `_top_architectures`, `_cost_breakdown`, `_recommendations`) is independently callable for targeted debugging
- `cmd_report` exit code 1 + stderr message on missing project — detectable by automation

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/report.py` — new module with ReportResult dataclass and composable section functions
- `src/autoagent/cli.py` — added cmd_report handler, report subparser, dispatch entry, import
- `tests/test_report.py` — 25 tests covering all section functions, edge cases, full report, and CLI
- `.gsd/milestones/M004/slices/S03/S03-PLAN.md` — added diagnostic verification step
- `.gsd/milestones/M004/slices/S03/tasks/T01-PLAN.md` — added Observability Impact section
