# S02: Structural Search & Component Vocabulary — Research

**Date:** 2026-03-14

## Summary

S02's job is enriching the meta-agent prompt so it proposes topology-changing mutations — not just parameter tweaks. The current `_build_prompt()` in `meta_agent.py` tells the LLM "You are an expert Python developer optimizing a data pipeline" but gives it zero information about what components exist, what architectural patterns are possible, or how to use the primitives correctly. The meta-agent is flying blind on structure.

The work is almost entirely prompt engineering with a structured vocabulary artifact. The existing `_build_prompt()` already accepts additive sections (archive_summary was added in S01 without touching the core). S02 adds two new sections: a **component vocabulary** (available primitives + architectural patterns) and **structural mutation guidance** (examples showing correct primitive usage in different topologies). No new classes, no new modules — this is about injecting richer context into the existing prompt builder.

The key risk is vocabulary bloat: the component vocabulary + pattern examples could easily eat 3-5K tokens. Combined with archive summaries (~3K tokens), current source, goal, and benchmark description, the prompt could exceed context windows. The vocabulary must be compact — structured reference material, not tutorial prose.

## Recommendation

Build the component vocabulary as a plain-text constant (or small builder function) that describes available primitives and architectural patterns in a compact, structured format. Inject it into `_build_prompt()` as a new section between Goal and Current Pipeline. Add structural mutation guidance as part of the system instructions, not as a separate section — keep it concise.

**Approach:**

1. Define the component vocabulary as a module-level constant or function in `meta_agent.py` (or a small `vocabulary.py` module if it gets large). It should list:
   - Available primitives: `primitives.llm.complete()`, `primitives.retriever.retrieve()` — with signatures and usage
   - Architectural patterns: RAG, CAG, debate, reflexion, ensemble, reranking — each with a 2-3 line description and skeleton showing correct primitive usage
   - Anti-patterns: hardcoded `import openai`, missing `primitives` parameter, calling external APIs directly

2. Extend `_build_prompt()` to accept and inject the vocabulary section. The vocabulary should be **always included** (not conditional like archive_summary) since it's static and cheap.

3. Update system instructions to encourage structural mutations explicitly: "Consider changing the pipeline topology — not just tuning parameters."

4. Add pattern examples showing correct primitive usage in different topologies (RAG pipeline, multi-agent debate, ensemble with reranking). These serve as few-shot examples for the LLM to generate valid structural mutations.

**What NOT to do:**

- Don't build a dynamic vocabulary that introspects `primitives.py` at runtime — the vocabulary is a prompt artifact, not a code artifact. It describes what's *conceptually available*, including patterns that don't have dedicated protocol classes (debate, reflexion, ensemble).
- Don't add new protocol classes (`ToolProtocol`, `AgentProtocol`) — M002-RESEARCH explicitly says these are optional and the meta-agent can generate code using any Python. Keep the protocol surface minimal.
- Don't build a template system or AST manipulation — per D029, mutations are free-form code generation.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Prompt section assembly | `_build_prompt()` sections list + `"\n\n".join()` | Established pattern — just append new sections |
| Pipeline validation | `MetaAgent._validate_source()` | Structural mutations still produce complete pipeline.py — same validation |
| Source extraction | `MetaAgent._extract_source()` via longest fenced block | Unchanged — structural mutations are still Python code blocks |
| Archive context | `archive_summary` parameter (S01) or raw entries | Vocabulary is additive alongside existing archive context |

## Existing Code and Patterns

- `src/autoagent/meta_agent.py` — **Primary extension point.** `_build_prompt()` builds sections as a list and joins them. S01 added `archive_summary` parameter without changing existing logic. S02 adds vocabulary section the same way. The system instructions section is where structural mutation guidance goes. `propose()` needs no changes — vocabulary is injected at the prompt level, not at the call level.
- `src/autoagent/primitives.py` — **Vocabulary source material.** Two protocols: `LLMProtocol` (`.complete(prompt, **kwargs) -> str`) and `RetrieverProtocol` (`.retrieve(query, **kwargs) -> list[str]`). `PrimitivesContext` holds configured instances as `.llm` and `.retriever`. Pipelines receive this as the `primitives` argument to `run()`. The vocabulary must describe this interface accurately.
- `src/autoagent/loop.py` — **No changes needed.** The loop passes context to `meta_agent.propose()` which passes it to `_build_prompt()`. The vocabulary is static — it doesn't depend on loop state. It can be set once when constructing the MetaAgent or injected as a parameter.
- `src/autoagent/summarizer.py` — **No changes needed.** Archive summaries and component vocabulary are independent prompt sections.
- `tests/test_meta_agent.py` — **27 existing tests.** Tests check prompt construction (sections present, entries formatted), extraction (fenced blocks, multiple blocks, no blocks), validation (syntax, missing run, not callable), and propose flow (success, failures, cost tracking). S02 tests follow the same patterns — verify vocabulary section appears in prompt, verify structural mutation guidance in system instructions.

