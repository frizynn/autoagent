# M002: Search Intelligence — Research

**Date:** 2026-03-14

## Summary

M002's job is turning a working-but-dumb loop into a genuinely intelligent search process. The codebase from M001 is clean and well-structured — 2,490 lines of source across 11 modules, zero runtime dependencies, frozen dataclasses everywhere, atomic writes, never-raise patterns. The key insight from studying the existing code is that **almost all of M002's intelligence lives in the MetaAgent's prompt and the archive's query surface** — the loop orchestration, evaluation, and persistence layers are already solid and need minimal changes.

The primary recommendation is: **build intelligence through prompting, not through frameworks**. ADAS's core finding is that a meta-agent writing free-form code, informed by a growing archive of prior attempts, outperforms hand-crafted search algorithms. DSPy/Optuna add heavy dependencies and structural assumptions that fight the existing architecture. Instead, build DSPy-inspired parameter optimization (few-shot example selection, instruction tuning) as prompt strategies the meta-agent can choose, and implement archive compression as a summarization layer that sits between the raw archive and the prompt builder.

The riskiest piece is archive compression — everything else is prompt engineering at heart. Archive compression is a real data pipeline: it must preserve breakthrough signals while fitting context windows, and if it throws away the wrong information, the meta-agent gets dumber as it runs longer. This should be proven first.

## Recommendation

**Prove archive compression first (S01), then structural search (S02), then parameter optimization (S03), then wire them into autonomous strategy selection (S04), and finish with cold-start (S05).** This ordering retires risk front-to-back: archive compression is the most novel engineering, structural search is the core product value, parameter optimization is complementary, strategy selection ties them together, and cold-start is the cherry on top that depends on all prior pieces.

The meta-agent should remain a single LLM call with a rich prompt — not a multi-step agent with tool use. The prompt gets richer (archive summaries, component vocabulary, stagnation signals), but the propose→validate→evaluate loop stays unchanged. This preserves M001's clean architecture and keeps the search debuggable (you can read the prompt, read the response, understand the decision).

For structural mutations: follow ADAS's approach of free-form code generation with a component vocabulary injected into the prompt. The meta-agent sees available primitives (LLM, Retriever, Tool, Agent) and architectural patterns (RAG, CAG, debate, reflexion, ensemble, reranking) as a menu, but generates complete pipeline.py source — no AST manipulation or template systems. This aligns with D001 (single-file constraint) and D005 (autonomous strategy decisions).

For parameter optimization: implement prompt tuning as a mutation type. The meta-agent can propose changes that only modify prompts, few-shot examples, or hyperparameters (temperature, top_k, chunk_size) within a fixed topology. No DSPy dependency — just structured prompt sections that encourage parameter-focused mutations when the topology is already good.

For exploration/exploitation: implement stagnation detection from archive statistics (plateau length, score variance, novelty of recent proposals) and inject these signals into the meta-agent prompt with explicit guidance ("scores have plateaued for 8 iterations — consider a structural change" vs "recent structural change improved score by 15% — consider tuning parameters within this topology").

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Unified diff computation | `difflib.unified_diff` (already used in `archive.py`) | Archive already computes diffs — extend, don't replace |
| JSON serialization of frozen dataclasses | `dataclasses.asdict` + `from_dict` pattern (established in M001) | 6 data types already use this pattern; stay consistent |
| Atomic file writes | `_atomic_write_json` / `_atomic_write_text` (in `state.py` / `archive.py`) | Proven pattern with fsync + os.replace; reuse for summary files |
| Pipeline source validation | `MetaAgent._validate_source()` (compile + exec + check run()) | Already catches syntax errors, missing run(), non-callable run; cold-start pipelines should use same validation |
| Archive querying | `Archive.query(decision=, sort_by=, ascending=, limit=)` | Rich enough for top-K kept, recent discards, best/worst — extend if needed, don't replace |
| Cost tracking | `MetricsCollector` + `calculate_cost()` | Archive compression LLM calls should use this same path |

## Existing Code and Patterns

