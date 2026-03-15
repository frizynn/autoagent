---
id: S05
parent: M001
milestone: M001
provides:
  - MetaAgent class with prompt construction, source extraction, compile validation, cost tracking
  - ProposalResult dataclass (proposed_source, rationale, cost_usd, success, error)
  - OptimizationLoop class orchestrating propose→evaluate→keep/discard cycle
  - cmd_run wired to loop with --max-iterations CLI arg
requires:
  - slice: S01
    provides: PipelineRunner, MetricsCollector, MockLLM, PrimitivesContext
  - slice: S02
    provides: StateManager, ProjectState, ProjectConfig, CLI scaffold
  - slice: S03
    provides: Evaluator, EvaluationResult, Benchmark
  - slice: S04
    provides: Archive, ArchiveEntry, query/filter/sort
affects:
  - S06
key_files:
  - src/autoagent/meta_agent.py
  - src/autoagent/loop.py
  - src/autoagent/cli.py
  - tests/test_meta_agent.py
  - tests/test_loop.py
key_decisions:
  - Source extraction picks longest code block when multiple fenced blocks present
  - Compiled source executed into temp module to verify run() callability (not just AST parse)
  - Cost tracking via incremental diff on MetricsCollector aggregate (before/after propose)
  - First successful evaluation always kept (best_score starts None, any score beats None)
  - MetaAgent failures produce zero-score EvaluationResult stubs for archive consistency
  - PipelineRunner allowed_root passed through Evaluator for test flexibility
patterns_established:
  - MetaAgent uses LLM's collector directly; cost isolation is structural (separate collector instances)
  - SequentialMockMetaAgent pattern for deterministic loop testing
  - Failed proposals recorded as discard entries with "proposal_error:" rationale prefix
observability_surfaces:
  - ProposalResult.error — structured error string on failure
  - ProposalResult.cost_usd — per-proposal LLM cost
  - ProjectState.phase transitions (initialized→running→completed)
  - ProjectState.current_iteration increments per iteration
  - ProjectState.total_cost_usd accumulates meta-agent + evaluation costs
  - MetaAgent failures visible as discard archive entries with error rationale
drill_down_paths:
  - .gsd/milestones/M001/slices/S05/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S05/tasks/T02-SUMMARY.md
duration: 30m
verification_result: passed
completed_at: 2026-03-14
---

# S05: The Optimization Loop

**Built the autonomous propose→evaluate→keep/discard optimization loop: MetaAgent reads archive history, proposes pipeline mutations via LLM, validates extracted source, and OptimizationLoop orchestrates ≥3 iterations with state persistence, archive entries, and phase transitions.**

## What Happened

Built two core modules that wire all upstream components into the autonomous optimization cycle.

**MetaAgent** (`meta_agent.py`) reads archive history (top-K kept entries sorted by score, recent discards) and constructs a structured mutation prompt with goal, benchmark description, and current pipeline source. It calls an LLM via the primitives layer, extracts complete pipeline.py source from the response (stripping markdown fences, picking the longest block when multiple are present), validates the source compiles and has a callable `run` function, and returns a `ProposalResult` with proposed source, rationale, cost, and success flag. Cost is tracked incrementally via the LLM's MetricsCollector.

**OptimizationLoop** (`loop.py`) orchestrates the full cycle: acquire lock → set phase to "running" → for each iteration: read best pipeline → MetaAgent.propose() → handle failures as discards → write proposed source → evaluate via Evaluator → compare primary_score to best → archive with keep/discard → restore previous best on disk if discard → persist state → repeat → set phase to "completed" → release lock. Failed proposals produce zero-score EvaluationResult stubs so archive entries are always structurally complete.

Wired `cmd_run` in cli.py to read config, load benchmark, instantiate all components, and run the loop. Added `--max-iterations` arg.

## Verification

- `pytest tests/test_meta_agent.py -v` — 25/25 passed (prompt construction, source extraction, compile validation, propose flow, cost tracking)
- `pytest tests/test_loop.py -v` — 10/10 passed (≥3 iterations, keep/discard decisions, state persistence, failure handling, cost accumulation, phase transitions, archive completeness, lock release)
- `pytest tests/ -v` — 173/173 passed, zero regressions across all upstream slices

## Requirements Advanced

- R001 (Autonomous Optimization Loop) — core propose→evaluate→keep/discard loop implemented and tested with ≥3 autonomous iterations
- R002 (Single-File Mutation Constraint) — MetaAgent produces complete pipeline.py source; loop writes/restores single file
- R003 (Instrumented Primitives) — primitives fully integrated into loop via Evaluator; metrics captured per-iteration
- R004 (Monotonic Archive) — archive wired into loop; every iteration (success or failure) recorded with metrics, diff potential, and rationale
- R008 (Benchmark-Driven Evaluation) — Evaluator integrated into loop; every iteration scored against benchmark
- R022 (Fixed Evaluation Time Budget) — timeout enforcement active through Evaluator in the loop

## Requirements Validated

- R001 — loop runs ≥3 iterations autonomously with correct keep/discard decisions, state persistence, and archive entries (proven by 10 integration tests)
- R002 — MetaAgent outputs complete pipeline.py; loop writes only pipeline.py file (enforced structurally)

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

- Updated `tests/test_cli.py::TestRun::test_run_after_init` → `test_run_no_benchmark_configured` since cmd_run is no longer a stub and correctly requires a configured benchmark.

## Known Limitations

- cmd_run currently uses MockLLM — real LLM integration requires API key and is a manual verification step
- No budget ceiling or crash recovery — deferred to S06 per plan
- No exploration/exploitation strategy — MetaAgent prompt is the only search intelligence (sufficient for M001)

## Follow-ups

- S06: Budget ceiling with auto-pause, crash recovery (kill/restart/resume), fire-and-forget operation
- Manual verification: run with real LLM (OpenAI) against toy benchmark to validate mutation quality ≥50% (M001 risk proof)

## Files Created/Modified

- `src/autoagent/meta_agent.py` — MetaAgent class with ProposalResult dataclass
- `src/autoagent/loop.py` — OptimizationLoop class with run() method
- `src/autoagent/cli.py` — cmd_run wired to loop, --max-iterations added
- `tests/test_meta_agent.py` — 25 unit tests for MetaAgent
- `tests/test_loop.py` — 10 integration tests for OptimizationLoop
- `tests/test_cli.py` — Updated TestRun for cmd_run behavior change

## Forward Intelligence

### What the next slice should know
- OptimizationLoop.run() acquires/releases lock via StateManager — S06 crash recovery needs to handle stale locks when the process is killed mid-iteration
- State is persisted after each successful iteration — crash recovery can reconstruct from last committed state + archive
- `total_cost_usd` accumulates both meta-agent and evaluation costs — budget ceiling should check this before each iteration
- Phase transitions: initialized→running→completed — S06 may need a "paused" phase for budget-triggered auto-pause

### What's fragile
- Lock release is in a `finally` block but kill -9 won't execute it — S06 must handle stale locks (already supported by StateManager's PID-based stale detection)
- cmd_run currently hardcodes MockLLM — needs to read provider config and instantiate the right LLM

### Authoritative diagnostics
- `ProjectState.phase` + `current_iteration` + `total_cost_usd` — the three signals that fully describe loop progress
- Archive entries with rationale starting with `"proposal_error:"` — indicates MetaAgent failure, not evaluation failure

### What assumptions changed
- No surprises — all upstream boundaries worked as documented in the boundary map