## Constraints

- **Zero runtime dependencies** — vocabulary is a static string, no external libraries needed
- **Single-file mutation constraint (D001)** — structural mutations still produce complete `pipeline.py`. The vocabulary describes patterns, not multi-file architectures.
- **compile()+exec() module loading (D014)** — pattern examples must work in the synthetic namespace. No relative imports, no `__file__` assumptions.
- **Provider-agnostic (D004)** — vocabulary describes `primitives.llm.complete()`, not `openai.ChatCompletion.create()`. Examples must use the primitives interface exclusively.
- **Autonomous strategy decisions (D005)** — vocabulary provides options, not commands. The meta-agent decides freely whether to make structural vs parameter changes. Guidance says "consider" not "you must."
- **Prompt token budget** — vocabulary + patterns must fit in ~2-3K tokens alongside archive summary (~3K), current source (variable), and other sections. S01 forward intelligence warns about character-count heuristic for context window limits. Keep vocabulary compact.
- **No new protocols** — M002-RESEARCH says `ToolProtocol`/`AgentProtocol` are optional. Don't add them. The vocabulary describes patterns using the existing two primitives.

## Common Pitfalls

- **Vocabulary too verbose** — Tutorial-style descriptions with full explanations eat tokens fast. The vocabulary should be reference-style: pattern name, 2-line description, 5-10 line skeleton. Target ~1.5-2K tokens total for the vocabulary section.
- **Pattern examples that don't use primitives** — Examples showing `import openai` or `import anthropic` would teach the LLM the wrong pattern. Every example must use `primitives.llm.complete()` and `primitives.retriever.retrieve()`. This is the #1 correctness constraint.
- **Hardcoded vocabulary that can't grow** — While the vocabulary starts static, it should be structured so adding new patterns is trivial (just add a new entry to the list). A function that builds the vocabulary string from a data structure is slightly better than a raw string constant.
- **Over-prompting structural changes** — If the system instructions push structural changes too hard, the meta-agent will make random topology changes when parameter tuning would be more productive. S03 handles the balance; S02 should provide the capability without forcing it. Guidance: "When the current approach has fundamental limitations, consider architectural changes."
- **Testing vocabulary content vs testing vocabulary injection** — Unit tests should verify the vocabulary section appears in the prompt and contains key elements (primitive names, pattern names). Don't test the exact wording — it'll change. Test structure and presence.

## Open Risks

- **Vocabulary completeness** — The initial vocabulary covers RAG, CAG, debate, reflexion, ensemble, reranking. Are there other patterns the meta-agent should know about? Chain-of-thought, map-reduce, hierarchical agents, tool use? Starting with the 6 patterns from the roadmap and adding more later is safe — the vocabulary is a string, not an API.
- **Prompt length with vocabulary + summary** — At ~2K tokens (vocabulary) + ~3K tokens (archive summary) + ~1K (current source) + ~0.5K (instructions/goal/benchmark), we're at ~6.5K tokens minimum for the prompt. This is fine for large-context models but could be tight if the current source is long. No mitigation needed now — just something to monitor.
- **Quality of structural mutations** — Even with a good vocabulary, the LLM may produce pipelines that compile but don't implement the pattern correctly (e.g., a "debate" pattern that just calls the LLM twice sequentially). The existing validation (compile + run() check) catches syntax issues but not semantic correctness. This is acceptable — the evaluation loop will score bad implementations low and discard them. The system learns from failure.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Prompt engineering | `rmyndharis/antigravity-skills@prompt-engineer` (25 installs) | available — not directly relevant (generic prompt engineering, not architecture search) |
| Architecture search (ADAS) | none found | no relevant skills |
| Meta-agent design | none found | no relevant skills |

No skills worth installing — this work is project-specific prompt construction, not a generic technology integration.

## Sources

- ADAS (Hu et al. 2024) — Meta-agent generates complete agent code with a growing archive of prior attempts. Component vocabulary is injected as prompt context describing available building blocks. Key insight: free-form generation with vocabulary outperforms structured mutation operators. (source: project M002-RESEARCH)
- autoresearch — "try combining previous near-misses, try more radical architectural changes" — the vocabulary gives the meta-agent concrete options for what "more radical" means. (source: project M002-RESEARCH)
- M001 codebase — `MetaAgent._build_prompt()` is the extension point. S01 proved additive prompt sections work without disrupting existing behavior. (source: codebase exploration)
