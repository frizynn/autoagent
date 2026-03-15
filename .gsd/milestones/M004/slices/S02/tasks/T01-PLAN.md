---
estimated_steps: 7
estimated_files: 2
---

# T01: Build BenchmarkGenerator with validation pipeline and tests

**Slice:** S02 — Benchmark Generation
**Milestone:** M004

## Description

Build `BenchmarkGenerator` as a standalone class in `src/autoagent/benchmark_gen.py`. It takes a goal string, optional sample data, and an `LLMProtocol` instance, prompts the LLM to generate evaluation examples as JSON, parses the response (handling markdown fences and prose wrapping), validates via leakage checking and baseline score diversity, and returns a structured `GenerationResult`. All testing uses `SequenceMockLLM` for deterministic responses.

## Steps

1. Create `benchmark_gen.py` with `GenerationResult` and `ValidationResult` frozen dataclasses. `GenerationResult` fields: `examples` (list of dicts), `scoring_function` (str), `validation` (ValidationResult), `cost_usd` (float), `success` (bool), `error` (str | None). `ValidationResult` fields: `leakage_blocked` (bool), `baseline_scores_identical` (bool), `diversity_ratio` (float), `passed` (bool), `details` (str).

2. Implement `BenchmarkGenerator.__init__(llm, goal, sample_data=None)` and `generate(num_examples=10) -> GenerationResult`. Build a section-based prompt (following meta_agent.py pattern) that instructs the LLM to produce a JSON array of `{input, expected, id}` objects where expected differs from input. Include goal and sample data context in the prompt. Default scoring function to `includes`.

3. Implement `_extract_json(response: str) -> list[dict]` — strip markdown fences (` ```json ... ``` ` or ` ``` ... ``` `), try `json.loads()` on the extracted block, fallback to trying `json.loads()` on the full response. Raise `ValueError` on failure.

4. Implement `_validate(examples: list[dict]) -> ValidationResult` — (a) Build a `Benchmark` from the examples and run `LeakageChecker.check()` against `STARTER_PIPELINE` source, (b) check input diversity: `len(set(str(e["input"]) for e in examples)) / len(examples) >= 0.8`, (c) check that examples have required keys (`input`, `expected`), (d) write examples to a temp file and load via `Benchmark.from_file()` to confirm round-trip compatibility.

5. Wire retry logic: if `_extract_json` raises on first attempt, send a follow-up prompt asking the LLM to output valid JSON only, try once more (max 2 total attempts). Track cost from LLM calls if the LLM exposes it.

6. Write `tests/test_benchmark_gen.py` with tests: happy path generation, JSON extraction from fenced blocks, JSON extraction from bare JSON, validation passing, leakage detection (examples containing STARTER_PIPELINE literals), diversity check failure (duplicate inputs), retry on malformed JSON, round-trip through `Benchmark.from_file()`, error result on exhausted retries.

7. Run tests and verify all pass.

## Must-Haves

- [ ] `BenchmarkGenerator` class with `generate()` returning `GenerationResult`
- [ ] JSON extraction handles markdown fences, bare JSON, and prose-wrapped output
- [ ] Validation checks: leakage, diversity, format round-trip
- [ ] Retry on JSON parse failure (max 2 attempts)
- [ ] `GenerationResult` exposes structured validation details for diagnosis
- [ ] Generated examples round-trip through `Benchmark.from_file()`
- [ ] All unit tests pass

## Verification

- `pytest tests/test_benchmark_gen.py -v` — all tests pass
- Import check: `from autoagent.benchmark_gen import BenchmarkGenerator, GenerationResult`

## Observability Impact

- Signals added: `GenerationResult.validation` with leakage_blocked, baseline_scores_identical, diversity_ratio, passed, details
- How a future agent inspects this: read `GenerationResult` fields after `generate()` call — all validation outcomes are structured and inspectable
- Failure state exposed: `GenerationResult.error` string with parse/validation/retry context; `GenerationResult.success = False` on any failure

## Inputs

- `src/autoagent/benchmark.py` — `Benchmark.from_file()` format contract, `BenchmarkExample` dataclass
- `src/autoagent/leakage.py` — `LeakageChecker.check(benchmark, pipeline_source)` API
- `src/autoagent/state.py` — `STARTER_PIPELINE` constant
- `src/autoagent/interview.py` — `SequenceMockLLM` for testing
- S02-RESEARCH.md — architecture recommendation, constraints, pitfalls

## Expected Output

- `src/autoagent/benchmark_gen.py` — new module with `BenchmarkGenerator`, `GenerationResult`, `ValidationResult`
- `tests/test_benchmark_gen.py` — comprehensive unit tests (≥12 tests covering happy path, parsing, validation, retry, errors)
