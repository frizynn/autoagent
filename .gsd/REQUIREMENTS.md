# Requirements

This file is the explicit capability and coverage contract for the project.

Use it to track what is actively in scope, what has been validated by completed work, what is intentionally deferred, and what is explicitly out of scope.

## Active

### R001 — Autonomous Optimization Loop
- Class: core-capability
- Status: active
- Description: System runs an infinite propose→evaluate→keep/discard loop without human intervention until interrupted or budget exhausted
- Why it matters: This is the entire product — autonomous architecture search
- Source: user
- Primary owning slice: M001/S05
- Supporting slices: M001/S06
- Validation: unmapped
- Notes: Must be truly autonomous — "NEVER STOP" per autoresearch pattern

### R002 — Single-File Mutation Constraint
- Class: constraint
- Status: active
- Description: All pipeline mutations are constrained to a single `pipeline.py` file — clean diffs, reviewable, tractable search space
- Why it matters: Prevents search space explosion, keeps every iteration a clean diff
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: M001/S05
- Validation: unmapped
- Notes: Mirrors autoresearch's `train.py` constraint

### R003 — Instrumented Primitives
- Class: core-capability
- Status: active
- Description: Pipeline building blocks (LLM, Retriever, Tool, Agent) auto-measure latency, tokens, and cost without user instrumentation
- Why it matters: Gives the meta-agent rich multi-dimensional signals beyond just accuracy
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: M001/S03
- Validation: partial — primitives implemented and tested in S01; metrics captured and aggregated per-example in evaluation (S03). Full validation when used in live optimization loop (S05).
- Notes: Provider-agnostic — must work with OpenAI, Anthropic, local models, any retrieval backend

### R004 — Monotonic Archive
- Class: core-capability
- Status: active
- Description: Every attempt (success or failure) is recorded with full metrics, diffs, and rationale — archive grows monotonically, never pruned
- Why it matters: Failures are as valuable as successes; the meta-agent learns from the full history
- Source: user
- Primary owning slice: M001/S04
- Supporting slices: M002/S01
- Validation: partial — Archive module implemented in S04 with ArchiveEntry (metrics, diff, rationale, timestamp), atomic writes, query/filter/sort, 32 tests passing. Full validation when wired into live optimization loop (S05).
- Notes: Must include metrics vector, pipeline diff, meta-agent rationale, timestamp

### R005 — Crash-Recoverable Disk State
- Class: continuity
- Status: active
- Description: All state lives on disk in `.autoagent/`. Kill at any point, restart, continue from last committed iteration
- Why it matters: Overnight runs must survive crashes — no lost work
- Source: user
- Primary owning slice: M001/S06
- Supporting slices: M001/S02
- Validation: partial — atomic writes, PID-based lock with stale detection implemented in S02. Full crash recovery (kill/restart/resume) in S06.
- Notes: GSD-2 style — lock files, state reconstruction from disk

### R006 — PI-Based CLI
- Class: core-capability
- Status: active
- Description: CLI built on PI SDK with GSD-2 style commands (`autoagent init`, `autoagent run`, `autoagent status`)
- Why it matters: Consistent UX with GSD-2, leverages PI's agent harness for the meta-agent
- Source: user
- Primary owning slice: M001/S02
- Supporting slices: M004/S05
- Validation: partial — CLI commands work via argparse (D017: PI is Node.js, no Python SDK). init/status/run implemented. Full meta-agent integration in S05.
- Notes: Meta-agent runs on user's coding agent subscription (Claude Code Max, Codex, etc.). Reinterpreted as standard Python CLI per D017.

### R007 — GSD-2 Depth Interview Phase
- Class: primary-user-loop
- Status: active
- Description: Before optimization begins, orchestrator deeply interrogates the user about goal, metrics, constraints, search space — investigates codebase, checks library docs, challenges vagueness
- Why it matters: Garbage in, garbage out — the interview quality determines optimization quality
- Source: user
- Primary owning slice: M004/S01
- Supporting slices: M004/S02, M004/S03
- Validation: unmapped
- Notes: Must probe gray areas, not just collect inputs

### R008 — Benchmark-Driven Evaluation
- Class: core-capability
- Status: active
- Description: Every iteration is scored against an explicit benchmark dataset + scoring function — always try to have something explicit
- Why it matters: Without explicit measurement, optimization is blind
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: M004/S02
- Validation: partial — Benchmark loader, Evaluator, and EvaluationResult implemented in S03 with 29 tests. Full validation when integrated into optimization loop (S05).
- Notes: If user provides no benchmark, system should create one (see R023)

### R009 — Data Leakage Guardrail
- Class: quality-attribute
- Status: active
- Description: Every evaluation step checks for train/test contamination before running benchmarks — permanent guardrail, not one-time check
- Why it matters: User's #1 concern alongside reward hacking — leaky benchmarks make all improvements fake
- Source: user
- Primary owning slice: M003/S04
- Supporting slices: M001/S03
- Validation: unmapped
- Notes: "ALWAYS CHECK IN EVERY STEP BEFORE RUNNING BENCHMARKS" — user's exact words. Could be via prompting or mechanical checks.

