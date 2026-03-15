---
estimated_steps: 5
estimated_files: 3
---

# T01: Build ReportGenerator module and wire autoagent report CLI

**Slice:** S03 — Reporting & End-to-End Assembly
**Milestone:** M004

## Description

Build `report.py` with composable section functions that read archive entries + project state + config and produce a structured markdown report. Wire `autoagent report` CLI subcommand. Pure computation — no LLM calls.

## Steps

1. Create `src/autoagent/report.py` with:
   - `ReportResult` frozen dataclass (`markdown: str`, `summary: str`)
   - `_score_trajectory(entries)` — best score progression, improvement rate, phase detection (exploring/converging/stagnated)
   - `_top_architectures(entries, limit=5)` — top-K kept entries with scores, mutation types, and rationale. Graceful degradation when no entries were kept.
   - `_cost_breakdown(state, entries)` — total cost from `ProjectState.total_cost_usd`, per-iteration breakdown, gate costs from `tla_verification["cost_usd"]` and `leakage_check["cost_usd"]` where present
   - `_recommendations(entries, state)` — use `analyze_strategy()` from strategy.py for stagnation/convergence signals, budget remaining calculation
   - `generate_report(entries, state, config)` — compose all sections with header (goal, iterations, best score), return `ReportResult`
   - Handle empty archive: return "no data" report with header only
2. Wire `cmd_report` in `cli.py`: load project dir, read archive entries via `Archive.query()`, read state via `StateManager.read_state()`, read config via `StateManager.read_config()`, call `generate_report()`, write `.autoagent/report.md`, print `result.summary` to stdout. Return 1 with stderr message if project not initialized.
3. Add `report` subparser to `build_parser()` and add to dispatch dict.
4. Write `tests/test_report.py` with unit tests:
   - Each section function with mock archive entries (kept entries, discarded entries, mixed)
   - Empty archive → "no data" output
   - All-discarded archive → graceful top architectures
   - Full `generate_report()` with all sections present
   - `cmd_report` CLI test writing report.md to disk
   - Cost breakdown summing gate costs correctly
5. Run full test suite, confirm no regressions.

## Must-Haves

- [ ] `ReportResult` frozen dataclass with `markdown` and `summary` fields
- [ ] Four composable section functions (trajectory, architectures, cost, recommendations)
- [ ] Empty archive produces readable "no data" report
- [ ] All-discarded archive degrades gracefully (no crash, useful output)
- [ ] `cmd_report` writes `.autoagent/report.md` and prints summary
- [ ] Cost breakdown includes TLA+ and leakage gate costs
- [ ] CLI wiring follows existing pattern (subparser + dispatch)

## Verification

- `pytest tests/test_report.py -v` — all tests pass
- `pytest tests/ -q` — 443+ tests pass, no regressions

## Inputs

- `src/autoagent/archive.py` — `Archive.query()`, `ArchiveEntry` fields
- `src/autoagent/state.py` — `ProjectState`, `ProjectConfig`
- `src/autoagent/strategy.py` — `analyze_strategy()` for recommendations
- `src/autoagent/summarizer.py` — `SummaryResult` frozen dataclass pattern
- `src/autoagent/cli.py` — existing subcommand pattern to follow

## Observability Impact

- **New inspection surface:** `.autoagent/report.md` written by `cmd_report` — a future agent can read this file to understand optimization outcomes without re-parsing the archive
- **Terminal signal:** `ReportResult.summary` printed to stdout provides a one-line status (best score, iterations, cost) usable by wrapper scripts or auto-mode
- **Failure visibility:** `cmd_report` returns exit code 1 with descriptive stderr message when project is not initialized or archive is empty — agents can detect and branch on this
- **Diagnostic entry point:** Each section function is independently callable for targeted inspection (e.g., `_cost_breakdown` to audit spend without generating full report)

## Expected Output

- `src/autoagent/report.py` — new module with `ReportGenerator` functions and `ReportResult`
- `src/autoagent/cli.py` — `cmd_report` handler + `report` subparser + dispatch entry
- `tests/test_report.py` — comprehensive unit + CLI tests for reporting
