# M001: Core Loop & Infrastructure

**Vision:** Build the foundational optimization loop — pipeline execution, CLI, archive, the propose→evaluate→keep/discard cycle, budget management, and crash recovery. By the end of M001, `autoagent run` works end-to-end: the meta-agent autonomously iterates on pipeline.py against a benchmark, keeps or discards changes, and respects budget limits.

## Success Criteria

- `autoagent init` scaffolds a project with pipeline.py, benchmark config, and .autoagent/ state directory
- `autoagent run` executes ≥3 autonomous optimization iterations with real LLM calls
- Each iteration produces an archive entry with metrics (latency, tokens, cost, primary score), diff, and rationale
- Budget ceiling triggers auto-pause before the configured limit is exceeded
- Kill the process mid-iteration, restart, and it resumes without re-running completed iterations
- Pipeline.py is the only file mutated by the meta-agent

## Key Risks / Unknowns

- **Pipeline execution model** — Loading arbitrary Python from pipeline.py, executing it with instrumented primitives, and capturing structured metrics reliably. If this doesn't work cleanly, nothing else matters.
- **Meta-agent mutation quality** — Even basic mutations need to produce valid, runnable Python. A meta-agent that generates broken code 90% of the time makes the loop useless.
- **PI SDK integration** — Building a CLI on PI in the style of GSD-2. Need to understand PI's extension model and how to invoke the meta-agent as an agent session.

## Proof Strategy

- Pipeline execution model → retire in S01 by proving a hand-written pipeline.py executes and reports metrics through instrumented primitives
- Meta-agent mutation quality → retire in S05 by proving the meta-agent produces runnable mutations that pass evaluation at least 50% of the time
- PI SDK integration → retire in S02 by proving `autoagent init` and `autoagent status` work as PI CLI commands

## Verification Classes

- Contract verification: pytest unit tests for primitives, archive format, state management
- Integration verification: end-to-end `autoagent run` with real LLM calls against a toy benchmark
- Operational verification: crash recovery (kill and restart), budget auto-pause
- UAT / human verification: the "fire and forget" experience — run overnight, check results

## Milestone Definition of Done

This milestone is complete only when all are true:

- All 6 slice deliverables are complete and verified
- `autoagent init` creates a working project scaffold
- `autoagent run` completes ≥3 autonomous iterations with real LLM API calls
- Archive contains iterations with multi-metric results, diffs, and meta-agent rationale
- Budget ceiling auto-pauses the loop
- Crash recovery works: kill mid-iteration, restart, resume from disk state
- Pipeline.py single-file constraint is enforced
- All success criteria are re-checked against live behavior

## Requirement Coverage

- Covers: R001, R002, R003, R004, R005, R006, R008, R017, R018, R019, R022
- Partially covers: R009 (basic leakage awareness, full detection in M003), R010 (metrics collected, Pareto enforcement in M003)
- Leaves for later: R007, R009 (full), R010 (full), R011, R012, R013, R014, R015, R016, R020, R021, R023, R024
- Orphan risks: none

## Slices

- [x] **S01: Pipeline Execution Engine** `risk:high` `depends:[]`
  > After this: a hand-written pipeline.py using instrumented primitives (LLM, Retriever) runs and reports latency, tokens, cost metrics to stdout. Proven by running a toy RAG pipeline against a mock LLM provider.

- [x] **S02: CLI Scaffold & Disk State** `risk:medium` `depends:[]`
  > After this: `autoagent init` creates .autoagent/ project structure with state files; `autoagent status` reads and displays current state from disk. Proven by CLI commands producing correct filesystem output.

- [x] **S03: Evaluation & Benchmark** `risk:medium` `depends:[S01]`
  > After this: a pipeline runs against a provided benchmark dataset with a scoring function; multi-metric results (primary score + latency + tokens + cost) are captured in a structured evaluation result. Proven by evaluating a toy pipeline against a toy benchmark.

- [x] **S04: Monotonic Archive** `risk:low` `depends:[S01,S03]`
  > After this: multiple pipeline iterations are archived on disk with full metrics, pipeline.py diffs, and meta-agent rationale; archive is readable and queryable. Proven by writing 5+ iterations and reading them back with filtering.