### R010 — Multi-Metric Pareto Evaluation
- Class: quality-attribute
- Status: active
- Description: Track multiple metrics (primary goal + latency + cost + code quality); reject changes that game primary metric at expense of others
- Why it matters: Prevents reward hacking — user's nightmare is waking up to gamed metrics with degraded quality
- Source: user
- Primary owning slice: M003/S05
- Supporting slices: M001/S03
- Validation: unmapped
- Notes: Meta-agent sees full metric vector, not scalar score

### R011 — Structural Search
- Class: core-capability
- Status: active
- Description: Meta-agent can change pipeline topology — swap RAG→CAG, add rerankers, introduce debate/reflexion, swap models, add parallel agents
- Why it matters: The most valuable improvements come from architecture changes, not parameter tweaks
- Source: user
- Primary owning slice: M002/S02
- Supporting slices: M002/S04
- Validation: unmapped
- Notes: Highest risk area — search intelligence determines product value

### R012 — Parameter Optimization
- Class: core-capability
- Status: active
- Description: DSPy/Optuna-style prompt tuning and hyperparameter optimization within a fixed architecture
- Why it matters: Once a good topology is found, tuning extracts remaining performance
- Source: user
- Primary owning slice: M002/S03
- Supporting slices: M002/S04
- Validation: unmapped
- Notes: Complementary to structural search, not replacement

### R013 — Autonomous Search Strategy
- Class: core-capability
- Status: active
- Description: Meta-agent decides freely when to do structural vs parameter search based on archive history — no explicit phase switching
- Why it matters: Rigid phases miss opportunities; the meta-agent should read the landscape and choose
- Source: user
- Primary owning slice: M002/S04
- Supporting slices: M002/S01
- Validation: unmapped
- Notes: ADAS-like autonomous decision-making

### R014 — TLA+ Verification for All Pipelines
- Class: quality-attribute
- Status: active
- Description: Every proposed pipeline gets a TLA+ spec generated and model-checked by TLC before evaluation — catches deadlocks, infinite loops, termination failures
- Why it matters: Burns tokens on verification instead of burning tokens on broken evaluations
- Source: user
- Primary owning slice: M003/S01
- Supporting slices: M003/S02, M003/S03
- Validation: unmapped
- Notes: Universal gate (all pipelines, not just concurrent). Genefication pattern: LLM drafts spec → TLC verifies → iterate.

### R015 — Cold-Start Pipeline Generation
- Class: core-capability
- Status: active
- Description: Given only goal + benchmark data (no existing pipeline), generate initial `pipeline.py` and begin optimizing from scratch
- Why it matters: Lowers barrier to entry — user doesn't need to write the first pipeline
- Source: user
- Primary owning slice: M002/S05
- Supporting slices: M004/S01
- Validation: unmapped
- Notes: Generated pipeline must use instrumented primitives

### R016 — Archive Compression for Scale
- Class: continuity
- Status: active
- Description: After many iterations, archive is compressed into structured summary (top-K, failure clusters, unexplored regions) that fits context window, with drill-down capability
- Why it matters: After 200 iterations, raw archive exceeds any context window — compression preserves intelligence
- Source: user
- Primary owning slice: M002/S01
- Supporting slices: M001/S04
- Validation: unmapped
- Notes: Like GSD-2's summary compression for downstream tasks

### R017 — Hard Budget Ceiling with Auto-Pause
- Class: operability
- Status: active
- Description: Dollar ceiling that auto-pauses the loop before overspending — user can run on Claude Code Max subscription or similar
- Why it matters: Overnight runs must not drain accounts
- Source: user
- Primary owning slice: M001/S06
- Supporting slices: M004/S04
- Validation: unmapped
- Notes: Budget tracks both meta-agent LLM cost and pipeline evaluation cost

### R018 — Provider-Agnostic Primitives
- Class: integration
- Status: active
- Description: Pipeline primitives can call any LLM provider (OpenAI, Anthropic, local), any retrieval system (Pinecone, FAISS, BM25), any tool API
- Why it matters: Users have different stacks — the system must not lock them in
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: unmapped
- Notes: Like GSD-2's provider agnosticism

### R019 — Fire-and-Forget Operation
- Class: primary-user-loop
- Status: active
- Description: Launch with goal and budget, check results later — system runs completely unattended
- Why it matters: The core UX — start at 11pm, check at 8am, be surprised by genuine improvements
- Source: user
- Primary owning slice: M001/S06
- Supporting slices: M004/S04
- Validation: unmapped
- Notes: No interactive approval, no human-in-the-loop per iteration

### R020 — Simplicity Criterion
- Class: quality-attribute
- Status: active
- Description: Changes that add complexity for marginal gains are rejected — simpler is better, all else equal
- Why it matters: Prevents reward hacking via complexity accumulation; keeps pipelines readable and debuggable
- Source: research (autoresearch)
- Primary owning slice: M003/S05
- Supporting slices: none
- Validation: unmapped
- Notes: "A 0.001 improvement that adds 20 lines of hacky code? Probably not worth it." — autoresearch

