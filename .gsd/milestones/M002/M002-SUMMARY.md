---
id: M002
provides:
  - ArchiveSummarizer with structured LLM-generated summaries (~3K tokens) replacing raw entries past threshold
  - Component vocabulary with 6 architectural patterns (RAG, CAG, Debate, Reflexion, Ensemble, Reranking) and primitive signatures
  - Graduated stagnation detection with sliding-window archive analysis and strategy signals
  - Mutation type classification (structural vs parametric) on every archive entry
  - Cold-start pipeline generation from goal + benchmark + vocabulary via LLM
  - Benchmark.describe() for compact benchmark descriptions
key_decisions:
  - D028: Intelligence through prompting, not frameworks — no DSPy/Optuna dependencies
  - D029: Free-form code generation for structural mutations, not AST manipulation
  - D030: Archive compression via LLM summarization with structured sections
  - D031: Graduated stagnation signals, not binary mode switching
  - D032: Strategy selection via prompt signals, not explicit phases
  - D035: Vocabulary built from _PATTERNS list of dicts for easy extension
  - D039: Cold-start detection via exact string match against STARTER_PIPELINE
  - D040: Separate _build_cold_start_prompt() instead of reusing _build_prompt()
patterns_established:
  - MetricsCollector delta pattern for tracking incremental LLM cost
  - Structured result dataclasses (SummaryResult, ProposalResult) for operations with side costs
  - Exception-safe fallback in loop — try/except with logger.warning and graceful degradation
  - Static prompt artifacts built from data structures for easy extension (_PATTERNS list)
  - Pure-function strategy analysis — no I/O, no LLM calls, fully testable with synthetic data
  - Section-based prompt construction — Goal, Vocabulary, Benchmark, Strategy Guidance, Archive sections
observability_surfaces:
  - SummaryResult.cost_usd and entry_count — compression cost per call
  - build_component_vocabulary() — pure function callable in REPL to inspect vocabulary output
  - analyze_strategy() and classify_mutation() — pure functions callable in REPL with synthetic data
  - Logger autoagent.loop at INFO — strategy signal summary and summary regeneration per iteration
  - Logger autoagent.loop at WARNING — summarizer and strategy detector failures with exc_info
  - stdout "Cold-start:" prefix for cold-start behavior tracing
  - Benchmark.describe() output inspectable as plain string
requirement_outcomes:
  - id: R016
    from_status: active
    to_status: validated
    proof: ArchiveSummarizer produces structured summaries (Top-K, Failure Clusters, Unexplored Regions, Score Trends) from 50+ entries within ~3K token budget. Loop switches to summaries past threshold. Cost tracked in budget. Graceful fallback. 25 tests (17 unit + 8 integration).
  - id: R015
    from_status: active
    to_status: validated
    proof: Benchmark.describe() + MetaAgent.generate_initial() + cmd_run() cold-start detection with retry + fallback. 17 tests (6 benchmark, 7 generation, 4 CLI). Generates valid pipeline from goal + benchmark + vocabulary.
  - id: R011
    from_status: active
    to_status: active
    proof: Component vocabulary and structural mutation guidance injected into prompt. Prompt capability proven (7 tests). Full end-to-end proof of topology-changing mutations improving metrics requires real LLM runs — not validated at unit test level.
  - id: R012
    from_status: active
    to_status: active
    proof: Parameter-only mutations are a distinct mode via strategy signals. Stagnation detector guides toward parameter tuning when topology is strong. Mechanism tested (26 strategy tests). Full validation requires real optimization runs.
  - id: R013
    from_status: active
    to_status: active
    proof: Meta-agent reads archive statistics and autonomously decides mutation type via graduated prompt signals. Mechanism implemented and tested. Full validation requires real optimization runs.
  - id: R024
    from_status: active
    to_status: active
    proof: Stagnation detection with graduated signals balances exploration/exploitation. Strategy visible in prompt signals. Mechanism tested. Full validation requires real optimization runs.
duration: 4 slices across ~8 context windows
verification_result: passed
completed_at: 2026-03-14
---

# M002: Search Intelligence

**Full search intelligence stack: archive compression at scale, component vocabulary with 6 architectural patterns, graduated stagnation detection with explore/exploit signals, mutation type tracking, and cold-start pipeline generation from scratch — all wired into the optimization loop with 267 tests passing.**

