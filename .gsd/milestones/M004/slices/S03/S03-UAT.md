# S03: Reporting & End-to-End Assembly — UAT

**Milestone:** M004
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: All outputs are deterministic given MockLLM — report markdown, test results, and CLI exit codes can be verified mechanically without live runtime

## Preconditions

- Python 3.11+ with project virtualenv activated (`.venv/bin/activate`)
- All project dependencies installed (`pip install -e .`)
- Working directory is the project root

## Smoke Test

Run `pytest tests/test_report.py tests/test_end_to_end.py -v` — all 26 tests pass in under 5 seconds.

## Test Cases

### 1. Report generation with populated archive

1. Run `pytest tests/test_report.py::TestGenerateReport::test_full_report_with_all_sections -v`
2. **Expected:** Test passes. Report markdown contains all four section headers: "Score Trajectory", "Top Architectures", "Cost Breakdown", "Recommendations".

### 2. Empty archive produces graceful report

1. Run `pytest tests/test_report.py::TestGenerateReport::test_empty_archive -v`
2. **Expected:** Test passes. Report markdown says "No optimization data available" — no crash, no empty sections.

### 3. All-discarded archive degrades gracefully

1. Run `pytest tests/test_report.py::TestGenerateReport::test_all_discarded_entries -v`
2. **Expected:** Test passes. Top Architectures section says "No architectures were kept" instead of showing an empty table.

### 4. CLI report on uninitialized project

1. Run `pytest tests/test_report.py::TestCmdReport::test_report_not_initialized -v`
2. **Expected:** Test passes. `cmd_report` returns exit code 1 and stderr contains "not initialized".

### 5. CLI report writes report.md and prints summary

1. Run `pytest tests/test_report.py::TestCmdReport::test_report_with_archive_data -v`
2. **Expected:** Test passes. `.autoagent/report.md` written to disk with all sections. Summary printed to stdout.

### 6. Score trajectory tracks best-score progression

1. Run `pytest tests/test_report.py::TestScoreTrajectory::test_progression_tracking -v`
2. **Expected:** Test passes. Trajectory table shows iteration numbers and best scores in ascending order.

### 7. Phase detection identifies stagnation

1. Run `pytest tests/test_report.py::TestScoreTrajectory::test_phase_detection_stagnated -v`
2. **Expected:** Test passes. Report includes "stagnated" phase indicator when scores haven't improved.

### 8. Cost breakdown sums gate costs

1. Run `pytest tests/test_report.py::TestCostBreakdown::test_gate_costs_summed -v`
2. **Expected:** Test passes. Cost breakdown includes TLA+ and leakage gate cost subtotals from ArchiveEntry fields.

### 9. Recommendations include budget remaining

1. Run `pytest tests/test_report.py::TestRecommendations::test_budget_remaining -v`
2. **Expected:** Test passes. Recommendations section shows remaining budget when budget_usd is configured.

### 10. Full cold-start flow end-to-end

1. Run `pytest tests/test_end_to_end.py::TestEndToEnd::test_full_cold_start_flow -v`
2. **Expected:** Test passes. Verifies at each stage boundary:
   - After cmd_new: `config.json` exists with goal, `benchmark.json` exists and loads via `Benchmark.from_file()`
   - After cmd_run: archive has entries
   - After cmd_report: `report.md` exists with all 4 section headers and the goal string

### 11. No regressions across full test suite

1. Run `pytest tests/ -q`
2. **Expected:** 469 tests pass, 0 failures.

## Edge Cases

### Missing gate costs in archive entries

1. Run `pytest tests/test_report.py::TestCostBreakdown::test_missing_gate_costs_handled -v`
2. **Expected:** Test passes. Cost breakdown handles entries without `tla_verification` or `leakage_check` fields without crashing — treats missing costs as 0.

### No budget configured

1. Run `pytest tests/test_report.py::TestRecommendations::test_no_budget_configured -v`
2. **Expected:** Test passes. Recommendations section omits budget remaining when `budget_usd` is not set in config.

### Report result immutability

1. Run `pytest tests/test_report.py::TestGenerateReport::test_report_result_is_frozen -v`
2. **Expected:** Test passes. Attempting to modify `ReportResult` attributes raises `FrozenInstanceError`.

## Failure Signals

- Any test in `test_report.py` or `test_end_to_end.py` fails — indicates broken report generation or integration
- `cmd_report` returns exit code 0 on uninitialized project — missing error handling
- E2e test assertion message identifies exact stage: "config.json not written by cmd_new", "Archive should have entries after cmd_run", "Missing Score Trajectory section"
- Test count drops below 469 — regression in existing tests
- `ModuleNotFoundError: No module named 'autoagent'` — virtualenv not activated

## Requirements Proved By This UAT

- R006 — `autoagent report` CLI command works (test cases 4, 5)
- R007 — interview output consumed in full flow (test case 10, via cmd_new stage)
- R017 — cost breakdown in report (test cases 8, edge case: missing gate costs)
- R019 — fire-and-forget flow complete: interview → benchmark → loop → report (test case 10)
- R023 — generated benchmark consumed by optimization loop (test case 10, cmd_run stage)

## Not Proven By This UAT

- Report quality with real LLM-generated archive data (only MockLLM used)
- Report rendering in different markdown viewers
- Report generation performance at scale (100+ archive entries)
- Real CLI invocation via `autoagent report` command (tested via Python function call, not subprocess)

## Notes for Tester

- The e2e test (test case 10) is the most valuable single test — if it passes, all M004 subsystems integrate correctly.
- All tests use MockLLM/SequenceMockLLM — no API keys or network access needed.
- The benchmark path inconsistency noted in the slice summary is visible in the e2e test source code (look for the config fixup after cmd_new) but does not affect test validity.
