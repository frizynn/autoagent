---
estimated_steps: 4
estimated_files: 1
---

# T02: End-to-end integration test proving full cold-start flow

**Slice:** S03 — Reporting & End-to-End Assembly
**Milestone:** M004

## Description

Capstone integration test that exercises the complete M004 flow: `autoagent new` (interview + benchmark generation) → `autoagent run` (optimization loop) → `autoagent report` (markdown output). Proves all subsystems chain correctly with MockLLM. Follows the pattern established in `tests/test_final_assembly.py`.

## Steps

1. Create `tests/test_end_to_end.py` with a single capstone test:
   - Set up `tmp_path` project directory
   - Prepare SequenceMockLLM with responses ordered for: interview phases (~8 responses for vague probing + answers), context generation (1), benchmark generation (1-2), then cycling for meta-agent proposals
   - Run `cmd_new` with `patch('builtins.input')` providing interview answers and SequenceMockLLM — verify config.json and benchmark.json written
   - Verify config has goal, benchmark.json loads via `Benchmark.from_file()`
2. Set up and run optimization loop:
   - Use a `SequentialMockMetaAgent` (from test_final_assembly.py pattern) or wire `MetaAgent` with MockLLM for 2-3 iterations
   - Run `cmd_run` with `--max-iterations=3`
   - Verify archive has entries after loop completes
3. Run `cmd_report`:
   - Call `cmd_report` on the same project dir
   - Verify `.autoagent/report.md` exists on disk
   - Verify report contains all 4 sections: "Score Trajectory", "Top Architectures", "Cost Breakdown", "Recommendations"
   - Verify report contains the goal string from the interview
4. Run full test suite, confirm no regressions against 443+ baseline.

## Must-Haves

- [ ] Single test exercises complete flow: interview → benchmark → loop → report
- [ ] SequenceMockLLM provides responses for all stages without manual LLM calls
- [ ] Verification at each stage boundary (config exists, benchmark loads, archive has entries, report has sections)
- [ ] Report file on disk contains expected section headers and goal
- [ ] All existing 443+ tests pass alongside the new test

## Verification

- `pytest tests/test_end_to_end.py -v` — capstone test passes
- `pytest tests/ -q` — all tests pass, no regressions

## Inputs

- `src/autoagent/report.py` — T01's ReportGenerator (must exist)
- `src/autoagent/cli.py` — `cmd_new`, `cmd_run`, `cmd_report` handlers
- `src/autoagent/interview.py` — `SequenceMockLLM`, `InterviewOrchestrator`
- `src/autoagent/benchmark_gen.py` — `BenchmarkGenerator`
- `tests/test_final_assembly.py` — capstone test pattern to follow
- `tests/test_cli.py` — CLI test patterns (`patch('builtins.input')`, `tmp_path`)

## Expected Output

- `tests/test_end_to_end.py` — capstone integration test proving full M004 flow

## Observability Impact

- **Signals verified:** This test validates the full diagnostic chain — config.json on disk after interview, benchmark.json loadable via `Benchmark.from_file()`, archive entries with evaluation_result/decision fields after loop, and `report.md` on disk with all 4 section headers after `cmd_report`.
- **Future inspection:** A failing e2e test pinpoints which subsystem boundary broke (interview→config, benchmark→generation, loop→archive, or report→disk). Each stage boundary has explicit assertions.
- **Failure state visibility:** Test failure messages identify the exact stage (config missing, benchmark not loadable, archive empty, report missing sections) — no silent passes.
