# M004: Interview & Polish — Research

**Date:** 2026-03-14

## Summary

M004 introduces three new subsystems — interview orchestrator, benchmark generator, and reporting — on top of a mature 4,800-line codebase with zero runtime dependencies, 381 tests, and well-established patterns (section-based prompts, frozen result dataclasses, atomic disk state, compile()+exec() loading). The core challenge isn't mechanical integration — the existing patterns extend cleanly. The challenge is **LLM interaction quality**: the interview must extract a useful optimization spec from vague input, the benchmark generator must produce evaluation data that actually measures what the user cares about, and the report must compress 100+ iterations into a compelling narrative.

The codebase imposes hard constraints: zero runtime dependencies (no `rich`, `inquirer`, or `click`), all LLM calls through `LLMProtocol`, all state in `.autoagent/` via atomic JSON writes, and all benchmarks as JSON arrays of `{input, expected}` objects. These constraints are well-understood and don't fight the design — they just mean the interview uses `input()`/`print()`, not a TUI framework.

**Primary recommendation:** Start with the interview orchestrator (highest risk — must produce a valid optimization spec from vague input), then benchmark generation (second-highest — must create meaningful evaluation data), then reporting (lowest risk — reads existing archive data). The interview should produce a populated `ProjectConfig` plus a `context.md` for the meta-agent. Benchmark generation should be a distinct step that the interview triggers when no benchmark is provided. Reporting reads the archive and produces a markdown file + terminal summary.

## Recommendation

Build the interview as an LLM-driven multi-turn conversation that populates `ProjectConfig` fields, using the same `LLMProtocol` the meta-agent uses. The interview orchestrator generates follow-up questions by analyzing the user's previous answers + any codebase/data files it can discover. Output is a structured spec (extended `ProjectConfig` or new `OptimizationSpec` dataclass) that the existing loop machinery consumes directly.

Benchmark generation should be a separate module callable from both the interview (cold-start) and standalone. It takes a goal description + optional sample data and produces a `Benchmark`-compatible JSON file, then runs the existing `LeakageChecker` against a trivial pipeline to validate no contamination.

Reporting reads `Archive.query()` results and computes: best score trajectory, top-K architectures with diffs, failure clusters, cost breakdown, and recommendations. Output is a markdown file in `.autoagent/report.md` plus a terminal summary via `autoagent report`.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| LLM-driven follow-up questions | `MetaAgent._build_prompt()` section-based pattern | Same pattern works: build interview prompt from sections (user answers, codebase analysis, remaining gaps), call LLM, parse structured response |
| Benchmark validation for leakage | `LeakageChecker.check()` | Already validates pipeline source against benchmark — reuse for generated benchmarks by checking a dummy pipeline |
| Archive querying for reports | `Archive.query(decision=, sort_by=, limit=)` | Full query API exists — reports just need to call it with different parameters |
| Atomic config persistence | `StateManager.write_config()` + `_atomic_write_json()` | Interview results persisted through existing atomic write path |
| Cost tracking | `MetricsCollector` + `LLMProtocol.collector` | Interview and benchmark generation LLM costs tracked the same way as meta-agent costs |
| Dynamic scorer loading | `Benchmark._resolve_scorer()` with compile()+exec() | If benchmark generator creates custom scorers, load them through the same path |
| Cold-start pipeline from spec | `MetaAgent.generate_initial()` | Interview produces the spec that cold-start already consumes |

## Existing Code and Patterns

