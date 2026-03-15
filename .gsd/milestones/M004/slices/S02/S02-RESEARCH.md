# S02: Benchmark Generation — Research

**Date:** 2026-03-14

## Summary

S02 builds a `BenchmarkGenerator` that produces valid `{input, expected}` JSON from the interview's goal + optional sample data, validates it for leakage and discriminating power, and writes it to `.autoagent/benchmark.json`. The interview (S01) already leaves `benchmark.dataset_path` empty when the user has no benchmark — this is the trigger. The generator must produce output compatible with `Benchmark.from_file()` (JSON array of `{input, expected, id?}` objects) and pass two validation gates: `LeakageChecker.check()` against a trivial pipeline (existing module, reused directly) and baseline score validation (D056: scores between 0.1–0.9 on `STARTER_PIPELINE`'s echo behavior).

The main challenge is LLM prompt quality: the generator asks the LLM to create realistic evaluation examples from a goal description, which is inherently open-ended. The mechanical parts — JSON writing, leakage checking, baseline validation — all have existing patterns to follow. The `SequenceMockLLM` from S01 makes multi-turn generation testing straightforward.

**Primary recommendation:** Build `BenchmarkGenerator` as a standalone class in `src/autoagent/benchmark_gen.py` that takes a goal string, optional sample data strings, and an `LLMProtocol` instance. It asks the LLM to generate examples as JSON, parses the response, runs leakage + baseline validation, and returns a structured result. Wire it into the interview flow (called from `cmd_new` when no benchmark path is provided) and make it independently callable for testing.

## Recommendation

### Architecture

1. **`BenchmarkGenerator`** class in new `src/autoagent/benchmark_gen.py`:
   - Constructor: `(llm: LLMProtocol, goal: str, sample_data: list[str] | None = None)`
   - Primary method: `generate(num_examples: int = 10) -> GenerationResult`
   - `GenerationResult` frozen dataclass: `examples: list[dict]`, `scoring_function: str`, `validation: ValidationResult`, `cost_usd: float`, `success: bool`, `error: str | None`

2. **Validation pipeline** (called internally by `generate()`):
   - Parse LLM output → extract JSON array of `{input, expected}`
   - Leakage check: build a `Benchmark` from the examples, run `LeakageChecker.check()` against `STARTER_PIPELINE` source
   - Baseline check: write examples to temp file, load via `Benchmark.from_file()`, run `Evaluator.evaluate()` with `STARTER_PIPELINE`, verify 0.1 ≤ primary_score ≤ 0.9

3. **Integration point**: `cmd_new` in `cli.py` — after interview completes, if `result.config.benchmark["dataset_path"]` is empty, call `BenchmarkGenerator.generate()`, write to `.autoagent/benchmark.json`, update config with the path.

### Why this approach

- Standalone class keeps benchmark generation testable independently of the interview
- Reuses `LeakageChecker` and `Evaluator` directly — no reimplementation
- `STARTER_PIPELINE` is already the canonical trivial pipeline — scoring against it validates discriminating power naturally
- `SequenceMockLLM` from S01 handles all testing needs

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Benchmark format validation | `Benchmark.from_file()` | Already validates JSON array of `{input, expected}` — round-trip through it to confirm format |
| Leakage detection | `LeakageChecker.check(benchmark, pipeline_source)` | Exact module, exact API — pass generated benchmark + `STARTER_PIPELINE` source |
| Pipeline evaluation for baseline | `Evaluator.evaluate(pipeline_path, benchmark)` | Full evaluation with timeout, scoring, aggregation — just point it at STARTER_PIPELINE |
| Trivial baseline pipeline | `STARTER_PIPELINE` in `state.py` | Returns `{"echo": input_data}` — if benchmark scores 1.0 against echo, it's trivially solvable |
| Atomic JSON writing | `_atomic_write_json()` in `state.py` | Same pattern for writing benchmark.json to disk |
| LLM response code extraction | `_CODE_BLOCK_RE` in `meta_agent.py` | May need similar fence-stripping for JSON blocks in LLM responses |
| Mock LLM for testing | `SequenceMockLLM` in `interview.py` | Pre-defined response sequences for deterministic generation testing |
| Config update after generation | `dataclasses.replace()` + `StateManager.write_config()` | Update `benchmark.dataset_path` in frozen `ProjectConfig` |

