# S03: Strategy Selection & Parameter Optimization — Research

**Date:** 2026-03-14

## Summary

S03 adds three capabilities to the meta-agent: (1) stagnation detection via sliding-window analysis of recent archive entries, (2) graduated strategy signals injected into the prompt that balance structural exploration vs parameter tuning, and (3) mutation type tagging on `ArchiveEntry` for richer analysis. All three are prompt-level changes — the loop orchestration, evaluation, and archive persistence layers need minimal modification.

The core insight from studying the codebase: **S03 is almost entirely prompt engineering + one dataclass field + one analysis function.** The `_build_prompt()` method already accepts `archive_summary` and composes sections cleanly. Strategy signals are a new section alongside the existing ones. Stagnation detection is a pure function that reads recent entries and returns signal text. Mutation type tagging is one optional field on `ArchiveEntry` with backward-compatible deserialization.

The main risk is calibrating stagnation thresholds — too sensitive causes oscillation, too insensitive misses plateaus. The approach per D031 is graduated signals (not binary switching), which makes calibration less critical since the meta-agent interprets hints, not commands.

## Recommendation

**Three implementation units:**

1. **Stagnation detector** — A pure function (or small class) in a new module `src/autoagent/strategy.py` that takes a list of recent `ArchiveEntry` objects and returns structured strategy signals. Analyzes: plateau length (consecutive iterations without score improvement), score variance (low variance = stuck), structural diversity (how different recent diffs are from each other). Returns a strategy guidance string, not a mode enum — per D005/D032, the meta-agent decides freely.

2. **Mutation type tagging** — Add optional `mutation_type: str | None = None` field to `ArchiveEntry`. The meta-agent's rationale already contains implicit mutation type info, but explicit tagging enables the stagnation detector to distinguish "tried 5 parameter tweaks" from "tried 5 structural changes." The tag is set by the loop after proposal, based on heuristic diff analysis (or extracted from the LLM response). Backward-compatible: existing JSON without the field deserializes fine via `.get()`.

3. **Prompt integration** — Add strategy signals as a `## Strategy Guidance` section in `_build_prompt()`, after Archive Summary / history sections. Add `strategy_signals: str = ""` parameter to `_build_prompt()` and `propose()`, following the same pattern as `archive_summary`. Also add a parameter optimization prompt section that encourages parameter-focused mutations when appropriate.

**Module placement:** New `strategy.py` module for the detector logic. Keeps it testable in isolation. The loop calls it before `propose()` and passes the result through. This follows the same pattern as `summarizer.py` — standalone module consumed by the loop.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Diff computation | `difflib.unified_diff` (used in `archive.py` L176-181) | Already computing diffs — use diff size/content for structural diversity analysis |
| Archive querying | `Archive.query()` and `Archive.recent()` | `recent(N)` gives sliding window; `query(decision="keep", sort_by="primary_score")` gives top-K for trend analysis |
| Prompt section composition | `_build_prompt()` sections pattern (list of strings joined by `\n\n`) | New strategy section follows same pattern — append to sections list |
| Cost delta tracking | MetricsCollector delta pattern (snapshot before/after) | Stagnation detection is pure computation, no LLM calls — no cost tracking needed |
| Result dataclass pattern | `SummaryResult`, `ProposalResult` (frozen dataclass with cost_usd) | Strategy signals are a plain string — no need for a result dataclass since there's no LLM cost |

## Existing Code and Patterns

- `src/autoagent/archive.py` — `ArchiveEntry` (frozen dataclass, L84-98) is the extension point for `mutation_type`. Field must have default `None` for backward compat. `from_dict()` (L109-119) uses positional construction — must add `.get("mutation_type")` for the new field. `Archive.recent(n)` (L275-278) returns N most recent entries sorted by iteration_id descending — ideal for sliding window analysis.

- `src/autoagent/meta_agent.py` — `_build_prompt()` (L224-299) is the primary extension point. Currently builds sections: system instructions → goal → component vocabulary → benchmark → current pipeline → history (summary or raw). Strategy signals go after history. `propose()` (L353-426) accepts kwargs and forwards to `_build_prompt()` — add `strategy_signals` param following `archive_summary` pattern.

- `src/autoagent/loop.py` — `OptimizationLoop.run()` (L117-367) is the integration point. Strategy detection runs after archive context gathering (L216-269) and before `propose()` (L272-277). The stagnation detector receives recent entries and returns a signal string that gets passed to `propose(strategy_signals=...)`.

- `src/autoagent/summarizer.py` — `ArchiveSummarizer` is a peer module, not consumed by S03. But it establishes the pattern: standalone module with a class, consumed by the loop, with its own test file. `strategy.py` follows the same structure.