- `src/autoagent/cli.py` — Entry point. Has `init`/`run`/`status`. Needs `new` (interview) and `report` commands. `build_parser()` uses argparse subparsers — straightforward to extend. `cmd_run()` already handles cold-start detection.
- `src/autoagent/state.py` — `ProjectConfig` dataclass: `goal`, `benchmark` (dict with `dataset_path`/`scoring_function`), `budget_usd`, `pipeline_path`. Interview output maps directly to populating these fields. May need extension for search space constraints, metric definitions, etc.
- `src/autoagent/meta_agent.py` — Section-based prompt construction in `_build_prompt()`. The interview orchestrator should follow this exact pattern: build prompt from sections, call LLM, parse response. `build_component_vocabulary()` is a reusable artifact the interview can show users.
- `src/autoagent/benchmark.py` — `Benchmark.from_file()` loads JSON arrays of `{input, expected, id?}`. `describe()` produces compact text. Benchmark generator must produce this exact format. `_resolve_scorer()` handles built-in and custom scorers.
- `src/autoagent/archive.py` — `ArchiveEntry` has `evaluation_result`, `rationale`, `decision`, `mutation_type`, `pareto_evaluation`, etc. Report reads all this. `Archive.query()` supports filtering and sorting.
- `src/autoagent/loop.py` — 592 lines. `OptimizationLoop.__init__()` takes `benchmark`, `meta_agent`, `primitives_factory`, `budget_usd`, plus safety gate instances. Interview output must produce all these parameters.
- `src/autoagent/evaluation.py` — `EvaluationResult` has `primary_score`, `per_example_results`, `metrics`, `duration_ms`. Report consumes these from archive entries.
- `src/autoagent/leakage.py` — `LeakageChecker.check(benchmark, pipeline_source)` — reusable for validating generated benchmarks.
- `src/autoagent/strategy.py` — `analyze_strategy()` and `classify_mutation()` — pure functions that report could use for trend analysis.
- `src/autoagent/primitives.py` — `LLMProtocol`, `MockLLM`, `MetricsCollector`. Interview orchestrator needs an LLM instance — same protocol.

## Constraints

- **Zero runtime dependencies** — no `rich`, `click`, `inquirer`, `pyyaml`. Interview UX is `input()`/`print()` only. Report output is plain text or markdown written to file.
- **LLMProtocol is the only LLM interface** — interview, benchmark generation, and report summarization all must go through `LLMProtocol.complete()`. No direct API calls.
- **Benchmarks must be JSON arrays of `{input, expected}`** — benchmark generator cannot use exotic formats. Scoring function is either built-in (`exact_match`, `includes`) or a custom `.py` file.
- **All state in `.autoagent/`** — interview spec, generated benchmarks, and reports all persist here via atomic writes.
- **`ProjectConfig` is frozen** — modifications require `dataclasses.replace()`. Adding fields is backward-compatible via `from_dict()` ignoring unknown keys, but old configs won't have new fields.
- **`cmd_run()` already does cold-start** — if interview generates a benchmark and populates config, `cmd_run()` picks it up. Interview doesn't need to invoke the loop directly.
- **MockLLM is the only implemented provider** — interview and benchmark generation will use MockLLM in tests, real LLM in production. Same pattern as meta-agent.

## Common Pitfalls

- **Interview that collects inputs but doesn't challenge them** — "What's your goal?" → user says "make it better" → system proceeds with a meaningless spec. The interview must probe vague answers: "Better in what dimension? Accuracy? Latency? Cost? What does 'better' look like concretely?" This is the GSD-2 pattern — detect gray areas and investigate them.
- **Generated benchmarks that are trivially solvable or unsolvable** — If the generator creates questions a dummy pipeline can score 1.0 on, or that no pipeline can score above 0.0 on, the benchmark is useless. Validation step: run a baseline pipeline against the generated benchmark and verify scores are between 0.1 and 0.9.
- **Report that dumps raw data instead of telling a story** — "Iteration 1: 0.45, Iteration 2: 0.42, ..." is not a report. The report needs to identify phases (exploration, convergence, stagnation), highlight turning points, and make recommendations.
- **Interview → config format mismatch** — If the interview produces fields that `ProjectConfig` doesn't have, or the loop doesn't consume, the interview is wasted work. Define the spec format first, then build the interview to produce it.
- **Benchmark generation without leakage validation** — If the generated benchmark contains data that will trivially appear in pipeline source (e.g., short string literals), the leakage checker will block valid iterations. Generated benchmarks need the same leakage validation as user-provided ones, but before optimization starts.
- **Report as a monolithic string concatenation** — Makes testing impossible. Build report from composable sections (score trajectory, architecture summary, cost breakdown) that can be tested independently.

## Open Risks