## Existing Code and Patterns

- `src/autoagent/benchmark.py` — `Benchmark.from_file(path, scoring_function)` loads JSON arrays. `BenchmarkExample(input, expected, id)` is the data unit. `_resolve_scorer()` handles built-in names and custom `.py` files. `describe()` produces compact text. Generator output must produce exactly this format.
- `src/autoagent/leakage.py` — `LeakageChecker(fuzzy_threshold=0.3).check(benchmark, pipeline_source)` returns `LeakageResult(blocked, exact_matches, fuzzy_warnings)`. Self-contained — no side effects. Pass `STARTER_PIPELINE` as the pipeline_source for validation.
- `src/autoagent/evaluation.py` — `Evaluator().evaluate(pipeline_path, benchmark, timeout_per_example, primitives_factory)` returns `EvaluationResult(primary_score, ...)`. For baseline validation, write STARTER_PIPELINE to a temp file and evaluate against generated benchmark.
- `src/autoagent/state.py` — `STARTER_PIPELINE` is a module-level string constant that returns `{"echo": input_data}`. `_atomic_write_json()` for safe disk writes. `ProjectConfig.benchmark` is a dict with `dataset_path` and `scoring_function` keys.
- `src/autoagent/interview.py` — `InterviewOrchestrator.generate_config()` sets `benchmark["description"]` from user's answer but leaves `dataset_path` empty. `SequenceMockLLM` cycles through responses. `InterviewResult.config` is the frozen `ProjectConfig`.
- `src/autoagent/cli.py` — `cmd_new()` writes config via `sm.write_config(result.config)`. Benchmark generation should happen here between interview completion and config write, so the generated path can be included in the config. `cmd_run()` checks `dataset_path` and fails if empty — after S02, this path should be populated.
- `src/autoagent/meta_agent.py` — `_CODE_BLOCK_RE` for extracting fenced code blocks from LLM responses. Same pattern needed for extracting JSON from generation responses. Section-based prompt construction in `_build_prompt()` / `_build_cold_start_prompt()` — follow this pattern for the generation prompt.

## Constraints

- **Zero runtime dependencies** — JSON parsing, file I/O, temp files all stdlib. No `jsonschema` or validation libraries.
- **LLM response parsing must be robust** — LLM may wrap JSON in markdown fences, add prose before/after, or produce malformed JSON. Need fence-stripping + fallback parsing.
- **Benchmark examples must not be trivially solvable by echo** — If `expected == input` for all examples, `STARTER_PIPELINE` scores 1.0 and the benchmark is useless. The 0.1–0.9 baseline threshold (D056) catches this.
- **Benchmark examples must not be unsolvable** — All-zero scores mean no optimization signal. The 0.1 lower bound catches this, but only against the echo pipeline. A score of 0.0 against echo is fine if the examples are genuinely non-trivial — the real test is that scores aren't all identical (no discriminating power).
- **`ProjectConfig` is frozen** — `dataclasses.replace()` to update benchmark dict after generation. Config write happens after generation completes.
- **Generated benchmark must be human-readable** — Users should be able to open `benchmark.json` and understand what's being tested. Examples should have meaningful IDs, clear input/expected pairs.
- **Scoring function selection** — Generator must choose an appropriate built-in scorer (`exact_match` or `includes`) based on the goal. For most generated benchmarks, `includes` is safer (partial matching) unless the goal explicitly requires exact matching.

## Common Pitfalls