### R021 — Sandbox Isolation for Pipeline Execution
- Class: compliance/security
- Status: active
- Description: Pipeline execution runs in isolated environment — model-generated code cannot access host filesystem, network, or state outside sandbox
- Why it matters: Executing untrusted model-generated code is inherently risky (ADAS safety warning)
- Source: research (ADAS)
- Primary owning slice: M003/S06
- Supporting slices: none
- Validation: unmapped
- Notes: Critical for unattended overnight runs

### R022 — Fixed Evaluation Time Budget
- Class: operability
- Status: active
- Description: Each evaluation has a fixed time budget — prevents runaway evaluations from blocking the loop
- Why it matters: One stuck evaluation shouldn't halt overnight progress
- Source: research (autoresearch)
- Primary owning slice: M001/S03
- Supporting slices: none
- Validation: partial — per-example timeout via ThreadPoolExecutor implemented in S03, timeout → score 0.0 with error="timeout". Full validation when wired into optimization loop (S05).
- Notes: Timeout → treat as failure, discard, move on

### R023 — Automatic Benchmark Generation
- Class: core-capability
- Status: active
- Description: When user provides no benchmark, system analyzes goal + data to create evaluation dataset and scoring function, validated for leakage
- Why it matters: Lowers barrier — user shouldn't need to hand-craft benchmarks for every goal
- Source: user (implied)
- Primary owning slice: M004/S02
- Supporting slices: M003/S04
- Validation: unmapped
- Notes: Generated benchmarks must pass same leakage checks as user-provided ones

### R024 — Exploration/Exploitation Balance
- Class: core-capability
- Status: active
- Description: System detects convergence stagnation and autonomously balances between exploration (new topologies) and exploitation (tuning current best)
- Why it matters: User's #2 risk concern — converging too early on local optimum or exploring too broadly and never improving
- Source: user
- Primary owning slice: M002/S04
- Supporting slices: M002/S01
- Validation: unmapped
- Notes: Must be visible in archive — why the system chose to explore vs exploit

## Validated

(none yet)

## Deferred

(none yet)

## Out of Scope

### R030 — Generic Agent Framework / Library
- Class: anti-feature
- Status: out-of-scope
- Description: AutoAgent is NOT a library of pre-built pipelines or a generic agent framework
- Why it matters: Prevents scope creep into framework territory — this is an optimization tool, not a toolkit
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: User explicitly rejected this

### R031 — Human-in-the-Loop Approval per Iteration
- Class: anti-feature
- Status: out-of-scope
- Description: No interactive approval of changes — the loop is fully autonomous
- Why it matters: Defeats the purpose of fire-and-forget overnight operation
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: User explicitly rejected this

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | core-capability | active | M001/S05 | M001/S06 | unmapped |
| R002 | constraint | active | M001/S01 | M001/S05 | unmapped |
| R003 | core-capability | active | M001/S01 | M001/S03 | partial (S01, S03) |
| R004 | core-capability | active | M001/S04 | M002/S01 | partial (S04) |
| R005 | continuity | active | M001/S06 | M001/S02 | unmapped |
| R006 | core-capability | active | M001/S02 | M004/S05 | unmapped |
| R007 | primary-user-loop | active | M004/S01 | M004/S02, M004/S03 | unmapped |
| R008 | core-capability | active | M001/S03 | M004/S02 | partial (S03) |
| R009 | quality-attribute | active | M003/S04 | M001/S03 | unmapped |
| R010 | quality-attribute | active | M003/S05 | M001/S03 | unmapped |
| R011 | core-capability | active | M002/S02 | M002/S04 | unmapped |
| R012 | core-capability | active | M002/S03 | M002/S04 | unmapped |
| R013 | core-capability | active | M002/S04 | M002/S01 | unmapped |
| R014 | quality-attribute | active | M003/S01 | M003/S02, M003/S03 | unmapped |
| R015 | core-capability | active | M002/S05 | M004/S01 | unmapped |
| R016 | continuity | active | M002/S01 | M001/S04 | unmapped |
| R017 | operability | active | M001/S06 | M004/S04 | unmapped |
| R018 | integration | active | M001/S01 | none | unmapped |
| R019 | primary-user-loop | active | M001/S06 | M004/S04 | unmapped |
| R020 | quality-attribute | active | M003/S05 | none | unmapped |
| R021 | compliance/security | active | M003/S06 | none | unmapped |
| R022 | operability | active | M001/S03 | none | partial (S03) |
| R023 | core-capability | active | M004/S02 | M003/S04 | unmapped |
| R024 | core-capability | active | M002/S04 | M002/S01 | unmapped |
| R030 | anti-feature | out-of-scope | none | none | n/a |
| R031 | anti-feature | out-of-scope | none | none | n/a |

## Coverage Summary

- Active requirements: 24
- Mapped to slices: 24
- Validated: 0
- Unmapped active requirements: 0