- `src/autoagent/meta_agent.py` — **Primary extension point for M002.** `_build_prompt()` constructs the LLM prompt from current source + archive context. M002 adds: archive summary section, component vocabulary, stagnation signals, mutation type guidance. `propose()` stays unchanged — it calls LLM, extracts source, validates. The only new capability needed is passing richer context into `_build_prompt()`.
- `src/autoagent/archive.py` — **Extension point for compression.** `Archive._load_all()` returns all entries; `Archive.query()` filters/sorts. M002 adds: `Archive.summarize()` or a separate `ArchiveSummarizer` that reads entries and produces structured summaries. The archive format (JSON files + pipeline snapshots) is stable; compression writes new summary files alongside, doesn't modify entries.
- `src/autoagent/loop.py` — **Minimal changes needed.** `OptimizationLoop.run()` currently hardcodes `top_k_kept=3, recent_discards=3` for archive context. M002 replaces this with archive summary when iteration count exceeds a threshold. The keep/discard logic stays the same. Strategy selection (structural vs parameter) happens inside the meta-agent prompt, not in the loop.
- `src/autoagent/primitives.py` — **Component vocabulary source.** The protocols (`LLMProtocol`, `RetrieverProtocol`) and concrete providers define what's available to pipelines. M002 may add `ToolProtocol`, `AgentProtocol` as new primitive types for richer topologies, but this is optional — the meta-agent can generate code using any Python, not just registered primitives.
- `src/autoagent/state.py` — **ProjectConfig may need search config fields.** Currently stores goal, benchmark, budget, pipeline_path. M002 might add `search_strategy` config (but per D005, the meta-agent decides freely — config should be hints, not hard constraints).
- `src/autoagent/evaluation.py` — **Stable, no changes expected.** Evaluator, EvaluationResult, ExampleResult are consumed by the loop and archived. M002 doesn't change how evaluation works, only how mutations are proposed.

## Constraints

