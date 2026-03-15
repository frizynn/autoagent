---
estimated_steps: 5
estimated_files: 2
---

# T01: Implement TLAVerifier with genefication loop and mock TLC tests

**Slice:** S01 — TLA+ Verification Gate
**Milestone:** M003

## Description

Build the core `TLAVerifier` class that generates TLA+ specs from pipeline source code via LLM, runs the TLC model checker via subprocess, and retries with genefication on spec errors. Includes complexity threshold to skip trivial pipelines and `available()` check for graceful degradation.

## Steps

1. Create `src/autoagent/verification.py` with `VerificationResult` frozen dataclass (`passed: bool`, `violations: list[str]`, `spec_text: str`, `attempts: int`, `cost_usd: float`, `skipped: bool`, `skip_reason: str`) and `TLAVerifier` class taking `llm: LLMProtocol` and optional `max_attempts: int = 3`
2. Implement `TLAVerifier.available()` — static/classmethod that checks `shutil.which("java")` for Java availability (TLC runs via `java -cp tla2tools.jar tlc2.TLC`). Return False if Java not found. Allow override via `TLC_JAR_PATH` env var or constructor param for the jar location.
3. Implement `_is_complex_enough(source: str) -> bool` — returns False (skip TLA+) if source has fewer than 10 non-blank non-comment lines AND contains no control flow keywords (`if`, `for`, `while`, `try`) beyond the top-level `def run`. This implements D047.
4. Implement `verify(source: str) -> VerificationResult` — the main method: (a) complexity check → skip if trivial, (b) prompt LLM with pipeline source to generate TLA+ spec, (c) write spec to temp `.tla` file, (d) run `java -cp <jar> tlc2.TLC <spec>` via subprocess with timeout, (e) parse TLC stdout/stderr for `Error:` / `Invariant .* is violated` patterns, (f) on failure, re-prompt LLM with spec + errors (genefication), (g) repeat up to `max_attempts` total, (h) track cumulative cost from LLM calls, (i) return VerificationResult.
5. Create `tests/test_verification.py` with tests covering: successful verification (mock TLC returns clean output), failed verification (mock TLC reports invariant violation), genefication recovery (first TLC fails, second passes after LLM fix), complexity skip (simple pipeline → skipped=True), all 3 attempts exhausted (returns passed=False with violations), unavailable (Java not on PATH → available() returns False), cost accumulation across genefication attempts.

## Must-Haves

- [ ] `VerificationResult` is a frozen dataclass with all specified fields
- [ ] `TLAVerifier.available()` correctly detects Java presence via `shutil.which`
- [ ] Complexity threshold skips trivial pipelines (< 10 LOC, no control flow)
- [ ] Genefication loop retries up to 3 times (D048)
- [ ] TLC subprocess is invoked correctly with temp file and parsed for errors
- [ ] LLM cost is accumulated across all genefication attempts
- [ ] All test paths covered: pass, fail, genefication recovery, complexity skip, unavailable

## Verification

- `pytest tests/test_verification.py -v` — all tests pass
- No imports from `loop.py` or `archive.py` — this module is self-contained

## Inputs

- `src/autoagent/primitives.py` — `LLMProtocol` interface and `MockLLM` for testing
- `src/autoagent/types.py` — `MetricsSnapshot` for cost tracking pattern
- D047 (complexity threshold), D048 (max 3 genefication attempts), D043 (graceful degradation)

## Observability Impact

- `logger.info` for TLA+ verification pass/fail/skip with source length and attempt count
- `logger.warning` when TLC/Java is unavailable (graceful degradation per D043)
- `VerificationResult` exposes: `passed`, `violations` list, `attempts` count, `cost_usd`, `skipped`/`skip_reason` — all inspectable by callers and serializable to archive JSON
- Future agent can diagnose verification issues by reading `VerificationResult.violations` and checking `attempts` vs `max_attempts`
- Failure state visible via: non-empty `violations` list, `passed=False`, attempt count showing how many genefication rounds were tried

## Expected Output

- `src/autoagent/verification.py` — complete `TLAVerifier` and `VerificationResult` ready for integration
- `tests/test_verification.py` — comprehensive unit tests with mocked TLC subprocess and MockLLM
