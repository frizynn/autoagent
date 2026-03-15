---
id: T01
parent: S01
milestone: M003
provides:
  - TLAVerifier class with verify(), available(), complexity threshold
  - VerificationResult frozen dataclass
  - 29 unit tests covering all verification paths
key_files:
  - src/autoagent/verification.py
  - tests/test_verification.py
key_decisions:
  - LLMProtocol re-declared locally in verification.py to maintain module isolation (no imports from primitives.py at runtime — test imports are fine)
  - Cost extraction uses duck-typed collector access (getattr) rather than requiring a specific LLM base class
  - Complexity threshold: AND condition (< 10 LOC AND no control flow) — either sufficient complexity passes
patterns_established:
  - SequentialMockLLM test helper for multi-call LLM interactions (genefication)
  - _parse_tlc_output as standalone function for testability
observability_surfaces:
  - logger.info for TLA+ pass/fail/skip with attempt count and source length
  - logger.warning when Java unavailable (graceful degradation)
  - VerificationResult exposes violations, attempts, cost_usd, skipped, skip_reason
duration: 15min
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Implement TLAVerifier with genefication loop and mock TLC tests

**Built TLAVerifier with full genefication loop, complexity threshold, graceful degradation, and 29 passing tests.**

## What Happened

Created `src/autoagent/verification.py` with:
- `VerificationResult` frozen dataclass with all specified fields (passed, violations, spec_text, attempts, cost_usd, skipped, skip_reason)
- `TLAVerifier` class taking `LLMProtocol` and `max_attempts=3`
- `available()` static method checking `shutil.which("java")`
- `_is_complex_enough()` implementing D047: skips if < 10 non-blank non-comment lines AND no control flow keywords
- `verify()` with full genefication loop: complexity check → LLM prompt → temp file → TLC subprocess → parse errors → re-prompt on failure → up to 3 attempts (D048)
- TLC jar path configurable via constructor, `TLC_JAR_PATH` env var, or default
- Cost accumulated across genefication attempts via duck-typed collector access
- Structured logging at info/warning levels

Created `tests/test_verification.py` with 29 tests across 11 test classes covering: frozen dataclass contract, complexity threshold (6 cases), TLC output parsing, availability detection, successful verification, failed verification, genefication recovery (2nd and 3rd attempt), complexity skip, all attempts exhausted, cost accumulation, unavailable graceful degradation, TLC timeout, env var jar path, module isolation.

## Verification

- `pytest tests/test_verification.py -v` — 29/29 passed
- `pytest tests/ -x` — 296/296 passed (267 existing + 29 new, zero regressions)
- No imports from `loop.py` or `archive.py` in verification.py — confirmed by test and inspection

Slice-level verification status:
- ✅ `pytest tests/test_verification.py -v` — passes
- ⬜ `pytest tests/test_loop_verification.py -v` — not yet created (T02)
- ✅ `pytest tests/ -x` — 296 passed

## Diagnostics

- Inspect verification outcomes via `VerificationResult` fields: `passed`, `violations`, `attempts`, `cost_usd`, `skipped`/`skip_reason`
- Runtime logging: `autoagent.verification` logger emits info on pass/fail/skip, warning on Java unavailability
- For debugging genefication: check `attempts` count and `violations` list on failed results

## Deviations

- Re-declared `LLMProtocol` locally in verification.py instead of importing from primitives.py — maintains strict module isolation as required by the task plan ("No imports from loop.py or archive.py — this module is self-contained"). The protocol is identical.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/verification.py` — new: TLAVerifier, VerificationResult, complexity threshold, TLC subprocess management
- `tests/test_verification.py` — new: 29 unit tests with mocked TLC subprocess and MockLLM
- `.gsd/milestones/M003/slices/S01/tasks/T01-PLAN.md` — added Observability Impact section (pre-flight fix)
