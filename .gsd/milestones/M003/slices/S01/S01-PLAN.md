# S01: TLA+ Verification Gate

**Goal:** Every proposed pipeline passes through a TLA+ verification gate before evaluation — LLM generates a TLA+ spec, TLC model-checks it, and failures block the proposal from being evaluated.

**Demo:** `autoagent run` generates a TLA+ spec for each proposed pipeline, runs TLC model checker, and rejects proposals that fail verification — proven with mock TLC subprocess and unit tests. When Java/TLC is unavailable, the gate is skipped with a warning.

## Must-Haves

- `TLAVerifier` class with `verify(source: str) -> VerificationResult` method
- `VerificationResult` frozen dataclass with `passed`, `violations`, `spec_text`, `attempts`, `cost_usd`
- `TLAVerifier.available()` class method that checks for Java/TLC on PATH
- Genefication loop: LLM drafts spec → write temp .tla → TLC subprocess → parse errors → LLM fixes → retry (max 3 attempts per D048)
- Complexity threshold skip: pipelines below threshold (< 10 LOC, no control flow) skip TLA+ with `passed=True` and `skipped` reason (D047)
- `ArchiveEntry` gains optional `tla_verification: dict | None` field (backward-compatible)
- Loop gate: TLA+ check after `propose()` success, before `evaluator.evaluate()` — failed verification → discard with rationale
- Graceful degradation: when Java/TLC unavailable, log warning and skip verification (D043)
- All 267 existing tests continue passing

## Proof Level

- This slice proves: contract
- Real runtime required: no (TLC subprocess is mocked in tests)
- Human/UAT required: no

## Verification

- `pytest tests/test_verification.py -v` — unit tests for TLAVerifier: spec generation prompt, TLC subprocess mocking, genefication retry, complexity skip, availability check, VerificationResult contract
- `pytest tests/test_loop_verification.py -v` — integration tests for loop gate: proposal rejected on TLA+ failure, proposal passes on TLA+ success, gate skipped when unavailable, tla_verification field in archive entries
- `pytest tests/ -x` — full suite passes (267 + new tests, zero regressions)

## Observability / Diagnostics

- Runtime signals: `logger.info` for TLA+ pass/fail/skip with iteration context, `logger.warning` for TLC unavailable
- Inspection surfaces: `tla_verification` dict in archive JSON entries (spec_text, passed, violations, attempts, cost_usd)
- Failure visibility: `VerificationResult.violations` list, attempt count, and cost expose what went wrong and how much it cost
- Redaction constraints: none (TLA+ specs contain no secrets)

## Integration Closure

- Upstream surfaces consumed: `meta_agent.llm` (LLMProtocol for spec generation), `loop.py` (insertion after proposal), `archive.py` (ArchiveEntry dataclass)
- New wiring introduced in this slice: `TLAVerifier` instantiated in loop, gate call between proposal and evaluation, `tla_verification` field serialized in archive JSON
- What remains before the milestone is truly usable end-to-end: S02 (Pareto), S03 (leakage), S04 (sandbox + final assembly)

## Tasks

- [x] **T01: Implement TLAVerifier with genefication loop and mock TLC tests** `est:2h`
  - Why: Core verification module — the TLA+ spec generation, TLC subprocess interaction, genefication retry, and complexity threshold logic. Everything else depends on this.
  - Files: `src/autoagent/verification.py`, `tests/test_verification.py`
  - Do: Create `VerificationResult` frozen dataclass and `TLAVerifier` class. Verifier takes an LLMProtocol for spec generation. `available()` checks `shutil.which("java")` and `shutil.which("tlc2.TLC")` or a configurable TLC jar path. `verify()` does: (1) complexity check — skip if <10 non-blank non-comment lines and no `if/for/while/def` beyond `def run`, (2) build prompt from pipeline source asking LLM to generate a TLA+ spec checking termination/no-deadlock/data-flow, (3) write spec to tempfile, run TLC via subprocess, (4) parse TLC output for violations, (5) on failure, re-prompt LLM with errors (genefication), up to 3 total attempts (D048), (6) return VerificationResult. Mock TLC subprocess in tests — test success path, failure path, genefication recovery, complexity skip, unavailable skip.
  - Verify: `pytest tests/test_verification.py -v` — all tests pass
  - Done when: `TLAVerifier.verify()` returns correct `VerificationResult` for all paths (pass, fail, skip, genefication recovery) with mocked TLC and mocked LLM

- [x] **T02: Wire TLA+ gate into optimization loop and archive** `est:1h30m`
  - Why: Connects the verifier to the optimization loop so proposals are actually gate-checked, and stores verification results in the archive for post-run inspection.
  - Files: `src/autoagent/loop.py`, `src/autoagent/archive.py`, `tests/test_loop_verification.py`
  - Do: (1) Add `tla_verification: dict | None = None` field to `ArchiveEntry` dataclass, update `from_dict()` and `asdict()` to handle it, ensure backward compatibility (missing field → None). (2) Add `tla_verifier: TLAVerifier | None = None` parameter to `OptimizationLoop.__init__()`. (3) In `loop.run()`, after successful proposal and before `evaluator.evaluate()`: if `tla_verifier` is not None and `tla_verifier.available()`, call `tla_verifier.verify(proposal.proposed_source)`, accumulate `result.cost_usd` into `total_cost`, if `result.passed` is False → discard with rationale including violations, skip to next iteration. (4) Pass `tla_verification=result.asdict()` (or None) to `archive.add()` and through to the JSON file. (5) Write integration tests: mock TLAVerifier in loop context, verify discards on failure, passes on success, skips when verifier is None or unavailable, archive entries contain `tla_verification` field. (6) Run full test suite to confirm zero regressions.
  - Verify: `pytest tests/test_loop_verification.py -v && pytest tests/ -x`
  - Done when: Loop discards proposals that fail TLA+ verification, archive entries contain `tla_verification` dict, all existing tests pass

## Files Likely Touched

- `src/autoagent/verification.py` (new)
- `src/autoagent/loop.py`
- `src/autoagent/archive.py`
- `tests/test_verification.py` (new)
- `tests/test_loop_verification.py` (new)
