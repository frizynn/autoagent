# Requirements

This file is the explicit capability and coverage contract for the project.

Use it to track what is actively in scope, what has been validated by completed work, what is intentionally deferred, and what is explicitly out of scope.

## Active

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

### R009 — Data Leakage Guardrail
- Class: quality-attribute
- Status: validated
- Description: Every evaluation step checks for train/test contamination before running benchmarks — permanent guardrail, not one-time check
- Why it matters: User's #1 concern alongside reward hacking — leaky benchmarks make all improvements fake
- Source: user
- Primary owning slice: M003/S03
- Supporting slices: M001/S03
- Validation: validated — LeakageChecker performs two-tier detection: AST-based exact-match blocking (serialized benchmark examples vs pipeline string literals) and word-level n-gram fuzzy warnings (Jaccard > 0.3). Short examples (<10 chars) skipped. Gate wired into loop after TLA+, before evaluation. Blocked iterations discarded with rationale. Results persisted in ArchiveEntry.leakage_check. 26 tests (21 unit + 5 integration). Contract-level proof in S03.
- Notes: "ALWAYS CHECK IN EVERY STEP BEFORE RUNNING BENCHMARKS" — user's exact words. Could be via prompting or mechanical checks.

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
- Status: validated
- Description: Every proposed pipeline gets a TLA+ spec generated and model-checked by TLC before evaluation — catches deadlocks, infinite loops, termination failures
- Why it matters: Burns tokens on verification instead of burning tokens on broken evaluations
- Source: user
- Primary owning slice: M003/S01
- Supporting slices: M003/S02, M003/S03
- Validation: validated — TLAVerifier generates TLA+ specs via LLM, model-checks via TLC subprocess with genefication retry (max 3 attempts per D048), complexity threshold skip (D047), graceful degradation when Java unavailable (D043). Loop gate blocks failing proposals before evaluation. 29 unit tests + 7 integration tests. Contract-level proof in S01.
- Notes: Universal gate (all pipelines, not just concurrent). Genefication pattern: LLM drafts spec → TLC verifies → iterate.


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

### R021 — Sandbox Isolation for Pipeline Execution
- Class: compliance/security
- Status: validated
- Description: Pipeline execution runs in isolated environment — model-generated code cannot access host filesystem, network, or state outside sandbox
- Why it matters: Executing untrusted model-generated code is inherently risky (ADAS safety warning)
- Source: research (ADAS)
- Primary owning slice: M003/S04
- Supporting slices: none
- Validation: validated — SandboxRunner executes pipeline code inside Docker container with --network=none and docker cp source transfer. Container-side harness avoids package install. available() checks binary + daemon. Graceful fallback to PipelineRunner when Docker unavailable (D043). SandboxResult carries fallback_reason and error diagnostics. sandbox_execution field in ArchiveEntry for post-run inspection. 18 unit tests + 4 loop integration + 2 capstone. Contract-level proof in S04.
- Notes: Critical for unattended overnight runs

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

### R010 — Multi-Metric Pareto Evaluation
- Class: quality-attribute
- Status: validated
- Description: Track multiple metrics (primary goal + latency + cost + code quality); reject changes that game primary metric at expense of others
- Why it matters: Prevents reward hacking — user's nightmare is waking up to gamed metrics with degraded quality
- Source: user
- Primary owning slice: M003/S02
- Supporting slices: M001/S03
- Validation: validated — Pareto dominance across 4-metric vector (primary_score, latency_ms, cost_usd, complexity) with direction-aware comparison. pareto_dominates() checks standard dominance, pareto_decision() orchestrates with simplicity tiebreaker. Wired into loop replacing score-only comparison. 28 unit tests + loop integration. Contract-level proof in S02.
- Notes: Meta-agent sees full metric vector, not scalar score

### R020 — Simplicity Criterion
- Class: quality-attribute
- Status: validated
- Description: Changes that add complexity for marginal gains are rejected — simpler is better, all else equal
- Why it matters: Prevents reward hacking via complexity accumulation; keeps pipelines readable and debuggable
- Source: research (autoresearch)
- Primary owning slice: M003/S02
- Supporting slices: none
- Validation: validated — AST-based compute_complexity() scores code complexity. Incomparable Pareto candidates resolved by preferring simpler source (D042). Equal complexity → conservative discard. Unparseable source → float('inf') → always loses. 28 unit tests prove all branches. Contract-level proof in S02.
- Notes: "A 0.001 improvement that adds 20 lines of hacky code? Probably not worth it." — autoresearch

