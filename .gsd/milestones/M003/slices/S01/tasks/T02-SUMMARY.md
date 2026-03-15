---
id: T02
parent: S01
milestone: M003
provides:
  - TLA+ verification gate wired into OptimizationLoop between proposal and evaluation
  - tla_verification field on ArchiveEntry for archive JSON persistence
key_files:
  - src/autoagent/archive.py
  - src/autoagent/loop.py
  - tests/test_loop_verification.py
key_decisions:
  - TLA+ verification dict serialized manually (not via dataclasses.asdict on VerificationResult) for explicit field control in archive JSON
  - MockTLAVerifier test helper duck-types TLAVerifier interface (verify/available) rather than subclassing
patterns_established:
  - MockTLAVerifier pattern for integration tests with predetermined VerificationResult sequences
observability_surfaces:
  - logger.info for TLA+ pass/fail/skip with iteration context in loop
  - tla_verification dict in archive JSON files (passed, violations, attempts, cost_usd, skipped, skip_reason, spec_text)
duration: 1 task
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T02: Wire TLA+ gate into optimization loop and archive

**Wired TLAVerifier as a gate between proposal and evaluation in OptimizationLoop; added tla_verification field to ArchiveEntry with backward-compatible JSON persistence.**

## What Happened

1. Added `tla_verification: dict[str, Any] | None = None` field to `ArchiveEntry` dataclass. Updated `from_dict()` to deserialize it with `d.get("tla_verification")` for backward compatibility. `asdict()` includes it automatically.

2. Updated `Archive.add()` to accept and pass through `tla_verification` parameter to `ArchiveEntry` construction.

3. Added `tla_verifier: TLAVerifier | None = None` parameter to `OptimizationLoop.__init__()`. In `run()`, after successful proposal and before evaluation: calls `verifier.verify(proposal.proposed_source)`, accumulates `result.cost_usd` into `total_cost`, and on failure discards with rationale containing violations. On pass/skip, proceeds to evaluation. Both paths store the `tla_verification` dict in the archive entry.

4. Created `tests/test_loop_verification.py` with 7 integration tests covering: pass → evaluated normally, fail → discarded without evaluation, no verifier → unchanged behavior, unavailable → skipped, JSON persistence on disk, cost accumulation, and backward compatibility with old entries.

## Verification

- `pytest tests/test_loop_verification.py -v` — 7/7 passed
- `pytest tests/ -x` — 303 passed, zero regressions (was 296 before T01+T02)
- `pytest tests/test_verification.py -v` — 29/29 passed (T01 tests unaffected)
- `pytest tests/test_archive.py -x` — 32/32 passed

## Diagnostics

- Inspect verification outcomes in archive JSON: read `tla_verification` field from `.autoagent/archive/NNN-{keep|discard}.json`
- Runtime logging: `autoagent.loop` logger emits info for TLA+ pass/fail/skip per iteration with iteration number
- For debugging: check `tla_verification.violations` list and `tla_verification.attempts` count in discarded entries

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/archive.py` — Added `tla_verification` field to `ArchiveEntry`, updated `from_dict()` and `Archive.add()`
- `src/autoagent/loop.py` — Added `tla_verifier` parameter and verification gate logic between proposal and evaluation
- `tests/test_loop_verification.py` — 7 integration tests for the verification gate
