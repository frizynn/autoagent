---
id: S01
parent: M003
milestone: M003
provides:
  - TLAVerifier class with verify(), available(), complexity threshold, genefication loop
  - VerificationResult frozen dataclass (passed, violations, spec_text, attempts, cost_usd, skipped, skip_reason)
  - TLA+ verification gate in OptimizationLoop between proposal and evaluation
  - tla_verification field on ArchiveEntry for archive JSON persistence
  - Graceful degradation when Java/TLC unavailable
requires: []
affects:
  - S04
key_files:
  - src/autoagent/verification.py
  - src/autoagent/loop.py
  - src/autoagent/archive.py
  - tests/test_verification.py
  - tests/test_loop_verification.py
key_decisions:
  - LLMProtocol re-declared locally in verification.py for module isolation
  - Cost extraction via duck-typed collector access (getattr)
  - Complexity threshold uses AND condition (< 10 LOC AND no control flow)
  - MockTLAVerifier duck-types interface for integration tests
patterns_established:
  - SequentialMockLLM test helper for multi-call LLM interactions (genefication)
  - _parse_tlc_output as standalone function for testability
  - MockTLAVerifier pattern for predetermined VerificationResult sequences
observability_surfaces:
  - logger.info for TLA+ pass/fail/skip with iteration context
  - logger.warning when Java unavailable (graceful degradation)
  - VerificationResult exposes violations, attempts, cost_usd, skipped, skip_reason
  - tla_verification dict in archive JSON files
drill_down_paths:
  - .gsd/milestones/M003/slices/S01/tasks/T01-SUMMARY.md
  - .gsd/milestones/M003/slices/S01/tasks/T02-SUMMARY.md
duration: 2 tasks
verification_result: passed
completed_at: 2026-03-14
---

# S01: TLA+ Verification Gate

**TLA+ verification gate wired into the optimization loop — LLM generates specs, TLC model-checks them, failures block proposals before evaluation, with genefication retry and graceful degradation.**

## What Happened

T01 built the core `TLAVerifier` class in `src/autoagent/verification.py`. The verifier takes an `LLMProtocol` for spec generation and implements the full genefication loop: complexity check (skip trivial pipelines per D047), LLM prompt to generate TLA+ spec, write to temp file, run TLC via subprocess, parse output for violations, re-prompt on failure up to 3 attempts (D048). `VerificationResult` frozen dataclass captures all outcomes including cost. `available()` checks for Java on PATH. 29 unit tests cover every path: pass, fail, genefication recovery, complexity skip, unavailable degradation, timeout, cost accumulation.

T02 wired the verifier into the optimization loop. Added `tla_verification: dict | None` field to `ArchiveEntry` (backward-compatible via `d.get()`). `OptimizationLoop` accepts an optional `tla_verifier` parameter. In `run()`, after successful proposal and before evaluation: verify → on failure, discard with violation rationale; on pass/skip, proceed to evaluation. Verification cost accumulated into `total_cost`. Archive entries persist the full verification dict. 7 integration tests cover the gate behavior.

## Verification

- `pytest tests/test_verification.py -v` — 29/29 passed
- `pytest tests/test_loop_verification.py -v` — 7/7 passed
- `pytest tests/ -x` — 303/303 passed (267 existing + 36 new, zero regressions)

## Requirements Advanced

- R014 (TLA+ Verification for All Pipelines) — TLAVerifier generates specs, model-checks via TLC, blocks failing proposals. Genefication retry implemented. Complexity threshold skips trivial pipelines. Now validated.

## Requirements Validated

- R014 — TLAVerifier with genefication loop proven by 29 unit tests (spec generation, TLC subprocess, retry recovery, complexity skip, availability check) + 7 integration tests (loop gate: pass→evaluate, fail→discard, unavailable→skip, archive persistence, cost tracking, backward compat). Contract-level proof complete.

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

- none

## Known Limitations

- TLC subprocess is mocked in all tests — no real TLC execution tested (by design: contract-level proof only, integration tests with real Java/TLC deferred to S04)
- LLMProtocol re-declared locally in verification.py rather than imported from primitives.py — maintains module isolation but creates a protocol copy

## Follow-ups

- S04 will exercise TLA+ verification with real TLC subprocess in integration tests (when Java available)
- S04 will wire all four safety gates together for final integrated verification

## Files Created/Modified

- `src/autoagent/verification.py` — new: TLAVerifier, VerificationResult, complexity threshold, TLC subprocess management, genefication loop
- `src/autoagent/archive.py` — added tla_verification field to ArchiveEntry, updated from_dict() and Archive.add()
- `src/autoagent/loop.py` — added tla_verifier parameter and verification gate logic between proposal and evaluation
- `tests/test_verification.py` — new: 29 unit tests with mocked TLC subprocess and MockLLM
- `tests/test_loop_verification.py` — new: 7 integration tests for loop verification gate

## Forward Intelligence

### What the next slice should know
- TLAVerifier follows a pattern that S03 (LeakageChecker) and S04 (SandboxRunner) can mirror: class with `available()` static method, result dataclass with `cost_usd`, optional parameter on OptimizationLoop, gate logic in run() between proposal and evaluation
- ArchiveEntry field addition pattern established: add field with `= None` default, handle in `from_dict()` with `.get()`, no migration needed

### What's fragile
- LLMProtocol is duplicated in verification.py — if the protocol in primitives.py changes, the copy must be updated manually

### Authoritative diagnostics
- `tla_verification` dict in archive JSON entries — contains passed, violations, attempts, cost_usd, skipped, skip_reason, spec_text
- `autoagent.verification` and `autoagent.loop` loggers — info for pass/fail/skip, warning for Java unavailability

### What assumptions changed
- none — implementation matched the plan closely
