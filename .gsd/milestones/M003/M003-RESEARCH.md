# M003: Safety & Verification — Research

**Date:** 2026-03-14

## Summary

M003 introduces four safety layers into autoagent's optimization loop: TLA+ verification, data leakage detection, multi-metric Pareto evaluation, and sandbox isolation. The codebase is clean, zero-dependency Python with a well-defined propose→evaluate→keep/discard loop (`loop.py`). Each safety feature naturally inserts as a gate at a specific point in this pipeline — TLA+ after propose (before eval), leakage check at benchmark load and before eval, Pareto at the keep/discard decision, sandbox wrapping `PipelineRunner.run()`.

The primary risk is TLA+ spec generation quality — LLMs generating correct TLA+ is harder than generating Python, and the genefication loop (draft→TLC verify→fix→repeat) could burn tokens on bad specs. The recommended approach: start with Pareto evaluation (pure Python, zero external dependencies, highest immediate value against reward hacking), then leakage detection (also pure Python), then TLA+ verification (requires Java/TLC subprocess), then sandbox (requires Docker). This ordering proves the highest-value, lowest-risk features first while deferring external dependencies.

The zero-dependency constraint (D016, `pyproject.toml`) applies to runtime `dependencies = []`. TLC (Java subprocess) and Docker are system-level tools invoked via `subprocess`, not Python package dependencies — same pattern as shelling out to `git`. The architecture should detect their availability at startup and degrade gracefully (warn + skip) when missing, rather than hard-failing.

## Recommendation