- `tests/test_meta_agent.py` — `_make_entry()` helper (L35-56) creates minimal `ArchiveEntry` objects. Adding `mutation_type` with a default means this helper works unchanged. New tests can pass `mutation_type="structural"` explicitly.

## Constraints

- **ArchiveEntry is frozen** — Can't add mutation_type post-construction. Must be a constructor parameter with default. Since it's frozen via `@dataclass(frozen=True)`, no setter possible.

- **Archive is append-only (D003)** — Existing JSON files on disk won't have `mutation_type`. `from_dict()` must use `.get("mutation_type")` with default `None`. Never rewrite existing entries.

- **Autonomous strategy decisions (D005)** — Strategy signals are hints, not commands. The prompt says "consider" not "you must." The meta-agent reads signals and decides freely.

- **Graduated signals, not binary switching (D031)** — No "explore mode" / "exploit mode" toggle. Graduated language: "scores plateaued for N iterations — consider structural changes" vs "recent structural improvement — consider tuning parameters within this topology."

- **Strategy via prompt signals, not phases (D032)** — No `strategy_mode` field in state. No phase switching logic. Just prompt text that varies based on archive statistics.

- **Zero runtime dependencies** — Stagnation detection must use stdlib only. Diff similarity could use `difflib.SequenceMatcher.ratio()` for structural diversity — it's stdlib.

- **Context window budget** — Strategy signals section should be compact (~200-500 chars). The prompt already includes: system instructions (~700 chars), goal (variable), component vocabulary (~3500 chars), benchmark (variable), current source (variable), archive summary (~12K chars max). Total prompt budget is tight — strategy signals must be concise.

## Common Pitfalls

- **Oscillation between explore/exploit** — Binary mode switching ("plateau detected → explore!" → "improvement! → exploit!" → "plateau → explore!") produces thrashing. Mitigation: graduated signals with sliding window. Don't react to single-iteration changes. Use window of 5-10 iterations.

- **Diff diversity as structural metric** — Using raw diff size to measure "structural diversity" is fragile — a 200-line diff could be a one-line change repeated across many functions, or a genuine topology change. Better: check whether the diff touches the `run()` function's control flow (function calls, conditionals, loops) vs just string constants/parameters. A simple heuristic: diffs containing new function definitions, new `primitives.` calls, or changed control flow keywords are structural; diffs that only change string literals, numbers, or variable names are parametric.

- **Mutation type classification accuracy** — LLM-extracted mutation type from rationale could be wrong. Heuristic diff analysis (does the diff add/remove function calls, change control flow?) is more reliable as primary signal, with rationale as secondary. Don't over-engineer — a wrong classification just slightly weakens the stagnation signal.

- **Over-engineering the detector** — This is a prompt hint generator, not a Bayesian optimizer. A simple sliding-window with 3 metrics (plateau length, score variance, diff diversity) is sufficient. Don't build a state machine.

- **Testing stagnation with real LLM calls** — All stagnation detection tests should use synthetic ArchiveEntry data, not LLM-generated entries. The detector is a pure function — test it as one.

## Open Risks

- **Stagnation threshold calibration** — What window size (5? 10? 15?) and what plateau length triggers exploration signals? These are empirical. Start with window=10, plateau_threshold=5, and make them configurable. The graduated signal approach reduces sensitivity to exact thresholds.

- **Mutation type heuristic accuracy** — Classifying mutations as structural vs parametric from diffs is heuristic. A prompt change could be "structural" in impact (completely different approach described in the prompt) but "parametric" in diff terms (one string changed). Accept this limitation — it's a signal, not ground truth.

- **Prompt length growth** — Adding strategy signals on top of component vocabulary and archive summary could push the prompt past context window limits for smaller models. The strategy section must stay compact. Monitor total prompt length in tests.

- **Strategy signals being ignored** — The meta-agent might ignore graduated hints. This is acceptable per D005 — the system provides signals, not commands. If signals are consistently ignored, stronger language can be tested in future iterations.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Stagnation detection / optimization | none found | no relevant skills |
| Prompt optimization | `eddiebe147/claude-settings@llm-prompt-optimizer` (51 installs) | tangentially relevant but not applicable — this is about optimizing Claude settings, not about building a stagnation detector |

## Sources

- ADAS (Hu et al. 2024) — Archive-driven search with free-form code generation. Key insight applied: the meta-agent reads the full archive and decides exploration vs exploitation autonomously. No explicit mode switching. (source: project context, M002-RESEARCH.md)
- autoresearch pattern — "If you run out of ideas, think harder — read papers, try combining previous near-misses, try more radical architectural changes." Graduated escalation, not binary mode switching. (source: project context)
- D005, D031, D032 — Decision constraints on strategy implementation: autonomous decisions, graduated signals, prompt-based signals. (source: DECISIONS.md)
