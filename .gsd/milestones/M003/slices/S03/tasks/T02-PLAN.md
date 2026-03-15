---
estimated_steps: 5
estimated_files: 3
---

# T02: Wire leakage gate into loop and archive

**Slice:** S03 — Data Leakage Detection
**Milestone:** M003

## Description

Integrate `LeakageChecker` into the optimization loop and archive. The leakage gate runs after TLA+ verification, before evaluation. Blocked iterations are discarded without burning eval tokens. Archive entries gain a `leakage_check` field for post-run inspection. Integration tests prove the gate works end-to-end with the loop.

## Steps

1. Update `src/autoagent/archive.py`:
   - Add `leakage_check: dict[str, Any] | None = None` field to `ArchiveEntry` (after `pareto_evaluation`)
   - Update `from_dict()` to deserialize with `.get("leakage_check")`
   - Add `leakage_check` parameter to `Archive.add()`, pass through to `ArchiveEntry` constructor
2. Update `src/autoagent/loop.py`:
   - Add `from autoagent.leakage import LeakageChecker` import
   - Add `leakage_checker: LeakageChecker | None = None` parameter to `OptimizationLoop.__init__()`, store as `self.leakage_checker`
   - Insert leakage gate after TLA+ verification gate (after ~L396), before evaluation (~L397):
     - `leakage_check: dict | None = None`
     - If `self.leakage_checker is not None`: call `check(self.benchmark, proposal.proposed_source)`
     - Accumulate `result.cost_usd` into `total_cost`
     - Build `leakage_check` dict from result fields
     - If `result.blocked`: log, create failed eval stub, archive with rationale `"leakage_blocked: N exact matches"`, restore pipeline, continue
     - If warnings: log them at WARNING level
   - Pass `leakage_check` to all `self.archive.add()` calls in the loop (both the blocked-discard path and the normal eval path)
3. Create `tests/test_loop_leakage.py` following `test_loop_verification.py` pattern:
   - `MockLeakageChecker` class returning predetermined `LeakageResult` values
   - Test: blocked iteration → discarded without evaluation, archive entry has `leakage_check` with `blocked=True`
   - Test: warning iteration → proceeds to evaluation, archive entry has `leakage_check` with warnings
   - Test: no checker configured → gate skipped entirely, loop works as before
   - Test: leakage cost tracked in `total_cost_usd`
4. Run full test suite to verify zero regressions
5. Verify existing archive tests still pass (backward compatibility of new optional field)

## Must-Haves

- [ ] `ArchiveEntry.leakage_check` is optional with `None` default (backward-compatible)
- [ ] `from_dict()` handles missing `leakage_check` key via `.get()`
- [ ] Leakage gate runs after TLA+ gate, before evaluation
- [ ] Blocked iteration → discard + archive + restore pipeline + continue (same pattern as TLA+ gate)
- [ ] `leakage_check` dict included in archive entries for both blocked and normal iterations
- [ ] `cost_usd` from `LeakageResult` accumulated in loop's `total_cost`
- [ ] No checker configured → gate skipped, no errors

## Verification

- `python3 -m pytest tests/test_loop_leakage.py -v` — all integration tests pass
- `python3 -m pytest tests/ -v` — full suite passes, zero regressions
- Inspect a test's archive entry JSON to confirm `leakage_check` field present

## Observability Impact

- Signals added/changed: `leakage_check` dict in archive entries (`blocked`, `exact_matches`, `fuzzy_warnings`), WARNING-level log for fuzzy warnings, INFO-level log for blocked iterations
- How a future agent inspects this: read archive JSON entries for `leakage_check` field; grep logs for "leakage"
- Failure state exposed: `blocked=True` with `exact_matches` count in archive; rationale string explains why iteration was discarded

## Inputs

- `src/autoagent/leakage.py` — `LeakageChecker` and `LeakageResult` from T01
- `src/autoagent/archive.py` — `ArchiveEntry` and `Archive.add()` to extend
- `src/autoagent/loop.py` — `OptimizationLoop` to wire gate into
- `tests/test_loop_verification.py` — test pattern to follow

## Expected Output

- `src/autoagent/archive.py` — `ArchiveEntry` with `leakage_check` field, `Archive.add()` with `leakage_check` parameter
- `src/autoagent/loop.py` — leakage gate wired after TLA+, before evaluation
- `tests/test_loop_leakage.py` — integration tests proving gate behavior in the loop