## What Happened

Four slices built the search intelligence stack bottom-up:

**S01 (Archive Compression)** built `ArchiveSummarizer` — takes 50+ archive entries, constructs a prompt requesting four structured sections (Top-K Results, Failure Clusters, Unexplored Regions, Score Trends), returns a `SummaryResult` with text, cost, and entry count. Wired into `OptimizationLoop` with threshold-based switching (default: 20 entries), cached regeneration every N iterations, cost tracking against budget, and graceful fallback to raw entries on failure.

**S02 (Structural Search)** added `build_component_vocabulary()` — a data-driven function generating ~875 tokens of structured text covering primitive signatures (`llm.complete()`, `retriever.retrieve()`), 6 architectural pattern skeletons (RAG, CAG, Debate, Reflexion, Ensemble, Reranking), and anti-pattern guidance. Injected into `_build_prompt()` as a permanent section. System instructions updated with structural mutation guidance.

**S03 (Strategy Selection)** built `strategy.py` with two pure functions: `classify_mutation()` (regex-based structural/parametric detection) and `analyze_strategy()` (sliding-window analysis computing plateau length, score variance, structural diversity ratio). Returns graduated signals — from empty (improving) through parameter tuning suggestions to structural exploration guidance. Added `mutation_type` field to `ArchiveEntry`. Wired into the loop: strategy analysis before `propose()`, classification after evaluation.

**S04 (Cold-Start)** added `Benchmark.describe()` for compact benchmark descriptions and `MetaAgent.generate_initial()` for LLM-based pipeline generation using a dedicated cold-start prompt with goal, vocabulary, benchmark description, and example pipeline. `cmd_run()` detects starter templates and triggers cold-start with one retry and fallback to starter template.

All four slices connect cleanly: vocabulary feeds into both iteration and cold-start prompts, archive summaries replace raw entries at scale, strategy signals inject graduated guidance, and cold-start exercises the full stack from scratch.

## Cross-Slice Verification

**Success Criterion: Cold-start generates pipeline and improves over 10+ iterations**
- `MetaAgent.generate_initial()` generates valid pipelines from goal + benchmark + vocabulary (7 tests in `test_meta_agent.py`). `cmd_run()` detects starter template and triggers cold-start with retry + fallback (4 tests in `test_cli.py`). Generated pipelines pass `_validate_source()` (compile + exec + callable run()). The mechanism is proven at unit/integration level. Real 10+ iteration improvement requires live LLM runs — the contract tests prove the pipeline is valid and enters the optimization loop.

**Success Criterion: Structural search proposes topology changes**
- Component vocabulary with 6 architectural patterns injected into every prompt (7 tests). System instructions include structural mutation guidance. Skeletons verified to use primitives interface exclusively. The meta-agent has the vocabulary and guidance to propose topology changes — actual topology-changing mutations depend on LLM quality during real runs.

**Success Criterion: Archive at 50+ iterations produces coherent summaries (~3K tokens)**
- `test_summarize_50_plus_entries` proves summarizer handles 50+ entries. Summary character budget tested (under 12K chars ≈ ~3K tokens). Structured sections (Top-K, Failure Clusters, Unexplored Regions, Score Trends) specified in prompt. Loop switches to summaries past threshold (8 integration tests).

**Success Criterion: Exploration/exploitation strategy visible in archive rationale**
- `analyze_strategy()` returns graduated signals with embedded diagnostic numbers (plateau length, variance, structural ratio). Signals injected into `## Strategy Guidance` prompt section. 26 strategy tests cover all paths: improving (no signal), short plateau (no signal), plateau with all-parametric (suggests structural), plateau with all-structural (suggests parametric), extended plateau (stronger signal). `mutation_type` field on `ArchiveEntry` tracks what type of mutation each iteration performed.

**Success Criterion: Parameter optimization as distinct mutation mode**
- `classify_mutation()` distinguishes structural vs parametric changes. Strategy signals guide toward parameter tuning when topology is strong ("recent improvement — consider tuning parameters"). Parameter-only mutations are a natural outcome of the graduated signal system.

**Full regression: 267 tests passing** (all M001 + M002 tests, zero failures).

## Requirement Changes

