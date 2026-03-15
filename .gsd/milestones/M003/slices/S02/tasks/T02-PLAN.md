---
estimated_steps: 5
estimated_files: 3
---

# T02: Wire Pareto decision into optimization loop and verify integration

**Slice:** S02 — Pareto Evaluation with Simplicity Criterion
**Milestone:** M003

## Description

Replace the single-score keep/discard logic in `loop.py` with `pareto_decision()` and update resume logic to reconstruct the full metrics vector. Verify that all existing tests pass unchanged — the key insight is that MockLLM-based tests produce None/zero metrics, causing Pareto to degrade to score-only comparison naturally.

## Steps

1. In `loop.py`, import `pareto_decision`, `compute_complexity`, and `ParetoResult` from `autoagent.pareto`
2. Add `best_metrics: dict | None = None` tracking variable alongside `best_score` (keep `best_score` — it's used by state tracking)
3. Replace L396-403 keep/discard block:
   - Build `candidate_metrics` dict from `eval_result.primary_score`, `eval_result.metrics` (latency_ms, cost_usd), and `compute_complexity(proposal.proposed_source)`
   - Call `pareto_decision(candidate_metrics, best_metrics, proposal.proposed_source, current_best_source)`
   - Set `decision = pareto_result.decision`
   - On keep: update `best_score`, `best_metrics`, `current_best_source`
4. Update resume logic (L160-169): when reconstructing from archive's best kept entry, also reconstruct `best_metrics` dict from the entry's evaluation_result metrics + pareto_evaluation complexity, and read `current_best_source` from archive pipeline snapshot (already done for source, add metrics)
5. Pass `pareto_evaluation=asdict(pareto_result)` (or `pareto_result.__dict__` equivalent) to `archive.add()` call at L426-437
6. Run `python3 -m pytest tests/test_loop.py -v` — verify all existing tests pass unchanged
7. Run `python3 -m pytest tests/ -v` — full suite green, zero regressions

## Must-Haves

- [ ] `best_score` variable preserved for state compatibility
- [ ] Pareto decision replaces score comparison — not added alongside it
- [ ] Resume reconstructs `best_metrics` from archive entry
- [ ] `pareto_evaluation` dict stored in archive entries
- [ ] All existing loop tests pass without modification
- [ ] Full test suite passes (303+ tests, zero regressions)

## Verification

- `python3 -m pytest tests/test_loop.py -v` — all existing loop tests pass
- `python3 -m pytest tests/ -v` — full suite green
- Inspect a test's archive output to confirm `pareto_evaluation` key is present

## Observability Impact

- Signals added: `pareto_evaluation` dict in archive entries (decision, rationale, candidate_metrics, best_metrics)
- How a future agent inspects this: read archive JSON files, look at `pareto_evaluation.rationale` for why each iteration was kept/discarded
- Failure state exposed: Pareto rationale in archive makes multi-metric tradeoff decisions inspectable post-run

## Inputs

- `src/autoagent/pareto.py` — T01 output, the module to wire in
- `src/autoagent/loop.py` — integration target (L396-403 keep/discard, L160-169 resume)
- `tests/test_loop.py` — existing tests that must pass unchanged

## Expected Output

- `src/autoagent/loop.py` — updated with Pareto decision logic, resume reconstruction, archive field
- Full test suite passing with zero regressions
