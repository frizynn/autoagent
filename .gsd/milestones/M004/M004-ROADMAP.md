# M004: Interview & Polish

**Vision:** The full user experience — from a vague goal to a morning report showing genuine improvement. `autoagent new` guides users through a deep interview, generates benchmarks when needed, and `autoagent report` delivers a clear story of what happened overnight.

## Success Criteria

- User runs `autoagent new`, answers questions about their goal, and gets a complete config written to `.autoagent/` that `autoagent run` consumes without manual editing
- Interview challenges vague input — "make it better" triggers probing follow-ups, not acceptance
- When no benchmark is provided, the system generates one from goal + sample data, validates it for leakage and discriminating power, and writes it to `.autoagent/`
- `autoagent report` on a completed optimization run produces a readable markdown file with best score trajectory, top architectures, cost breakdown, and recommendations
- Full cold-start flow works: vague goal → interview → generated benchmark → optimization iterations → morning report

## Key Risks / Unknowns

- **Interview quality** — The interview must extract a useful optimization spec from vague, varied input ("improve RAG" vs "minimize latency"). This is the GSD-2 pattern applied to an open-ended domain. Hard to test mechanically.
- **Benchmark generation quality** — Automatically generating meaningful `{input, expected}` data from a vague goal is genuinely hard. Generated benchmarks must actually measure what the user cares about, not be trivially solvable or unsolvable.
- **Interview → config format** — The interview captures more than `ProjectConfig` currently holds (search space constraints, metric priorities, domain context). Extension scope must be bounded carefully.

## Proof Strategy

- **Interview quality** → retire in S01 by building the real `autoagent new` command with LLM-driven multi-turn conversation that populates config. Proven when the interview produces a valid config from deliberately vague input.
- **Benchmark generation quality** → retire in S02 by building the generator with baseline validation (scores between 0.1–0.9 on a trivial pipeline) and leakage checking. Proven when a generated benchmark is consumed by the evaluation loop.
- **Interview → config format** → retire in S01 by extending `ProjectConfig` with the minimal fields needed and creating a supplementary `context.md` for richer meta-agent context.

## Verification Classes

- Contract verification: pytest tests for interview spec output, benchmark format/validation, report section generation
- Integration verification: CLI commands (`autoagent new`, `autoagent report`) produce expected artifacts; generated benchmarks pass through evaluation loop
- Operational verification: none (no daemons or services)
- UAT / human verification: interview question quality with real LLM (manual spot-check, not gating)

## Milestone Definition of Done

This milestone is complete only when all are true:

- `autoagent new` runs a multi-turn interview and writes a complete config to `.autoagent/`
- Interview probes vague answers with follow-up questions (tested with MockLLM sequences)
- Benchmark generator produces valid `{input, expected}` JSON that passes leakage and baseline validation
- `autoagent report` reads archive data and produces a markdown report with score trajectory, top architectures, cost breakdown, and recommendations
- End-to-end flow works with MockLLM: interview → config → benchmark generation → loop iterations → report
- All tests pass (existing 381 + new M004 tests)

## Requirement Coverage

- Covers: R007 (interview, primary S01), R023 (benchmark generation, primary S02)
- Partially covers: R009 (leakage — benchmark generation reuses existing LeakageChecker, supporting S02)
- Supporting validated requirements: R015 (cold-start, S01 produces spec it consumes), R019 (fire-and-forget, S03 completes morning report), R006 (CLI, S03 adds new commands), R017 (budget, S03 reports cost)
- Not relevant to M004: R011, R012, R013, R018, R024 (M002 scope), R010, R014, R020, R021 (M003 scope, validated)
- Orphan risks: none

## Slices

- [x] **S01: Interview Orchestrator** `risk:high` `depends:[]`
  > After this: `autoagent new` runs a multi-turn LLM-driven interview, challenges vague input with follow-ups, and writes a complete config to `.autoagent/config.json` plus `context.md` — proven via MockLLM test sequences and CLI integration test
- [ ] **S02: Benchmark Generation** `risk:medium` `depends:[S01]`
  > After this: when the interview finds no benchmark, the system generates `{input, expected}` JSON from goal + sample data, validates for leakage and discriminating power, and writes to `.autoagent/benchmark.json` — proven via MockLLM generation + validation tests
- [ ] **S03: Reporting & End-to-End Assembly** `risk:low` `depends:[S01,S02]`
  > After this: `autoagent report` produces a markdown report with score trajectory, top architectures, cost breakdown, and recommendations. End-to-end integration test proves the full flow: `autoagent new` → benchmark generation → `autoagent run` → `autoagent report` — all with MockLLM

## Boundary Map

### S01 → S02

Produces:
- Extended `ProjectConfig` with optional fields: `search_space` (list of strings), `constraints` (list of strings), `metric_priorities` (list of strings)
- `context.md` in `.autoagent/` — rich narrative context for the meta-agent
- `InterviewOrchestrator` class using `LLMProtocol` for multi-turn conversation
- `autoagent new` CLI subcommand that runs the interview and writes config
- Interview state: structured dict of user answers persisted incrementally

Consumes:
- nothing (first slice)

### S02 → S03

Produces:
- `BenchmarkGenerator` class that takes goal + optional sample data, produces `{input, expected}` JSON
- Baseline validation: generated benchmark scored by trivial pipeline, scores must be 0.1–0.9
- Integration with `LeakageChecker` for generated benchmark validation
- Generated benchmark file at the path specified in `ProjectConfig.benchmark.dataset_path`

Consumes:
- `ProjectConfig` with goal and benchmark fields (S01)
- `LeakageChecker.check()` (existing M003)
- `Benchmark.from_file()` format contract (existing M001)

### S01+S02 → S03

Produces:
- `ReportGenerator` class that reads `Archive.query()` results and produces sections
- `autoagent report` CLI subcommand
- Markdown report file at `.autoagent/report.md`
- Terminal summary output
- End-to-end integration test proving full flow with MockLLM

Consumes:
- `Archive.query()` API (existing M001)
- `ArchiveEntry` fields including M003 additions (evaluation_result, pareto_evaluation, etc.)
- `ProjectConfig` from S01 interview output
- Generated benchmark from S02
- `OptimizationLoop` (existing M001–M003)