### R001 — Autonomous Optimization Loop
- Class: core-capability
- Status: validated
- Description: System runs an infinite propose→evaluate→keep/discard loop without human intervention until interrupted or budget exhausted
- Why it matters: This is the entire product — autonomous architecture search
- Source: user
- Primary owning slice: M001/S05
- Supporting slices: M001/S06
- Validation: validated — Loop runs ≥3 autonomous iterations with keep/discard decisions, state persistence, and archive entries (S05, 10 integration tests). Budget/interrupt handling in S06.

### R002 — Single-File Mutation Constraint
- Class: constraint
- Status: validated
- Description: All pipeline mutations are constrained to a single `pipeline.py` file — clean diffs, reviewable, tractable search space
- Why it matters: Prevents search space explosion, keeps every iteration a clean diff
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: M001/S05
- Validation: validated — MetaAgent outputs complete pipeline.py; loop writes/restores only pipeline.py (S01 + S05).

### R003 — Instrumented Primitives
- Class: core-capability
- Status: validated
- Description: Pipeline building blocks (LLM, Retriever, Tool, Agent) auto-measure latency, tokens, and cost without user instrumentation
- Why it matters: Gives the meta-agent rich multi-dimensional signals beyond just accuracy
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: M001/S03
- Validation: validated — Primitives integrated into optimization loop via Evaluator; metrics captured per-iteration in S05.
- Notes: Provider-agnostic — must work with OpenAI, Anthropic, local models, any retrieval backend

### R004 — Monotonic Archive
- Class: core-capability
- Status: validated
- Description: Every attempt (success or failure) is recorded with full metrics, diffs, and rationale — archive grows monotonically, never pruned
- Why it matters: Failures are as valuable as successes; the meta-agent learns from the full history
- Source: user
- Primary owning slice: M001/S04
- Supporting slices: M002/S01
- Validation: validated — Archive wired into optimization loop; every iteration (success or failure) recorded with metrics and rationale (S04 + S05).
- Notes: Must include metrics vector, pipeline diff, meta-agent rationale, timestamp

### R005 — Crash-Recoverable Disk State
- Class: continuity
- Status: validated
- Description: All state lives on disk in `.autoagent/`. Kill at any point, restart, continue from last committed iteration
- Why it matters: Overnight runs must survive crashes — no lost work
- Source: user
- Primary owning slice: M001/S06
- Supporting slices: M001/S02
- Validation: validated — Atomic writes and PID-based lock (S02). Full crash recovery: resume from archive with best_score reconstruction, pipeline.py restoration from archive's best kept entry, iteration continuity across restarts (S06, 7 tests).
- Notes: GSD-2 style — lock files, state reconstruction from disk

### R006 — PI-Based CLI
- Class: core-capability
- Status: validated
- Description: CLI built on PI SDK with GSD-2 style commands (`autoagent init`, `autoagent run`, `autoagent status`)
- Why it matters: Consistent UX with GSD-2, leverages PI's agent harness for the meta-agent
- Source: user
- Primary owning slice: M001/S02
- Supporting slices: M004/S05
- Validation: validated — cmd_run wired to OptimizationLoop in S05; init/status/run all functional via argparse.
- Notes: Meta-agent runs on user's coding agent subscription (Claude Code Max, Codex, etc.). Reinterpreted as standard Python CLI per D017.

### R008 — Benchmark-Driven Evaluation
- Class: core-capability
- Status: validated
- Description: Every iteration is scored against an explicit benchmark dataset + scoring function — always try to have something explicit
- Why it matters: Without explicit measurement, optimization is blind
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: M004/S02
- Validation: validated — Evaluator integrated into optimization loop; every iteration scored against benchmark (S03 + S05).
- Notes: If user provides no benchmark, system should create one (see R023)

### R017 — Hard Budget Ceiling with Auto-Pause
- Class: operability
- Status: validated
- Description: Dollar ceiling that auto-pauses the loop before overspending — user can run on Claude Code Max subscription or similar
- Why it matters: Overnight runs must not drain accounts
- Source: user
- Primary owning slice: M001/S06
- Supporting slices: M004/S04
- Validation: validated — Hard ceiling check before each iteration, pre-iteration cost estimation using global average, phase="paused" on budget exhaustion (S06, 2 tests).
- Notes: Budget tracks both meta-agent LLM cost and pipeline evaluation cost

### R019 — Fire-and-Forget Operation
- Class: primary-user-loop
- Status: validated
- Description: Launch with goal and budget, check results later — system runs completely unattended
- Why it matters: The core UX — start at 11pm, check at 8am, be surprised by genuine improvements
- Source: user
- Primary owning slice: M001/S06
- Supporting slices: M004/S04
- Validation: validated — Autonomous loop (S05) + budget ceiling auto-pause (S06) + crash recovery with resume (S06) together prove unattended operation. No human-in-the-loop per iteration.
- Notes: No interactive approval, no human-in-the-loop per iteration