- **Zero runtime dependencies** — `pyproject.toml` has `dependencies = []`. DSPy, Optuna, numpy, tiktoken — all out. Archive compression must use stdlib only (or the meta-agent's own LLM calls for summarization).
- **Single-file mutation constraint (D001)** — All mutations produce complete `pipeline.py` source. No multi-file generation, no AST manipulation libraries, no template systems.
- **compile()+exec() module loading (D014)** — Generated pipelines run in a synthetic namespace. They can't do relative imports or assume `__file__`. Cold-start pipelines must work within this constraint.
- **Autonomous strategy decisions (D005)** — No explicit phase switching between structural and parameter search. The meta-agent reads the archive and decides. Implementation provides signals, not commands.
- **Archive is append-only (D003)** — Compression produces new summary artifacts alongside existing entries, never modifies or deletes existing JSON files.
- **Provider-agnostic (D004)** — Search strategies can't assume specific LLM providers. Archive compression that uses LLM calls must use whatever LLM the meta-agent is configured with.
- **Context window limits** — At 50+ iterations, raw archive entries (~1-2KB each) could hit 100KB+. Archive summaries must compress this to ~2-5KB that fits alongside the prompt, current source, and component vocabulary.

## Common Pitfalls

- **Over-engineering the mutation grammar** — Building an AST-based mutation system (add node, remove edge, swap component) sounds rigorous but fights the ADAS finding: free-form code generation with good prompting outperforms structured mutation operators. The meta-agent should see patterns and examples, not a formal grammar. Keep it as prompt context.
- **Compressing too aggressively** — Archive summaries that only keep "top 5 results" lose the failure patterns that prevent re-exploring dead ends. Summaries need: top-K kept with rationale, clustered failure modes ("swapping to model X consistently degrades score"), and unexplored regions ("haven't tried parallel execution, debate patterns, or ensemble approaches").
- **Stagnation oscillation** — Naively switching to "explore mode" when score plateaus, then back to "exploit mode" on any improvement, creates oscillation. Better: use a sliding window of N iterations. If no improvement in the window AND recent proposals are structurally similar (low diff diversity), then signal exploration. Don't binary-switch — inject graduated signals.
- **Cold-start pipelines that don't use primitives** — A generated pipeline that hardcodes `import openai` instead of using `primitives.llm.complete()` breaks instrumentation (R003). Cold-start generation must include explicit examples of correct primitive usage in the prompt.
- **Archive summary staleness** — Regenerating summaries on every iteration is expensive (LLM call). But caching summaries for too long means the meta-agent misses recent results. Sweet spot: regenerate summary every N iterations (e.g., 10) or when the archive grows past the last summary's coverage.
- **Parameter optimization without topology lock** — If the meta-agent is told "tune parameters" but also changes the topology, the parameter search signal gets muddied. The prompt should distinguish: "the current topology is good — focus on prompt wording, temperature, chunk sizes" vs "the topology may be a local optimum — consider structural changes."

## Open Risks

- **Archive compression quality is untestable in unit tests** — You can verify the format and token count of summaries, but whether they preserve the right signals is an empirical question that only shows up over 50+ real iterations. Mitigation: build the summarizer with explicit section structure (top-K, failure clusters, unexplored regions, trend lines) so the format is auditable even if content quality varies.
- **Structural search may produce pipelines that compile but don't work** — A pipeline that introduces a debate pattern between two agents will compile fine but may loop forever or produce garbage if the debate protocol isn't correctly implemented. The existing per-example timeout (R022) is the safety net, but "compiles and runs within timeout but produces 0.0 score" wastes iterations. No clear mitigation beyond good prompting with examples.
- **LLM cost of archive compression** — Each summarization call uses tokens. At 50 iterations with summaries every 10, that's 5 extra LLM calls. This eats into the user's budget. Need to track compression cost in the same budget system (MetricsCollector).
- **Cold-start quality variance** — The first generated pipeline may be terrible (score 0.0) or may not even use the right primitives. Multiple cold-start attempts before starting optimization? Or just let the loop handle it (first pipeline is always kept per D024, meta-agent improves from there)?

## Candidate Requirements

These surfaced during research. They should be discussed during planning, not auto-adopted:

- **CR-01: Archive summary token budget** — Summaries should have a configurable max token count (default ~3000 tokens) to guarantee they fit alongside the prompt. Currently no token counting exists — would need a heuristic (chars/4) or tiktoken as optional dependency.
- **CR-02: Mutation type tagging** — Archive entries could tag whether a mutation was structural or parametric, enabling richer analysis. Currently rationale is free text. Would require adding a `mutation_type` field to `ArchiveEntry`.
- **CR-03: Component vocabulary registry** — A structured list of available primitives and architectural patterns that gets injected into the meta-agent prompt. Currently the prompt just says "You are an expert Python developer" — it doesn't tell the meta-agent what components exist.
- **CR-04: Compression cost tracking** — Archive compression LLM calls should be tracked in `total_cost_usd` and visible in `autoagent status`. Currently only proposal and evaluation costs are tracked.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| DSPy | `davila7/claude-code-templates@dspy` (195 installs) | available — but project explicitly avoids DSPy dependency |
| Architecture search | none found | no relevant skills |
| Prompt optimization | none found | no relevant skills |

## Sources

- ADAS (Automated Design of Agentic Systems, Hu et al. 2024) — Meta-agent programs new agents in free-form code based on archive of prior discoveries. Key insight: free-form code generation outperforms hand-crafted search operators. Archive includes all prior attempts (kept and discarded) with performance metrics. (source: referenced in project context, author's prior knowledge)
- DSPy MIPROv2 (Opsahl-Ong et al. 2024) — Prompt optimization via instruction generation + few-shot example selection. Uses a "teacher" model to generate candidate instructions, then Bayesian optimization (TPE) to select best combination. Key insight: separating instruction optimization from example selection enables efficient search. (source: referenced in project context, author's prior knowledge)
- Optuna (Akiba et al. 2019) — Bayesian hyperparameter optimization with TPE (Tree-structured Parzen Estimator). Efficient for low-dimensional continuous/categorical spaces. Would be relevant for temperature, top_k, chunk_size tuning but adds a dependency. (source: referenced in project context, author's prior knowledge)
- autoresearch pattern — "If you run out of ideas, think harder — read papers, try combining previous near-misses, try more radical architectural changes." Key insight for stagnation handling: graduated escalation, not binary mode switching. (source: project context documents)