- [ ] **S05: The Optimization Loop** `risk:high` `depends:[S01,S02,S03,S04]`
  > After this: the meta-agent reads the archive, proposes a mutation to pipeline.py, evaluates it against the benchmark, and keeps or discards based on metrics — runs ≥3 iterations autonomously. Proven by running the loop with real LLM calls against a toy benchmark.

- [ ] **S06: Budget, Recovery & Fire-and-Forget** `risk:medium` `depends:[S05]`
  > After this: `autoagent run --budget 5.00` runs with hard budget ceiling and auto-pause; process can be killed and restarted without losing progress; fire-and-forget operation works end-to-end. Proven by budget-triggered pause and kill/restart recovery test.

## Boundary Map

### S01 → S03
Produces:
- `src/autoagent/primitives.py` → `LLM`, `Retriever`, `Tool`, `Agent` base classes with instrumentation (latency, tokens, cost auto-captured)
- `src/autoagent/pipeline.py` → `PipelineRunner` that loads and executes a user's pipeline.py, returns `PipelineResult` with captured metrics
- `src/autoagent/types.py` → `MetricsSnapshot` (latency_ms, tokens_in, tokens_out, cost_usd, custom_metrics dict), `PipelineResult`

Consumes: nothing (first slice)

### S01 → S05
Produces:
- `PipelineRunner.run(pipeline_path, input_data)` → executes pipeline, returns `PipelineResult`
- Provider-agnostic primitive registry — `LLM(provider="openai", model="gpt-4o")` pattern

Consumes: nothing (first slice)

### S02 → S05
Produces:
- `src/autoagent/cli.py` → `init`, `run`, `status` command handlers
- `src/autoagent/state.py` → `StateManager` that reads/writes `.autoagent/state.json`, handles lock files
- `.autoagent/` directory convention: `state.json`, `config.json`, `archive/`, `pipeline.py`

Consumes: nothing (parallel first slice)

### S03 → S04
Produces:
- `src/autoagent/evaluation.py` → `Evaluator` that runs pipeline against benchmark, returns `EvaluationResult` with multi-metric vector
- `src/autoagent/benchmark.py` → `Benchmark` loader (dataset + scoring function), `ScoringResult`
- `EvaluationResult` → primary_score, metrics: `MetricsSnapshot`, benchmark_id, timestamp, duration_ms

Consumes from S01:
- `PipelineRunner.run()` to execute the pipeline
- `MetricsSnapshot` type for structured metrics

### S03 → S05
Produces:
- `Evaluator.evaluate(pipeline_path, benchmark)` → `EvaluationResult`
- Fixed time budget enforcement (timeout → treat as failure)

Consumes from S01:
- `PipelineRunner` for pipeline execution

### S04 → S05
Produces:
- `src/autoagent/archive.py` → `Archive` that stores/retrieves iterations on disk
- `ArchiveEntry` → iteration_id, timestamp, pipeline_diff, evaluation_result, rationale, decision (keep/discard), parent_iteration_id
- `Archive.query()` → filter by decision, sort by metric, get best/worst/recent
- On-disk format: `.autoagent/archive/NNN-{keep|discard}.json` + `.autoagent/archive/NNN-pipeline.py`

Consumes from S01:
- `PipelineResult`, `MetricsSnapshot` types

Consumes from S03:
- `EvaluationResult` type

### S05 → S06
Produces:
- `src/autoagent/loop.py` → `OptimizationLoop` that orchestrates propose→evaluate→keep/discard
- `src/autoagent/meta_agent.py` → `MetaAgent` that reads archive and proposes pipeline mutations
- Loop state persisted to `.autoagent/state.json` after each iteration (current_iteration, best_iteration_id, total_cost)

Consumes from S01:
- `PipelineRunner` for execution

Consumes from S02:
- `StateManager` for disk state, `cli.py` for `run` command entry point

Consumes from S03:
- `Evaluator` for benchmark scoring

Consumes from S04:
- `Archive` for reading history and writing new entries

### S06 (terminal slice)
Produces:
- Budget tracking and auto-pause in `OptimizationLoop`
- Crash recovery: lock file protocol, state reconstruction from archive
- `autoagent run --budget N` CLI integration

Consumes from S05:
- `OptimizationLoop`, `MetaAgent`, loop state protocol