- **Interview quality is hard to test mechanically** — Unit tests can verify the interview produces valid config, but can't verify it asked the *right* follow-up questions. This requires real LLM testing or carefully crafted MockLLM response sequences.
- **Benchmark generation domain variance** — "Improve RAG accuracy" needs question-answer pairs. "Minimize latency" needs timing benchmarks. "Improve code generation" needs code-and-test pairs. A single generation strategy may not cover all domains. May need domain-specific strategies or a meta-strategy that picks the right approach.
- **`ProjectConfig` extension scope** — The interview needs to capture search space constraints, metric priorities, provider preferences, and other fields that `ProjectConfig` doesn't currently have. Extending it carefully (backward-compatible, no breaking changes) is essential. Alternative: a separate `OptimizationSpec` file that augments `ProjectConfig`.
- **LLM cost of interview** — A deep multi-turn interview could burn significant tokens before optimization even starts. Need a cost ceiling for the interview itself, or at minimum track and report interview cost.
- **Report markdown rendering** — Terminal markdown rendering varies wildly. The report should be readable as plain text even without a markdown renderer — no complex tables, no nested formatting.

## Candidate Requirements

The following surfaced during research. They are advisory — not automatically in scope.

- **CR-001: Interview cost tracking** — The interview makes LLM calls. These should be tracked and reported, and possibly count against the budget. Currently `ProjectConfig` has `budget_usd` but only `cmd_run` uses it.
- **CR-002: Optimization spec as separate artifact** — `ProjectConfig` may not be the right place for everything the interview captures (search space constraints, metric priorities, domain context). A separate `spec.md` or `spec.json` in `.autoagent/` would keep config clean and give the meta-agent richer context.
- **CR-003: Benchmark quality validation** — After generating a benchmark, run a baseline pipeline against it to verify scores aren't all-0 or all-1. This is more than leakage checking — it's measuring whether the benchmark is discriminating.
- **CR-004: Report delivery as file + terminal** — Context mentions leaning toward generated markdown file + terminal summary. Both are needed: the file for sharing/archiving, the terminal output for quick "what happened?" checks.
- **CR-005: Interview resumption** — If the interview is interrupted (user quits mid-conversation), it should be resumable. Persist interview state incrementally. Low priority but impacts UX for long interviews.

## Requirement Analysis

### Table Stakes (must have, already specified)
- **R007 (Interview)** — The core of M004. Without this, users manually configure everything — defeats the UX promise.
- **R023 (Benchmark Generation)** — Without this, users without existing eval data can't use the system. Critical for cold-start.

### Expected Behaviors (not specified but users will assume)
- Interview should populate all fields needed by `cmd_run()` — goal, benchmark path, scoring function, budget. If any are missing, `cmd_run()` errors.
- Generated benchmarks should be viewable/editable by the user — they're just JSON files.
- Reports should be re-runnable — `autoagent report` on a completed run should always work, not just immediately after.

### Risks of Overbuilding
- **Domain-specific interview strategies** — The interview should be general enough to work across optimization goals. Building domain-specific question trees (one for RAG, one for latency, etc.) would be overbuilding for M004. A single adaptive interview that probes vague areas is sufficient.
- **Rich TUI for interview** — `input()`/`print()` is fine. Investing in terminal formatting beyond basic prompts is unnecessary.

### Missing from Requirements
- No requirement for interview cost tracking (CR-001)
- No requirement for benchmark quality validation beyond leakage (CR-003)
- No requirement for interview resumption (CR-005)
- R019 (fire-and-forget) is already validated but the "morning report" completes the experience — R019 supporting slice M004/S04 aligns

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| CLI interview/wizard | none found | No relevant skills — interview is domain-specific, built on stdlib input()/print() |
| Benchmark generation | `davila7/claude-code-templates@evaluating-llms-harness` | Available (195 installs) — tangentially related but focused on eval harness setup, not generation from vague goals |
| LLM evaluation | `davila7/claude-code-templates@evaluating-code-models` | Available (180 installs) — code model evaluation, not general benchmark generation |

No skills are directly relevant. The interview orchestrator, benchmark generator, and reporter are domain-specific modules best built on existing codebase patterns.

## Sources

- Codebase analysis: `src/autoagent/` (4,799 LOC across 17 modules, 381 tests across 22 files)
- M002 summary: archive compression, component vocabulary, strategy detection, cold-start generation patterns
- M003 summary: safety gate sequence, graceful degradation, archive entry field extension pattern
- GSD-2 interview pattern: deep interrogation that probes gray areas, challenges vagueness, investigates codebase (referenced in M004 context)
- ADAS research: autonomous search, free-form code generation outperforms hand-crafted operators (per D028, D029)
