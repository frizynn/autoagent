# S03: Reporting & End-to-End Assembly

**Goal:** `autoagent report` produces a structured markdown report from archive data, and an end-to-end integration test proves the full cold-start flow (interview → benchmark generation → optimization loop → report) with MockLLM.
**Demo:** `pytest tests/test_report.py tests/test_end_to_end.py -v` passes — report sections contain score trajectory, top architectures, cost breakdown, and recommendations; e2e test chains all four subsystems through CLI commands.

## Must-Haves

- `ReportGenerator` with composable section functions (score trajectory, top architectures, cost breakdown, recommendations)
- `ReportResult` frozen dataclass with `markdown` and `summary` fields
- Empty archive produces a "no data" message, not a crash
- All-discarded archive degrades gracefully in top architectures section
- `autoagent report` CLI subcommand writes `.autoagent/report.md` and prints terminal summary
- End-to-end test chains `cmd_new` → `cmd_run` → `cmd_report` with SequenceMockLLM
- Report cost breakdown sums evaluation, TLA+, and leakage gate costs
- All existing tests pass (443 baseline + new)

## Proof Level

- This slice proves: final-assembly
- Real runtime required: no (MockLLM throughout)
- Human/UAT required: no

## Verification

- `pytest tests/test_report.py -v` — unit tests for each section function, edge cases (empty archive, all-discarded), full report generation, CLI command
- `pytest tests/test_end_to_end.py -v` — end-to-end test proving interview → benchmark → loop → report flow
- `pytest tests/ -q` — all tests pass (443 baseline + new, no regressions)
- `cmd_report` returns exit code 1 with stderr message when `.autoagent/` does not exist — verify via CLI test asserting non-zero return and stderr content
- End-to-end test verifies diagnostic surface: report.md written to disk is inspectable, archive entries have expected gate fields, and `cmd_report` exit code 0 confirms healthy state after full flow

## Observability / Diagnostics

- Runtime signals: `ReportResult.summary` provides terminal-friendly short output; `ReportResult.markdown` is the full artifact
- Inspection surfaces: `.autoagent/report.md` on disk after `cmd_report`; stdout summary after CLI execution
- Failure visibility: `cmd_report` returns non-zero exit code with descriptive stderr on missing project/archive
- Redaction constraints: none

## Integration Closure

- Upstream surfaces consumed: `Archive.query()`, `Archive.best()`, `ArchiveEntry` fields (evaluation_result, decision, mutation_type, tla_verification, leakage_check, pareto_evaluation), `ProjectState` (total_cost_usd, current_iteration, phase), `ProjectConfig` (goal, budget_usd), `analyze_strategy()` from strategy.py
- New wiring introduced in this slice: `cmd_report` CLI handler + `report` subparser in `build_parser()`, `ReportGenerator` module
- What remains before the milestone is truly usable end-to-end: nothing — this is the final assembly slice

## Tasks

- [x] **T01: Build ReportGenerator module and wire autoagent report CLI** `est:1h`
  - Why: Delivers the reporting feature — composable section functions that read archive data and produce structured markdown. This is the primary deliverable of the slice.
  - Files: `src/autoagent/report.py`, `src/autoagent/cli.py`, `tests/test_report.py`
  - Do: Build `report.py` with composable section functions (`_score_trajectory`, `_top_architectures`, `_cost_breakdown`, `_recommendations`), `ReportResult` frozen dataclass, and `generate_report()` entry point. Wire `cmd_report` into CLI with `report` subparser. Handle edge cases: empty archive → "no data" message, all-discarded → graceful degradation. Cost breakdown must sum evaluation + TLA+ + leakage costs from ArchiveEntry fields. Use `analyze_strategy()` for recommendations section. No LLM calls — pure computation. Write comprehensive unit tests.
  - Verify: `pytest tests/test_report.py -v` passes; `pytest tests/ -q` shows no regressions
  - Done when: `cmd_report` writes `.autoagent/report.md` with all 4 sections and prints terminal summary; empty/all-discarded edge cases tested; 443+ tests pass

- [x] **T02: End-to-end integration test proving full cold-start flow** `est:45m`
  - Why: Proves the milestone's success criterion — full flow from vague goal through morning report. This is the capstone test that validates all M004 subsystems work together.
  - Files: `tests/test_end_to_end.py`
  - Do: Write a capstone test that sets up a `tmp_path` project, runs `cmd_new` with SequenceMockLLM providing interview + benchmark generation responses, runs `cmd_run` with max_iterations=3 and MockLLM/mock meta-agent, then runs `cmd_report` and verifies: config.json exists with goal, benchmark.json exists and loads via `Benchmark.from_file()`, archive has entries, report.md exists with all 4 sections. Use `patch('builtins.input')` for interview simulation. Verify at each stage boundary, not just the end.
  - Verify: `pytest tests/test_end_to_end.py -v` passes; `pytest tests/ -q` shows no regressions
  - Done when: Single test exercises interview → benchmark generation → optimization loop → report generation; all artifacts verified on disk; all existing tests still pass

## Files Likely Touched

- `src/autoagent/report.py`
- `src/autoagent/cli.py`
- `tests/test_report.py`
- `tests/test_end_to_end.py`
