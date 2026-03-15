# S03: Data Leakage Detection

**Goal:** Every optimization iteration checks for train/test contamination before evaluation — exact overlap blocks, fuzzy overlap warns.
**Demo:** Tests prove: (1) a pipeline embedding benchmark examples is blocked before evaluation, (2) a pipeline with high n-gram overlap generates warnings but proceeds, (3) a clean pipeline passes without issues, (4) the gate is wired into the loop and leakage results appear in archive entries.

## Must-Haves

- `LeakageResult` frozen dataclass with `blocked: bool`, `exact_matches: int`, `fuzzy_warnings: list[str]`, `cost_usd: float`
- `LeakageChecker` class with `check(benchmark, pipeline_source) -> LeakageResult`
- Exact-match detection: AST string literal extraction from pipeline source, match against serialized benchmark examples — blocks iteration
- Fuzzy n-gram detection: word-level n-grams (n=3,4), configurable overlap threshold (default 0.3) — warns only, never blocks (D046)
- Short example skip: exact-match ignores examples with input/expected shorter than 10 chars
- `ArchiveEntry` gains optional `leakage_check: dict | None` field (backward-compatible)
- `Archive.add()` gains `leakage_check` parameter
- `OptimizationLoop.__init__()` gains `leakage_checker` parameter; gate runs after TLA+ verification, before evaluation
- Blocked iteration → discard with rationale, restore pipeline, continue (same pattern as TLA+ gate)
- `LeakageResult.cost_usd` tracked in loop's `total_cost` (0.0 for now — forward-compatible)
- Self-contained module: `leakage.py` imports nothing from `loop.py` or `archive.py`
- Zero external dependencies — stdlib only (`hashlib`, `ast`, `json`, `re`)

## Proof Level

- This slice proves: contract + integration
- Real runtime required: no (MockLLM + synthetic benchmarks)
- Human/UAT required: no

## Verification

- `python3 -m pytest tests/test_leakage.py -v` — unit tests for `LeakageChecker` and `LeakageResult` (exact match blocking, fuzzy warnings, clean pass, short example skip, non-string data, AST parse failure fallback)
- `python3 -m pytest tests/test_loop_leakage.py -v` — integration tests for leakage gate in `OptimizationLoop` (blocked iteration discarded, warning iteration proceeds, no checker = gate skipped, archive entries contain leakage_check)
- `python3 -m pytest tests/ -v` — all existing tests pass (zero regressions)

## Integration Closure

- Upstream surfaces consumed: `benchmark.py` `Benchmark`/`BenchmarkExample`, `loop.py` `OptimizationLoop`, `archive.py` `ArchiveEntry`/`Archive`
- New wiring introduced in this slice: `leakage_checker` parameter on `OptimizationLoop`, leakage gate in loop body, `leakage_check` field on `ArchiveEntry`
- What remains before the milestone is truly usable end-to-end: S04 (sandbox isolation + final assembly with all four gates active)

## Tasks

- [x] **T01: Implement LeakageChecker module with unit tests** `est:1h`
  - Why: Core detection logic — must exist before loop integration
  - Files: `src/autoagent/leakage.py`, `tests/test_leakage.py`
  - Do: Create `leakage.py` with `LeakageResult` frozen dataclass and `LeakageChecker` class. Exact-match: use `ast.parse()` to extract all string literals from pipeline source, compare against `json.dumps(example.input, sort_keys=True)` and `json.dumps(example.expected, sort_keys=True)` plus `str()` representations. Skip examples where both input and expected string representations are shorter than 10 chars. Fuzzy: word-level tokenization (split on `\W+`), extract (3,4)-grams from benchmark examples, compute Jaccard overlap with pipeline source n-grams, warn if overlap > threshold (default 0.3). `cost_usd` always 0.0 for now. Write comprehensive unit tests covering: exact match found → blocked, no match → pass, fuzzy overlap → warnings but not blocked, short examples skipped, non-string data (dicts/lists) serialized correctly, AST parse failure → fallback to regex string extraction, empty benchmark → pass.
  - Verify: `python3 -m pytest tests/test_leakage.py -v`
  - Done when: All unit tests pass, LeakageChecker correctly blocks exact matches and warns on fuzzy overlap

- [x] **T02: Wire leakage gate into loop and archive** `est:45m`
  - Why: Detection without enforcement is useless — gate must block contaminated iterations in the loop
  - Files: `src/autoagent/archive.py`, `src/autoagent/loop.py`, `tests/test_loop_leakage.py`
  - Do: Add `leakage_check: dict[str, Any] | None = None` field to `ArchiveEntry`, update `from_dict()` with `.get()`. Add `leakage_check` parameter to `Archive.add()`, pass through to `ArchiveEntry`. Add `leakage_checker` parameter to `OptimizationLoop.__init__()`. Insert leakage gate after TLA+ verification gate (~L396), before evaluation: call `leakage_checker.check(self.benchmark, proposal.proposed_source)`, accumulate `cost_usd`, if `blocked` → discard with rationale + archive + restore + continue, else log warnings if any. Pass `leakage_check` dict to `archive.add()` for both blocked and evaluated iterations. Write integration tests following `test_loop_verification.py` pattern: mock LeakageChecker, test blocked iteration is discarded, test warning iteration proceeds to evaluation, test no checker = gate skipped, verify archive entries contain `leakage_check` data.
  - Verify: `python3 -m pytest tests/test_loop_leakage.py tests/test_leakage.py -v` and `python3 -m pytest tests/ -v` (full suite, zero regressions)
  - Done when: Leakage gate active in loop, archive entries include leakage results, all tests pass including existing 267

## Observability / Diagnostics

- **Logging:** `LeakageChecker.check()` logs at INFO level: number of exact matches found, number of fuzzy warnings, and whether the result is blocked. Logs at DEBUG level: individual matched literals and per-example Jaccard scores.
- **Inspection surface:** `LeakageResult` is a frozen dataclass — all fields are inspectable. Serialized as a dict in `ArchiveEntry.leakage_check` for post-run analysis.
- **Failure visibility:** If AST parsing fails, logs a WARNING with the `SyntaxError` message and notes the fallback to regex extraction. This makes detection-mode degradation visible without manual debugging.
- **Redaction:** No secrets or benchmark answers are logged at INFO. DEBUG-level logs may include matched literal strings — acceptable since benchmark data is not secret, but keep format terse.

## Files Likely Touched

- `src/autoagent/leakage.py` (new)
- `src/autoagent/archive.py`
- `src/autoagent/loop.py`
- `tests/test_leakage.py` (new)
- `tests/test_loop_leakage.py` (new)
