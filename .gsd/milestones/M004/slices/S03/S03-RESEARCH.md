# S03: Reporting & End-to-End Assembly — Research

**Date:** 2026-03-14

## Summary

S03 has two deliverables: (1) a `ReportGenerator` class that reads archive data and produces a structured markdown report, and (2) an end-to-end integration test proving the full flow: `autoagent new` → benchmark generation → `autoagent run` → `autoagent report`.

The reporting side is straightforward — all the data it needs already exists in well-structured form. `Archive.query()` returns `ArchiveEntry` objects with `evaluation_result` dicts (containing `primary_score`, `metrics`, `per_example_results`), `decision`, `rationale`, `mutation_type`, `pareto_evaluation`, and `leakage_check`. The `ProjectState` dataclass has `total_cost_usd`, `current_iteration`, `best_iteration_id`, and `phase`. These two data sources contain everything needed for score trajectory, top architectures, cost breakdown, and recommendations.

The end-to-end test is the more interesting challenge. It must chain interview → benchmark generation → optimization loop → report in a single test, with `SequenceMockLLM` providing responses for all stages. The response ordering is critical — interview phases consume responses first, then benchmark generation, then meta-agent proposals, then report generation. The existing `test_final_assembly.py` capstone pattern (412 lines) provides a good template: it uses mock meta-agents with predetermined proposals, sets up a full `OptimizationLoop`, and verifies archive entries.

**Primary recommendation:** Build `ReportGenerator` as a pure-function module (`report.py`) that takes archive entries + project state + config and returns section strings. Wire `autoagent report` CLI command. Then write the end-to-end test as a capstone that exercises the full cold-start flow. Report generation does NOT need an LLM call — it's pure computation over archive data. This avoids adding LLM cost to reporting and keeps it deterministic/testable.

## Recommendation

Report sections should be composable functions, each taking archive entries and returning a markdown string:
- `_score_trajectory(entries)` — best score over time, improvement rate, phases (exploration/convergence/stagnation)
- `_top_architectures(entries, limit=5)` — top-K kept entries with scores, diffs, and what made them work
- `_cost_breakdown(state, entries)` — total cost, cost per iteration, cost by gate (TLA+, leakage, evaluation)
- `_recommendations(entries, state)` — actionable next steps based on current state (stagnated? budget left? etc.)

`generate_report()` composes these sections into a markdown document with a header containing goal, iteration count, and best score. Output is a `ReportResult` frozen dataclass with `markdown` (full report string) and `summary` (terminal-friendly short version).

For the end-to-end test: create a single test that sets up a tmp_path project, runs `cmd_new` with mocked input + SequenceMockLLM, runs `cmd_run` with max_iterations=3, then runs `cmd_report` and verifies the markdown output contains expected sections. This proves the full flow without requiring real LLM calls.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Archive data access | `Archive.query(decision=, sort_by=, limit=)` | Full query API with filtering/sorting — report just calls with different params |
| Score trajectory data | `Archive.query(sort_by="primary_score", ascending=False)` | Already sorted by score |
| Cost data | `ProjectState.total_cost_usd` + per-entry `evaluation_result["metrics"]["cost_usd"]` | Cost tracked at both levels |
| Mutation classification | `ArchiveEntry.mutation_type` field | Already classified by loop, no recomputation needed |
| Stagnation detection | `analyze_strategy()` from `strategy.py` | Pure function, reusable for report recommendations |
| CLI subcommand wiring | `build_parser()` + dispatch dict in `cli.py` | Exact same pattern as init/run/status/new |
| Project state reading | `StateManager.read_state()` + `read_config()` | Existing atomic read path |

## Existing Code and Patterns

- `src/autoagent/archive.py` — `Archive.query()` is the primary data source. `ArchiveEntry` has all fields needed: `evaluation_result` (dict with `primary_score`, `metrics`, `per_example_results`), `decision`, `rationale`, `mutation_type`, `pareto_evaluation`, `leakage_check`, `tla_verification`, `sandbox_execution`. `Archive.best()` and `Archive.worst()` provide quick extremes.
- `src/autoagent/state.py` — `ProjectState.total_cost_usd`, `current_iteration`, `best_iteration_id`, `phase`. `ProjectConfig.goal`, `budget_usd`. These populate the report header and cost section.
- `src/autoagent/strategy.py` — `analyze_strategy()` produces graduated strategy signals from recent entries. Reusable for the recommendations section — if it detects stagnation, the report can recommend what to try next.
- `src/autoagent/cli.py` — `build_parser()` adds subparsers; dispatch dict maps command names to handler functions. Pattern: `cmd_report(args)` reads project dir, loads archive + state, generates report, writes to file, prints summary. 376 lines currently.
- `src/autoagent/summarizer.py` — `ArchiveSummarizer` follows the section-based prompt pattern for LLM-driven summaries. Report generation is *not* LLM-driven (pure computation), but the `SummaryResult` frozen dataclass pattern (text + cost + metadata) is worth following for `ReportResult`.
- `tests/test_final_assembly.py` — Capstone integration test pattern: `SequentialMockMetaAgent` with predetermined proposals, mock verifiers/checkers, full loop setup with all gates. 412 lines, 2 tests. End-to-end test should follow this structure.
- `tests/test_cli.py` — CLI test patterns: `capsys` for output capture, `tmp_path` for project dirs, `unittest.mock.patch('builtins.input')` for interview simulation. 24 tests across 5 test classes.

