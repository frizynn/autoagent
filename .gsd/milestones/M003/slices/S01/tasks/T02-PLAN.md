---
estimated_steps: 4
estimated_files: 3
---

# T02: Wire TLA+ gate into optimization loop and archive

**Slice:** S01 — TLA+ Verification Gate
**Milestone:** M003

## Description

Connect the `TLAVerifier` to the optimization loop as a gate between proposal and evaluation. Add the `tla_verification` field to `ArchiveEntry` so verification results are visible in the archive. Prove integration works with mock verifier tests.

## Steps

1. Add `tla_verification: dict | None = None` optional field to `ArchiveEntry` dataclass in `archive.py`. Update `from_dict()` to deserialize it (defaulting to None for backward compatibility). Verify `asdict()` includes it automatically (dataclass default behavior). Run existing archive tests to confirm no regressions.
2. Update `Archive.add()` to accept an optional `tla_verification: dict | None = None` parameter and pass it through to `ArchiveEntry` construction and JSON serialization.
3. Add `tla_verifier: TLAVerifier | None = None` parameter to `OptimizationLoop.__init__()`. In `loop.run()`, after proposal success and before `evaluator.evaluate()`: check if verifier exists, call `verify(proposal.proposed_source)`, accumulate `result.cost_usd` into `total_cost`. If `not result.passed` and `not result.skipped`: discard with rationale `f"tla_verification_failed: {'; '.join(result.violations)}"`, store `tla_verification` dict in archive entry, restore previous best source, continue to next iteration. If passed or skipped: store `tla_verification` in archive entry and proceed to evaluation.
4. Create `tests/test_loop_verification.py` with integration tests: (a) proposal passes TLA+ → evaluated normally, archive entry has `tla_verification` with `passed=True`, (b) proposal fails TLA+ → discarded without evaluation, archive entry has `tla_verification` with `passed=False` and violations, (c) `tla_verifier=None` → no gate, loop works as before, (d) verifier unavailable (`available()=False`) → gate skipped, entry has `tla_verification` with `skipped=True`, (e) run full test suite to confirm zero regressions.

## Must-Haves

- [ ] `ArchiveEntry` has `tla_verification` field, backward-compatible with existing JSON entries
- [ ] Loop discards proposals that fail TLA+ verification before evaluation
- [ ] Loop proceeds normally when TLA+ passes or is skipped
- [ ] `tla_verification` dict appears in archive JSON files
- [ ] `tla_verifier=None` has zero impact on existing loop behavior
- [ ] All 267 existing tests continue passing

## Verification

- `pytest tests/test_loop_verification.py -v` — all new integration tests pass
- `pytest tests/ -x` — full suite passes with zero regressions

## Observability Impact

- Signals added/changed: `logger.info` for TLA+ pass/fail/skip in loop iteration, `logger.warning` when TLC unavailable
- How a future agent inspects this: read `tla_verification` field from archive JSON files in `.autoagent/archive/`
- Failure state exposed: `violations` list and `attempts` count in `tla_verification` dict

## Inputs

- `src/autoagent/verification.py` — `TLAVerifier` and `VerificationResult` from T01
- `src/autoagent/loop.py` — insertion point after proposal validation (~L318)
- `src/autoagent/archive.py` — `ArchiveEntry` dataclass and `Archive.add()` method
- Existing test patterns from `tests/test_loop.py` — MockLLM, mock evaluator setup

## Expected Output

- `src/autoagent/archive.py` — `ArchiveEntry` with `tla_verification` field
- `src/autoagent/loop.py` — TLA+ gate wired between proposal and evaluation
- `tests/test_loop_verification.py` — integration tests proving the gate works
