# S05: The Optimization Loop

**Goal:** The meta-agent reads archive history, proposes mutations to pipeline.py, evaluates them against a benchmark, and keeps or discards based on primary score — running ≥3 iterations autonomously.
**Demo:** `pytest tests/test_loop.py -v` passes, proving ≥3 mock iterations with keep/discard decisions, state persistence, and archive entries. `pytest tests/test_meta_agent.py -v` passes, proving prompt construction, source extraction, compile validation, and edge cases.

## Must-Haves

- MetaAgent reads archive history (top-K kept, recent discards) and constructs a structured mutation prompt
- MetaAgent calls an LLM (OpenAILLM or MockLLM), extracts complete pipeline.py source from response, strips markdown fences
- Extracted source is compile-validated before evaluation; invalid Python → discard with error rationale
- Extracted source is validated for `run` callable; missing run → discard with error rationale
- MetaAgent tracks its own LLM cost separately from pipeline evaluation cost
- OptimizationLoop orchestrates: read best pipeline → propose mutation → write to disk → evaluate → compare primary_score → archive with keep/discard → update state → repeat
- Loop persists state (current_iteration, best_iteration_id, total_cost_usd, phase) after every iteration
- Loop sets phase to "running" on start, "completed" on finish
- `cmd_run` in cli.py is wired to instantiate and start the loop
- Loop supports `max_iterations` parameter for bounded execution

## Proof Level

- This slice proves: integration (meta-agent + loop + all upstream modules working together)
- Real runtime required: no (MockLLM for tests; real LLM integration is a manual verification)
- Human/UAT required: no

## Verification

- `pytest tests/test_meta_agent.py -v` — unit tests for MetaAgent: prompt construction, source extraction (clean + fenced), compile validation (valid/invalid), missing run detection, cost tracking
- `pytest tests/test_loop.py -v` — integration tests for OptimizationLoop: ≥3 iterations with mock meta-agent, state persistence after each iteration, keep/discard decisions based on score, archive entries written, phase transitions
- `pytest tests/ -v` — full suite passes with zero regressions
- MetaAgent compile/validation failures produce `ProposalResult(success=False)` with structured error strings (inspectable via `result.error`); these are surfaced as discard entries with error rationale when wired into the loop

## Observability / Diagnostics

- Runtime signals: `ProjectState.phase` transitions (initialized→running→completed), `current_iteration` increments, `total_cost_usd` accumulates
- Inspection surfaces: `autoagent status` shows iteration count + cost + best iteration; `.autoagent/archive/` entries are human-readable JSON
- Failure visibility: MetaAgent compile/validation failures recorded as discard entries with error rationale in archive; loop exceptions don't corrupt state (state written after successful iteration only)
- Redaction constraints: API keys passed to OpenAILLM, never logged or persisted

## Integration Closure

- Upstream surfaces consumed: `PipelineRunner.run()`, `Evaluator.evaluate()`, `Archive.add()/query()/best()`, `StateManager.read_state()/write_state()/acquire_lock()/release_lock()`, `ProjectState/ProjectConfig`, `MetricsCollector`, `MockLLM/OpenAILLM`, `PrimitivesContext`, `Benchmark.from_file()`
- New wiring introduced: `cmd_run` → `OptimizationLoop.run()` entry point; MetaAgent → LLM call → source extraction pipeline
- What remains before the milestone is truly usable end-to-end: S06 (budget ceiling, crash recovery, fire-and-forget)

## Tasks

- [x] **T01: Build MetaAgent with prompt construction and source extraction** `est:45m`
  - Why: The meta-agent is the core intelligence — it reads history, proposes mutations, and must produce valid Python. This is the highest-risk component (mutation quality proof).
  - Files: `src/autoagent/meta_agent.py`, `tests/test_meta_agent.py`
  - Do: Build MetaAgent class that takes archive + current pipeline source + goal + benchmark info; constructs a structured prompt with top-K kept iterations and recent discards; calls an LLM via the primitives layer; extracts full pipeline.py source from the response (strip markdown fences, handle edge cases); validates extracted source compiles and has a callable `run`; tracks its own cost via a separate MetricsCollector. Return a ProposalResult dataclass with proposed_source, rationale, cost_usd, and success flag.
  - Verify: `pytest tests/test_meta_agent.py -v` — all tests pass
  - Done when: MetaAgent produces valid pipeline source from MockLLM responses, correctly rejects invalid Python, strips markdown fences, and tracks cost independently

- [x] **T02: Build OptimizationLoop, wire cmd_run, and prove ≥3 autonomous iterations** `est:45m`
  - Why: The loop is the product — propose→evaluate→keep/discard cycle running autonomously. This wires all upstream modules together and proves the M001 core loop works.
  - Files: `src/autoagent/loop.py`, `src/autoagent/cli.py`, `tests/test_loop.py`
  - Do: Build OptimizationLoop class that takes StateManager, Archive, Evaluator, MetaAgent, Benchmark, and max_iterations; orchestrates the cycle (read best pipeline → MetaAgent.propose() → write proposed source to .autoagent/pipeline.py → Evaluator.evaluate() → compare primary_score to current best → Archive.add() with keep/discard → update ProjectState → repeat); handle MetaAgent failures (compile error, missing run) as discard iterations; set phase transitions; persist state after every iteration. Wire cmd_run to instantiate the loop from disk config and run it. Use a mock meta-agent (returns canned pipeline mutations) for deterministic integration tests.
  - Verify: `pytest tests/test_loop.py -v` — ≥3 iterations, state persistence, archive entries, keep/discard logic all pass. `pytest tests/ -v` — full suite green.
  - Done when: Loop runs ≥3 iterations autonomously with mock providers, archive contains entries with correct decisions, state reflects final iteration count and best ID, phase goes running→completed

## Files Likely Touched

- `src/autoagent/meta_agent.py` (new)
- `src/autoagent/loop.py` (new)
- `src/autoagent/cli.py` (modify cmd_run)
- `tests/test_meta_agent.py` (new)
- `tests/test_loop.py` (new)
