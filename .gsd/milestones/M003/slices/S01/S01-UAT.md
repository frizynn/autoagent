# S01: TLA+ Verification Gate — UAT

**Milestone:** M003
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: TLA+ verification is contract-level — TLC subprocess is mocked, no live Java/TLC runtime needed. All behavior proven via pytest with mock LLM and mock subprocess.

## Preconditions

- Python 3.11+ with project venv activated (`.venv/bin/python`)
- Project dependencies installed (`pip install -e .`)
- Working directory: project root

## Smoke Test

Run `pytest tests/test_verification.py tests/test_loop_verification.py -v` — all 36 tests pass.

## Test Cases

### 1. TLAVerifier produces correct VerificationResult on TLC success

1. Create a `TLAVerifier` with a mock LLM that returns a TLA+ spec
2. Mock `subprocess.run` to return clean TLC output (exit code 0, "Model checking completed. No error has been found.")
3. Call `verifier.verify(complex_pipeline_source)`
4. **Expected:** `VerificationResult(passed=True, violations=[], attempts=1, cost_usd>=0, skipped=False)`

### 2. TLAVerifier rejects pipeline on TLC invariant violation

1. Create a `TLAVerifier` with a mock LLM
2. Mock `subprocess.run` to return TLC output with "Error: Invariant InvariantName is violated" on all attempts
3. Call `verifier.verify(complex_pipeline_source)`
4. **Expected:** `VerificationResult(passed=False, violations=['Invariant InvariantName is violated'], attempts=3, skipped=False)`

### 3. Genefication recovery on second attempt

1. Create a `TLAVerifier` with a `SequentialMockLLM` returning [bad_spec, good_spec]
2. Mock TLC to fail on first call (invariant violation), succeed on second call
3. Call `verifier.verify(complex_pipeline_source)`
4. **Expected:** `VerificationResult(passed=True, attempts=2)` — recovered via genefication

### 4. Complexity threshold skips simple pipelines

1. Call `verifier.verify(simple_pipeline_source)` where source has < 10 LOC and no control flow
2. **Expected:** `VerificationResult(passed=True, skipped=True, skip_reason='below complexity threshold', attempts=0)`

### 5. Graceful degradation when Java unavailable

1. Mock `shutil.which("java")` to return `None`
2. Call `verifier.verify(any_source)`
3. **Expected:** `VerificationResult(passed=True, skipped=True, skip_reason='Java/TLC not available', attempts=0)`

### 6. Loop gate rejects proposal on TLA+ failure

1. Create an `OptimizationLoop` with a `MockTLAVerifier` that returns `passed=False`
2. Run one iteration
3. **Expected:** Proposal is discarded without calling `evaluator.evaluate()`. Archive entry has `rationale` containing "TLA+ verification failed" and `tla_verification.passed == False`.

### 7. Loop gate passes proposal on TLA+ success

1. Create an `OptimizationLoop` with a `MockTLAVerifier` that returns `passed=True`
2. Run one iteration
3. **Expected:** Proposal proceeds to evaluation normally. Archive entry has `tla_verification.passed == True`.

### 8. Loop works unchanged without verifier

1. Create an `OptimizationLoop` without `tla_verifier` parameter (default None)
2. Run one iteration
3. **Expected:** Behaves identically to pre-S01 — no TLA+ verification, `tla_verification` field is None in archive.

### 9. Archive backward compatibility

1. Load an archive JSON file written before S01 (no `tla_verification` key)
2. Parse via `ArchiveEntry.from_dict()`
3. **Expected:** `entry.tla_verification is None` — no errors, backward compatible.

### 10. TLA+ verification cost tracked in budget

1. Create a `MockTLAVerifier` returning `cost_usd=0.05`
2. Run loop with `budget_usd=0.10`
3. **Expected:** `total_cost` in loop includes the $0.05 TLA+ verification cost.

## Edge Cases

### TLC subprocess timeout

1. Mock `subprocess.run` to raise `subprocess.TimeoutExpired`
2. Call `verifier.verify(complex_source)`
3. **Expected:** Treated as a violation ("TLC timed out"), counted as a failed attempt, genefication continues.

### All three genefication attempts fail

1. Mock TLC to return violations on all 3 calls
2. Call `verifier.verify(complex_source)`
3. **Expected:** `VerificationResult(passed=False, attempts=3)` — does not retry beyond max.

### TLC jar path from environment variable

1. Set `TLC_JAR_PATH=/custom/path/tla2tools.jar` in environment
2. Create `TLAVerifier` without explicit jar_path
3. **Expected:** TLC subprocess uses the env var path.

## Failure Signals

- Any of the 303 tests failing in `pytest tests/ -x`
- `tla_verification` missing from archive JSON entries after a verification-enabled loop run
- Loop proceeding to evaluation despite TLA+ failure (no gate enforcement)
- Cost not accumulated from verification into total_cost
- Import errors between verification.py and loop.py/archive.py (module isolation broken)

## Requirements Proved By This UAT

- R014 (TLA+ Verification for All Pipelines) — TLAVerifier generates specs for every proposed pipeline, model-checks via TLC, blocks failures. Genefication retry (D048), complexity threshold skip (D047), graceful degradation (D043) all proven.

## Not Proven By This UAT

- Real TLC execution with actual Java runtime (deferred to S04 integration tests)
- Quality of LLM-generated TLA+ specs against real pipeline code (runtime concern, not contract)
- Interaction with other safety gates (S02 Pareto, S03 leakage, S04 sandbox — tested in S04)

## Notes for Tester

- All tests use mocked TLC subprocess and mock LLM — no Java or TLC installation needed
- The `SequentialMockLLM` helper in test_verification.py returns predetermined responses in order — useful pattern for testing multi-call LLM interactions
- Test cases 6-10 are implemented in `tests/test_loop_verification.py`; cases 1-5 and edge cases in `tests/test_verification.py`