### R022 — Fixed Evaluation Time Budget
- Class: operability
- Status: validated
- Description: Each evaluation has a fixed time budget — prevents runaway evaluations from blocking the loop
- Why it matters: One stuck evaluation shouldn't halt overnight progress
- Source: research (autoresearch)
- Primary owning slice: M001/S03
- Supporting slices: none
- Validation: validated — Per-example timeout implemented in S03, wired into optimization loop in S05. Timeout → score 0.0, discard, continue.
- Notes: Timeout → treat as failure, discard, move on

### R016 — Archive Compression for Scale
- Class: continuity
- Status: validated
- Description: After many iterations, archive is compressed into structured summary (top-K, failure clusters, unexplored regions) that fits context window, with drill-down capability
- Why it matters: After 200 iterations, raw archive exceeds any context window — compression preserves intelligence
- Source: user
- Primary owning slice: M002/S01
- Supporting slices: M001/S04
- Validation: validated — ArchiveSummarizer produces structured summaries with 4 sections (Top-K Results, Failure Clusters, Unexplored Regions, Score Trends) from 50+ entries within ~3K token budget. OptimizationLoop switches from raw entries to summaries past configurable threshold. Compression cost tracked in budget. Graceful fallback on failure. 25 tests (17 unit + 8 integration). Drill-down capability deferred.
- Notes: Like GSD-2's summary compression for downstream tasks

### R015 — Cold-Start Pipeline Generation
- Class: core-capability
- Status: validated
- Description: Given only goal + benchmark data (no existing pipeline), generate initial `pipeline.py` and begin optimizing from scratch
- Why it matters: Lowers barrier to entry — user doesn't need to write the first pipeline
- Source: user
- Primary owning slice: M002/S04
- Supporting slices: M004/S01
- Validation: validated — Benchmark.describe() produces compact benchmark description. MetaAgent.generate_initial() generates pipeline via LLM using goal + component vocabulary + benchmark description, validates with _extract_source() → _validate_source(). cmd_run() detects starter template, triggers cold-start with retry + fallback. 17 tests (6 benchmark, 7 generation, 4 CLI integration). 267 total tests passing.
- Notes: Generated pipeline must use instrumented primitives

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
| R001 | core-capability | validated | M001/S05 | M001/S06 | validated (S05) |
| R002 | constraint | validated | M001/S01 | M001/S05 | validated (S01+S05) |
| R003 | core-capability | validated | M001/S01 | M001/S03 | validated (S01+S03+S05) |
| R004 | core-capability | validated | M001/S04 | M002/S01 | validated (S04+S05) |
| R005 | continuity | validated | M001/S06 | M001/S02 | validated (S02+S06) |
| R006 | core-capability | validated | M001/S02 | M004/S05 | validated (S02+S05) |
| R007 | primary-user-loop | active | M004/S01 | M004/S02, M004/S03 | unmapped |
| R008 | core-capability | validated | M001/S03 | M004/S02 | validated (S03+S05) |
| R009 | quality-attribute | validated | M003/S03 | M001/S03 | validated (S03) |
| R010 | quality-attribute | validated | M003/S02 | M001/S03 | validated (S02) |
| R011 | core-capability | active | M002/S02 | M002/S04 | unmapped |
| R012 | core-capability | active | M002/S03 | M002/S04 | unmapped |
| R013 | core-capability | active | M002/S04 | M002/S01 | unmapped |
| R014 | quality-attribute | validated | M003/S01 | M003/S02, M003/S03 | validated (S01) |
| R015 | core-capability | validated | M002/S04 | M004/S01 | validated (S04) |
| R016 | continuity | validated | M002/S01 | M001/S04 | validated (S01) |
| R017 | operability | validated | M001/S06 | M004/S04 | validated (S06) |
| R018 | integration | active | M001/S01 | none | unmapped |
| R019 | primary-user-loop | validated | M001/S06 | M004/S04 | validated (S05+S06) |
| R020 | quality-attribute | validated | M003/S02 | none | validated (S02) |
| R021 | compliance/security | validated | M003/S04 | none | validated (S04) |
| R022 | operability | validated | M001/S03 | none | validated (S03+S05) |
| R023 | core-capability | active | M004/S02 | M003/S04 | unmapped |
| R024 | core-capability | active | M002/S04 | M002/S01 | unmapped |
| R030 | anti-feature | out-of-scope | none | none | n/a |
| R031 | anti-feature | out-of-scope | none | none | n/a |

## Coverage Summary

- Active requirements: 7
- Mapped to slices: 24
- Validated: 17
- Unmapped active requirements: 0