- **LLM generates examples where `expected` matches `input`** — Echo pipeline would score 1.0, making the benchmark trivially solvable. The baseline validation catches this, but the prompt should explicitly instruct "expected output must differ from input."
- **LLM generates examples that are all identical or near-identical** — No discriminating power. Add a diversity check: unique inputs should be ≥ 80% of total examples.
- **LLM wraps JSON in markdown fences or adds prose** — Must strip ` ```json ... ``` ` fences and extract the JSON array. Regex pattern similar to `_CODE_BLOCK_RE` but for JSON blocks.
- **Baseline validation against STARTER_PIPELINE is too strict** — STARTER_PIPELINE echoes input as `{"echo": input_data}`. If the scorer is `exact_match`, nearly everything scores 0.0 against echo. That's fine — it means the benchmark is non-trivial. The risk is the *upper* bound: if something accidentally scores > 0.9, the benchmark is too easy. A score of 0.0 against echo is actually expected for a good benchmark — reconsider whether the 0.1 lower bound should apply to the echo pipeline or to a smarter baseline.
- **Writing benchmark.json before validation passes** — Generate → validate → write, never write first. If validation fails, report error, don't write partial results.
- **Config benchmark path as relative vs absolute** — `cmd_run()` resolves relative paths against `project_dir`. Generated benchmark should use a relative path like `benchmark.json` (relative to `.autoagent/`), matching how other project files are referenced.

## Open Risks

- **Baseline validation semantics need clarification** — D056 says scores 0.1–0.9 on a "trivial pipeline." But `STARTER_PIPELINE` just echoes — most real benchmarks would score 0.0 against echo with `exact_match` scoring. The 0.1 lower bound makes more sense with `includes` scoring or with a smarter baseline (e.g., a pipeline that calls the LLM). **Resolution approach:** Use `includes` as default scorer for generated benchmarks, and adjust validation to check that scores are *not all identical* (discriminating power) rather than enforcing a specific range against echo. Keep the 0.9 upper bound as a degeneracy check.
- **Scoring function selection** — The generator must pick an appropriate scorer. For text-generation goals, `includes` is usually right. For classification/extraction goals, `exact_match` may be better. The generator can default to `includes` and let the user override.
- **Number of examples** — Too few (< 5) gives noisy scores. Too many (> 50) makes evaluation slow. Default to 10, which is a reasonable balance for cold-start. The user can add more later.
- **LLM may generate invalid JSON despite prompting** — Need retry logic (max 2 attempts) before failing. Each retry costs tokens but is cheaper than producing a broken benchmark.
- **Integration with `cmd_new` flow** — Benchmark generation adds LLM calls after the interview. If the interview already used many tokens, generation adds more. Track cost via `MetricsCollector` on the LLM instance. Not gating, but reportable.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Benchmark generation | `davila7/claude-code-templates@evaluating-code-models` | Available (180 installs) — focused on code model evaluation harness, not generation from vague goals. Not relevant. |
| Performance benchmarking | `manutej/luxor-claude-marketplace@performance-benchmark-specialist` | Available (51 installs) — hardware performance benchmarking, not LLM evaluation data generation. Not relevant. |

No skills are directly relevant. Benchmark generation from optimization goals is domain-specific to autoagent.

## Sources

- Codebase analysis: `src/autoagent/` modules — benchmark.py (212 LOC), leakage.py (250 LOC), evaluation.py (250 LOC), interview.py (321 LOC), state.py (309 LOC), cli.py (347 LOC), meta_agent.py (539 LOC)
- S01 summary: InterviewOrchestrator produces ProjectConfig with empty benchmark.dataset_path when user has no benchmark; SequenceMockLLM available for testing
- D056: Benchmark baseline validation scores 0.1–0.9 on trivial pipeline
- D046: Leakage detection — exact match blocks, fuzzy warns
- Boundary map S02→S03: BenchmarkGenerator class, baseline validation, LeakageChecker integration, generated benchmark at config path