## Constraints

- **Zero runtime dependencies** — report output is plain markdown string. No `rich`, `tabulate`, or formatting libraries. Tables must be simple pipe-delimited markdown.
- **Report must be readable as plain text** — no complex nested formatting, no HTML. Simple markdown: headers, bullet lists, simple tables. Per M004 research: "Terminal markdown rendering varies wildly."
- **No LLM calls in report generation** — report is pure computation over archive data. Keeps it deterministic, testable, and zero-cost. The summarizer already handles LLM-based archive compression; the report is a different concern.
- **`ProjectConfig` is frozen** — access fields directly, no mutation needed for reporting.
- **`ArchiveEntry.evaluation_result` is a dict, not `EvaluationResult`** — must access via dict keys (`["primary_score"]`, `["metrics"]`), not object attributes. Use `evaluation_result_obj` property only if full deserialization needed.
- **`cmd_run()` requires benchmark and goal** — end-to-end test must ensure interview + benchmark generation produce both before running the loop.
- **SequenceMockLLM cycles when exhausted** — end-to-end test must provide enough responses for all stages: ~8 interview phases + 1 context generation + ~2 benchmark generation + N meta-agent proposals.

## Common Pitfalls

- **Report as monolithic string concatenation** — Makes testing impossible. Build from composable section functions that can be unit-tested independently. Each section takes entries and returns a string.
- **Testing report output with exact string matching** — Fragile. Test for section presence (`"## Score Trajectory" in report`), key data points (`"0.85" in report` for best score), and structural completeness (all 4 sections present). Not exact string equality.
- **End-to-end test with too many mock responses** — SequenceMockLLM cycles, so extra responses are harmless. But too few will silently cycle and produce wrong answers. Count the exact call sequence: interview (6 phases × 1 question each + up to 2 LLM calls for vague detection + 1 context generation) + benchmark gen (1-2 calls) + meta-agent proposals (N iterations).
- **Forgetting to handle empty archive** — `autoagent report` on a project with no iterations should produce a "no data" message, not crash. Edge case that's easy to miss.
- **Cost breakdown missing gate costs** — TLA+ verification and leakage checking costs are in `tla_verification["cost_usd"]` and `leakage_check["cost_usd"]` on each entry. These aren't in `evaluation_result.metrics`. Report must sum across both sources.
- **End-to-end test not verifying report file on disk** — `cmd_report` should write `.autoagent/report.md`. Test must verify the file exists and contains expected content, not just check stdout.

## Open Risks

- **Archive with only discarded entries** — If all iterations were discarded (all proposals failed gates), the report must still be useful: show what was tried, why it failed, and what to change. The "top architectures" section needs graceful degradation to "no successful iterations."
- **Cost tracking accuracy across gates** — Total cost in `ProjectState` may not equal sum of per-entry costs because summarization costs and meta-agent costs are tracked differently. Report should use `ProjectState.total_cost_usd` as the authoritative total and per-entry costs for the breakdown. The numbers may not add up exactly — the report should note this.
- **End-to-end test brittleness** — The test chains 4 subsystems (interview → benchmark gen → loop → report) with a single SequenceMockLLM. Any change to interview phase count, benchmark generation prompt structure, or meta-agent call sequence breaks the response ordering. Mitigation: use SequenceMockLLM's cycling behavior so extra/missing calls don't hard-fail, and verify outputs at each stage boundary.
- **Report recommendations quality** — Recommendations based on mechanical analysis (stagnation detection, mutation diversity) are limited. "Consider structural changes" is generic. Acceptable for M004 — richer LLM-driven recommendations would be a future enhancement.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Markdown report generation | `curiouslearner/devkit@report-generator` | Available (28 installs) — generic report generator, not optimization-specific |
| CLI testing | none found | No relevant skills — CLI testing uses pytest + capsys (stdlib patterns) |
| End-to-end integration testing | none found | Domain-specific — follows existing capstone pattern in test_final_assembly.py |

No skills are directly relevant. The report generator and end-to-end test are domain-specific, built on existing codebase patterns.

## Sources

- `src/autoagent/archive.py` — Archive API (query, best, worst, recent), ArchiveEntry fields
- `src/autoagent/cli.py` — CLI subcommand pattern (376 lines, 4 existing commands)
- `src/autoagent/state.py` — ProjectState and ProjectConfig structures
- `src/autoagent/strategy.py` — analyze_strategy() for stagnation detection reuse
- `src/autoagent/summarizer.py` — SummaryResult frozen dataclass pattern
- `src/autoagent/evaluation.py` — EvaluationResult and ExampleResult structure
- `tests/test_final_assembly.py` — Capstone integration test pattern (SequentialMockMetaAgent, full gate setup)
- `tests/test_cli.py` — CLI test patterns (capsys, tmp_path, mock input)
- M004 S01/S02 summaries — Forward intelligence on SequenceMockLLM usage and response ordering