- R016 (Archive Compression): active → validated — ArchiveSummarizer with structured summaries from 50+ entries, ~3K token budget, threshold switching, cost tracking, graceful fallback. 25 tests.
- R015 (Cold-Start Pipeline Generation): active → validated — Benchmark.describe() + generate_initial() + cmd_run() cold-start detection with retry + fallback. 17 tests.
- R011 (Structural Search): remains active — component vocabulary and prompt guidance implemented and tested. End-to-end topology mutation proof deferred to real runs.
- R012 (Parameter Optimization): remains active — parameter-only mutation mode implemented via strategy signals. End-to-end proof deferred.
- R013 (Autonomous Search Strategy): remains active — graduated prompt signals implemented and tested. End-to-end autonomy proof deferred.
- R024 (Exploration/Exploitation Balance): remains active — stagnation detection and graduated signals implemented and tested. End-to-end balance proof deferred.

## Forward Intelligence

### What the next milestone should know
- `_build_prompt()` now has 5 sections: Goal, Component Vocabulary, Benchmark, Strategy Guidance (conditional), Archive (summary or raw). Adding new sections (e.g., TLA+ verification results, leakage check results) should follow the same pattern.
- `propose()` accepts `archive_summary: str = ""` and `strategy_signals: str = ""` — new parameters are additive.
- `ArchiveEntry` has `mutation_type: str | None` — backward-compatible. M003 could add more fields following the same optional-field pattern.
- `MockLLM.last_prompt` captures the full prompt text — useful for testing prompt content in M003.
- Cold-start prompt is in `_build_cold_start_prompt()`, separate from iteration prompt. If prompt structure changes, both need updating.

### What's fragile
- Character-count heuristic for token budget (~4 chars/token) — if M003 adds significant prompt sections (TLA+ specs, leakage results), the meta-agent prompt could exceed context window. Monitor total prompt size.
- Cold-start detection relies on exact string match against `STARTER_PIPELINE` — if the starter template changes, detection must be updated in tandem.
- Pattern skeletons in vocabulary are illustrative, not validated as runnable — if primitive APIs change, skeletons may become invalid.
- Plateau detection depends on entries being newest-first from `archive.recent()` — if sort order changes, analysis breaks.

### Authoritative diagnostics
- `pytest tests/ -v` (267 tests) — full regression suite, all M001+M002 features
- `build_component_vocabulary()`, `analyze_strategy()`, `classify_mutation()` — all pure functions callable in REPL for inspection
- Logger `autoagent.loop` at WARNING — surfaces summarizer and strategy detector failures
- Grep stdout for `Cold-start:` to trace cold-start behavior

### What assumptions changed
- Originally considered DSPy/Optuna integration for parameter optimization — decided against (D028). Intelligence through prompting proved sufficient and avoids heavy dependencies.
- Originally planned return/yield as structural indicators in classify_mutation() — removed because changing a return value is parametric (D038).
- DSPy-style parameter tuning reinterpreted as prompt-guided parameter-only mutations rather than a separate optimization framework.

## Files Created/Modified

- `src/autoagent/summarizer.py` — ArchiveSummarizer class and SummaryResult dataclass
- `src/autoagent/strategy.py` — classify_mutation() and analyze_strategy() pure functions
- `src/autoagent/meta_agent.py` — build_component_vocabulary(), _build_cold_start_prompt(), generate_initial(), archive_summary/strategy_signals parameters
- `src/autoagent/loop.py` — summarizer integration, strategy detector wiring, mutation_type classification
- `src/autoagent/archive.py` — mutation_type field on ArchiveEntry
- `src/autoagent/benchmark.py` — describe() method
- `src/autoagent/cli.py` — cold-start detection and generation in cmd_run()
- `src/autoagent/primitives.py` — MockLLM.last_prompt tracking
- `tests/test_summarizer.py` — 17 tests for summarizer contract
- `tests/test_loop_summarizer.py` — 8 integration tests for loop summarizer wiring
- `tests/test_strategy.py` — 26 tests for mutation classification and stagnation detection
- `tests/test_loop_strategy.py` — 5 integration tests for loop strategy wiring
- `tests/test_meta_agent.py` — 13 new tests (vocabulary, strategy signals, cold-start generation)
- `tests/test_benchmark.py` — 6 tests for Benchmark.describe()
- `tests/test_cli.py` — 4 tests for cold-start CLI integration
- `tests/test_loop.py` — updated mock signatures for new parameters
