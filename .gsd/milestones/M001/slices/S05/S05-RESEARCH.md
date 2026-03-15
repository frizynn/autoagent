# S05: The Optimization Loop — Research

**Date:** 2026-03-14

## Summary

S05 builds two new modules (`loop.py` and `meta_agent.py`) and wires them into the existing CLI's `cmd_run` stub. All four upstream modules are stable and well-tested (137 tests green): PipelineRunner loads/executes pipelines, Evaluator scores them against benchmarks, Archive stores iterations atomically, and StateManager manages disk state with locking.

The critical design question is the meta-agent: how it reads archive history, constructs a mutation prompt, calls an LLM, and extracts valid Python from the response. The boundary map says S05 produces `OptimizationLoop` (orchestrator) and `MetaAgent` (proposer). The loop itself is straightforward plumbing — the risk is mutation quality. The roadmap's proof strategy requires "runnable mutations that pass evaluation at least 50% of the time."

The zero-dependency constraint (no new runtime deps in pyproject.toml) means the meta-agent must use the existing `OpenAILLM` provider from `primitives.py` for LLM calls, or use stdlib HTTP directly. OpenAILLM is the simplest path — it already handles token counting and metrics capture. The meta-agent's own LLM costs should be tracked separately from pipeline evaluation costs since S06 needs to budget both.

## Recommendation

Build two modules with clear separation:

1. **`meta_agent.py`** — `MetaAgent` class that takes an archive, current pipeline source, benchmark info, and goal; constructs a structured prompt with archive history (top-K kept, recent discards); calls an LLM; extracts the full pipeline.py source from the response. Returns the proposed source code + rationale string. Uses `OpenAILLM` from primitives for the LLM call. Tracks its own cost via a separate `MetricsCollector`.

2. **`loop.py`** — `OptimizationLoop` class that orchestrates the cycle: read current best pipeline → call MetaAgent.propose() → write proposed pipeline to temp location → Evaluator.evaluate() → compare primary_score to current best → Archive.add() with keep/discard → update StateManager → repeat. Takes `max_iterations` (defaulting to unlimited) for testing. Persists state after every iteration so S06 can add crash recovery trivially.

Wire `cmd_run` in cli.py to instantiate and start the loop.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Pipeline execution | `PipelineRunner.run()` | Already handles compile+exec, path validation, structured errors |
| Benchmark scoring | `Evaluator.evaluate()` | Per-example timeout, metric aggregation, fresh context isolation |
| Iteration storage | `Archive.add()` | Atomic writes, diff computation, JSON + pipeline snapshot |
| Disk state | `StateManager` | Atomic writes, PID lock, state/config dataclasses |
| LLM calls for meta-agent | `OpenAILLM` from primitives | Already handles token counting, cost tracking, lazy import |
| Diff computation | `Archive.add()` baseline_source param | Already uses difflib.unified_diff internally |

## Existing Code and Patterns

- `src/autoagent/pipeline.py` — PipelineRunner.run(path, input_data, primitives_context) returns PipelineResult, never raises. Use for evaluating proposed pipelines.
- `src/autoagent/evaluation.py` — Evaluator.evaluate(pipeline_path, benchmark, timeout, primitives_factory) returns EvaluationResult. Needs a `primitives_factory` callable that returns fresh PrimitivesContext per example.
- `src/autoagent/archive.py` — Archive(dir).add(source, eval_result, rationale, decision, parent_id, baseline_source). query(decision="keep", sort_by="primary_score", ascending=False, limit=N) for top-K. best()/recent() for quick access.
- `src/autoagent/state.py` — StateManager: read_state()/write_state(), read_config()/write_config(), acquire_lock()/release_lock(). ProjectState fields: current_iteration, best_iteration_id, total_cost_usd, phase, updated_at. ProjectConfig fields: goal, benchmark (dict), budget_usd, pipeline_path.
- `src/autoagent/cli.py` — cmd_run() is a stub returning 0 with "not yet implemented" message. Wire the loop here.
- `src/autoagent/primitives.py` — OpenAILLM(model, api_key, collector) for meta-agent LLM calls. MockLLM for testing.
- `tests/fixtures/toy_pipeline.py` — Reference for what a valid pipeline.py looks like (def run(input_data, primitives)).
- `tests/fixtures/toy_benchmark.json` — 5-example benchmark for integration testing.