**Prove Pareto evaluation first** — it's the user's #1 concern (reward hacking), pure Python, and validates the multi-metric decision framework that all other safety features feed into. Then data leakage (also pure Python, user's other top concern). TLA+ third (external dependency but unique value). Sandbox last (heaviest infrastructure, most integration complexity). Each slice should be independently demoable: Pareto changes the keep/discard decision; leakage blocks contaminated iterations; TLA+ rejects bad specs; sandbox isolates execution.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|-------------------|------------|
| TLA+ model checking | TLC (Java, `tla2tools.jar`) via subprocess | De facto standard. No Python TLA+ checker exists. AWS uses TLC at scale. |
| Container isolation | Docker via subprocess/SDK | Proven isolation. Firecracker is overkill. Python `subprocess` with restricted perms is too leaky. |
| Pareto dominance checking | Implement from scratch (~20 lines) | Too simple to justify a dependency. Standard algorithm: point A dominates B if A ≥ B on all metrics and A > B on at least one. |
| Data leakage (train/test overlap) | Implement from scratch | Domain-specific to benchmark format. Hash-based dedup of input/expected pairs, n-gram overlap for fuzzy matching. |
| TLA+ spec generation | LLM (meta-agent's configured LLM) | Genefication pattern: LLM drafts spec, TLC validates, iterate on violations. No reliable Python→TLA+ transpiler exists. |

## Existing Code and Patterns

- `loop.py` — **Core integration point.** The `while` loop at L183 is where all gates insert. Proposal → [TLA+ gate] → [leakage gate] → evaluation → [Pareto decision] → archive. Clean linear flow, no framework abstractions to fight.
- `evaluation.py` `Evaluator.evaluate()` — **Leakage check insertion point.** Check benchmark data for contamination before running evaluation. Also wraps pipeline execution — sandbox wraps `PipelineRunner.run()` inside `_run_with_timeout()`.
- `evaluation.py` `EvaluationResult` — **Multi-metric surface.** Already captures `primary_score`, `metrics.latency_ms`, `metrics.cost_usd`, `metrics.tokens_in/out`. Pareto evaluation extends the keep/discard decision (L334 in loop.py) from `score >= best_score` to Pareto dominance check.
- `meta_agent.py` `MetaAgent.propose()` — **TLA+ spec generation point.** After `propose()` returns valid source, generate TLA+ spec from it via a separate LLM call, then run TLC. If TLC fails, the proposal is discarded (same as failed validation).
- `pipeline.py` `PipelineRunner` — **Sandbox wrapping target.** `_load_module()` and `run()` are where untrusted code executes. Sandbox replaces direct `exec()` with containerized execution.
- `archive.py` `ArchiveEntry` — **Verification result storage.** Add optional `tla_verification` field (pass/fail, violations, spec text) to archive entries. Follows D020 pattern (dict storage).
- `strategy.py` `classify_mutation()` — **Reusable pattern.** Pure function, no side effects. Same pattern for leakage checks and Pareto checks — pure functions that take data, return decisions.
- `types.py` `MetricsSnapshot` — **Metric vector for Pareto.** Already has `latency_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `custom_metrics`. Pareto operates on this vector plus `primary_score`.
- `benchmark.py` `Benchmark` — **Leakage check target.** Has `examples` list with `input`/`expected`. Leakage detection compares these against pipeline training data (if any) and checks for contamination patterns.
- `primitives.py` `MockLLM`/`MetricsCollector` — **Testing pattern.** All M003 features must be testable with mocks. TLA+ verification tests use a mock TLC subprocess. Sandbox tests use a mock Docker client.

## Constraints

- **Zero Python package dependencies** — TLC (Java) and Docker are system-level tools invoked via `subprocess.run()`, not pip packages. Must detect availability and degrade gracefully.
- **Java required for TLC** — `java -jar tla2tools.jar` subprocess. TLA2Tools is a ~15MB JAR. Must be downloadable or bundled. Java 11+ required.
- **Docker required for sandbox** — `docker run` subprocess. Must handle Docker not installed (warn, run unsandboxed with user consent).
- **Loop budget tracking** — All safety layer costs (LLM calls for spec generation, leakage analysis) must be tracked against `budget_usd` in the loop. Follow existing pattern: `total_cost += result.cost_usd`.
- **Archive backwards compatibility** — New fields on `ArchiveEntry` (e.g., `tla_verification`) must be optional with defaults to avoid breaking existing archives from M001/M002 runs.
- **Frozen dataclass pattern** — All result types are `@dataclass(frozen=True)`. New result types (ParetoResult, LeakageResult, VerificationResult) must follow this.
- **compile()+exec() for pipeline loading** — D014 mandates this. Sandbox must handle this differently (serialize source, send to container, exec there).
- **Per-example timeout** — D018 uses ThreadPoolExecutor. Sandbox adds another layer — container-level timeout as belt-and-suspenders.

## Common Pitfalls

- **TLA+ spec quality thrashing** — LLMs often generate TLA+ specs that don't type-check, use wrong syntax, or miss key invariants. Mitigation: start with a minimal spec template (just termination + eventually-produces-output), let the LLM fill in pipeline-specific details. Cap genefication iterations (3-5 attempts) to avoid infinite spec-fixing loops.
- **Pareto dimensionality trap** — With too many metrics, nothing ever dominates anything (curse of dimensionality). Mitigation: use a small fixed metric vector (primary_score, latency_ms, cost_usd, code_complexity). User can configure weights but default set should be 3-4 metrics.
- **Leakage false positives** — Aggressive string matching between train/test data flags legitimate shared vocabulary as leakage. Mitigation: check for exact example-level matches first (high precision), use n-gram overlap only as a warning, not a hard block.
- **Sandbox network access** — Pipeline code needs LLM API access from inside the container. Blocking all network kills the pipeline. Mitigation: allow outbound HTTPS to configured provider domains, block everything else.
- **Sandbox startup latency** — Docker container cold-start adds 1-5s per evaluation. With 100 benchmark examples, that's 100-500s overhead. Mitigation: start one container, run all examples in it (reuse container per iteration, not per example). Fresh container per iteration is sufficient isolation.
- **TLA+ for trivial pipelines** — A simple `def run(): return llm.complete(prompt)` doesn't benefit from formal verification. Mitigation: skip TLA+ for pipelines below a complexity threshold (e.g., < 10 LOC, no control flow). Still archive as "skipped: below complexity threshold".
- **Pareto ties** — When the new pipeline is not dominated by the old one AND doesn't dominate it (incomparable), the decision is ambiguous. Mitigation: prefer the simpler pipeline (R020 simplicity criterion) as the tiebreaker. If equal complexity, keep the current best (conservative).

## Open Risks

- **TLC availability** — Java + TLA2Tools JAR must be present. Users without Java installed need clear setup instructions or an auto-download mechanism. Could provide `autoagent setup-tla` command.
- **Docker availability** — Not all dev environments have Docker. WSL2, corporate laptops with restricted Docker access. Graceful degradation is essential — sandbox is defense-in-depth, not hard requirement.
- **TLA+ spec generation token cost** — Each spec generation is an LLM call (~2-4K tokens). With genefication (3-5 attempts), that's 6-20K tokens per iteration just for verification. At scale (200 iterations), this is significant. Budget tracking must account for this.
- **Sandbox file system isolation completeness** — Docker bind-mounts can leak. Pipeline code that `import`s from parent directories could escape. Need to copy only `pipeline.py` into the container, not mount the workspace.
- **Pareto evaluation vs. simplicity criterion interaction** — R010 (Pareto) and R020 (simplicity) could conflict. A complex pipeline that Pareto-dominates a simple one should be kept per R010 but rejected per R020. Resolution: simplicity is a metric IN the Pareto vector, not a separate gate.

## Candidate Requirements (Advisory)

These are not auto-binding. Surface for user decision:

- **R-candidate: TLA+ property vocabulary** — Define the standard set of properties every pipeline spec checks (termination, bounded-steps, eventually-produces-output). Without this, spec generation has no consistent target. Currently an open question in M003-CONTEXT.
- **R-candidate: Graceful degradation for missing tools** — When TLC/Docker aren't available, the system should warn and continue without those safety layers rather than hard-failing. This is important for developer experience but not explicitly stated in requirements.
- **R-candidate: Verification cost budget** — TLA+ spec generation and leakage analysis have their own LLM costs. Should there be a separate budget ceiling for verification overhead, or does it share the main loop budget? Currently shares (simplest), but could be split.
- **R-candidate: Complexity metric definition** — R020 says "simpler is better" but doesn't define how to measure complexity. LOC? Cyclomatic complexity? AST node count? Need a concrete metric for the Pareto vector.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| TLA+ / TLC | `melodic-software/claude-code-plugins@tla-specification` | available (12 installs) |
| TLA+ / TLC | `younes-io/agent-skills@tlaplus-workbench` | available (6 installs) |
| Docker sandbox | `joelhooks/joelclaw@docker-sandbox` | available (62 installs) |
| Sandbox security | `useai-pro/openclaw-skills-security@sandbox-guard` | available (86 installs) |

Note: TLA+ skills could help with spec template design. Docker sandbox skill could inform isolation patterns. Low install counts suggest these are niche — evaluate before installing.

## Sources

- Codebase analysis: `src/autoagent/loop.py`, `evaluation.py`, `meta_agent.py`, `pipeline.py`, `archive.py`, `strategy.py`, `types.py`, `benchmark.py`, `cli.py`, `primitives.py`
- Architecture decisions: `.gsd/DECISIONS.md` (D001-D041)
- Requirements: `.gsd/REQUIREMENTS.md` (R009, R010, R014, R020, R021)
- Project context: `.gsd/PROJECT.md`, `.gsd/milestones/M003/M003-CONTEXT.md`
- Domain knowledge: AWS TLA+ paper (formal methods at scale), ADAS paper (safety warnings for untrusted code execution), Pareto optimality theory, data leakage detection patterns in ML benchmarking
- TLC model checker: Java-based, invoked via `java -jar tla2tools.jar -modelcheck spec.tla`
- Genefication pattern: LLM generates TLA+ spec → TLC validates → LLM fixes violations → iterate until pass or max attempts