## Constraints

- **Zero runtime dependencies** — meta-agent LLM calls must use existing OpenAILLM or a mock. No new packages.
- **Single-file mutation constraint (D001)** — only pipeline.py is mutated. MetaAgent must output complete pipeline.py source, not patches.
- **compile()+exec() loading (D014)** — proposed pipelines are loaded the same way as originals. No import system, no __file__ relative paths.
- **Pipeline signature** — `def run(input_data, primitives=None)` must be preserved. MetaAgent prompt must enforce this.
- **Frozen dataclasses** — EvaluationResult, MetricsSnapshot, ArchiveEntry are all frozen. Can't mutate after creation.
- **Archive stores evaluation_result as dict** — not object. Use entry.evaluation_result dict directly for prompt context; reconstructed object for comparisons.
- **ProjectState.phase** — currently "initialized". Loop should set to "running" on start, back to "paused" or "completed" on stop.
- **Lock protocol** — must acquire_lock() before writing state in the loop, release on exit (including exceptions).
- **Evaluation pipeline path must be a real .py file on disk** — PipelineRunner validates the path. Proposed pipeline must be written to a temp file or the actual pipeline.py path before evaluation.

## Common Pitfalls

- **Meta-agent producing invalid Python** — LLM output often includes markdown fences, explanatory text around code. Must strip ```python fences robustly. Validate that the extracted source compiles before evaluating. If it doesn't compile, record as a discard with error rationale.
- **Meta-agent forgetting `def run(input_data, primitives=None)`** — Prompt must be explicit about required signature. Post-extraction validation: check that the module has a callable `run` attribute.
- **Evaluating pipeline at the wrong path** — PipelineRunner validates against allowed_root. The proposed pipeline must be written inside the .autoagent/ directory (e.g., overwrite .autoagent/pipeline.py or use a temp file under .autoagent/).
- **Cost tracking double-counting** — Meta-agent LLM calls vs pipeline evaluation LLM calls use different MetricsCollector instances. Don't mix them. total_cost_usd in state should track both.
- **Baseline pipeline for first iteration** — Archive.add() needs baseline_source for the first iteration's diff. Read the original pipeline.py before the loop starts.
- **Stale best_iteration_id** — If a "keep" decision happens, update both state.best_iteration_id and the actual pipeline.py used for next iteration's baseline.

## Open Risks

- **Meta-agent mutation quality at 50%** — The proof strategy requires runnable mutations ≥50% of the time. With careful prompt engineering (full pipeline source in context, explicit constraints, few-shot examples from archive), this is achievable for simple toy pipelines. Complex pipelines may have lower success rates — but that's M002's problem.
- **OpenAI API key requirement for integration tests** — Real LLM integration tests need an API key. Unit tests should use MockLLM for the meta-agent too. Need a mock meta-agent path for the test suite.
- **Token context limits** — Archive history in the meta-agent prompt grows with iterations. For M001 (proving ≥3 iterations), this is fine. R016 (archive compression) is deferred to M002.
- **Pipeline evaluation cost** — If the toy pipeline uses MockLLM, evaluation cost is $0. Real pipeline evaluation cost tracking only matters when pipelines use real LLM providers. The cost tracking plumbing should be there regardless.
- **Thread safety of StateManager** — The loop is single-threaded in M001, so no issue. S06 adds lock protocol for crash recovery.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Python optimization loops | none found | No relevant skills — standard Python patterns |
| LLM code generation | none found | Meta-agent is custom prompt engineering, not a framework |

## Sources

- Upstream slice summaries S01–S04 (preloaded context)
- Existing codebase: src/autoagent/*.py (8 modules, 137 tests passing)
- Boundary map in M001-ROADMAP.md defining S05 inputs/outputs
- DECISIONS.md (D001–D021) for established patterns
