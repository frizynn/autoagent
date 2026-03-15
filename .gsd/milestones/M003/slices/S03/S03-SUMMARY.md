---
id: S03
parent: M003
milestone: M003
provides:
  - LeakageChecker class with two-tier detection (exact-match blocking + fuzzy n-gram warnings)
  - LeakageResult frozen dataclass
  - Leakage gate wired into OptimizationLoop (after TLA+, before evaluation)
  - ArchiveEntry.leakage_check field for post-run inspection
requires: []
affects:
  - S04
key_files:
  - src/autoagent/leakage.py
  - src/autoagent/archive.py
  - src/autoagent/loop.py
  - tests/test_leakage.py
  - tests/test_loop_leakage.py
key_decisions:
  - D046 — exact match blocks, fuzzy match warns (already registered)
  - Per-example counting for exact_matches (break after first match per example, not per-target)
  - Combined (3,4)-grams for fuzzy detection rather than separate passes
  - Leakage gate follows identical discard pattern as TLA+ gate (zero-score stub, archive, restore, continue)
patterns_established:
  - Self-contained checker module with frozen result dataclass (matches verification.py pattern)
  - MockLeakageChecker test pattern mirrors MockTLAVerifier from test_loop_verification.py
observability_surfaces:
  - INFO log on every check outcome (blocked status, match counts, warning counts)
  - WARNING log on AST parse fallback with SyntaxError details
  - DEBUG log on per-example match details and Jaccard scores
  - leakage_check dict in archive JSON entries for post-run inspection
drill_down_paths:
  - .gsd/milestones/M003/slices/S03/tasks/T01-SUMMARY.md
  - .gsd/milestones/M003/slices/S03/tasks/T02-SUMMARY.md
duration: 30m
verification_result: passed
completed_at: 2026-03-14
---

# S03: Data Leakage Detection

**Two-tier leakage detection (AST-based exact-match blocking + word-level n-gram fuzzy warnings) wired into the optimization loop with archive persistence. 26 tests, 357 total passing.**

## What Happened

Built `leakage.py` as a self-contained module following the `verification.py` pattern. `LeakageChecker.check()` runs two passes: (1) AST-based string literal extraction matched against serialized benchmark examples — exact match → block, (2) word-level (3,4)-gram Jaccard overlap — high overlap → warn only, never block (per D046). Short examples (both representations < 10 chars) are skipped. AST parse failures fall back to regex extraction with a WARNING log.

Wired the gate into `OptimizationLoop` after TLA+ verification and before evaluation. Same discard pattern: zero-score eval stub, archive entry, restore pipeline, continue. Added `leakage_check: dict | None` to `ArchiveEntry` for post-run inspection. `cost_usd` always 0.0 for now (forward-compatible for LLM-based detection later).

## Verification

- `pytest tests/test_leakage.py -v` — 21/21 passed (exact match, fuzzy, short skip, AST fallback, empty benchmark, helpers)
- `pytest tests/test_loop_leakage.py -v` — 5/5 passed (blocked discard, warning proceeds, no checker skip, cost tracking, JSON persistence)
- `pytest tests/ -v` — 357/357 passed, zero regressions
- Observability confirmed: INFO/DEBUG/WARNING logging all active at correct levels

## Requirements Advanced

- R009 (Data Leakage Guardrail) — primary validation: every evaluation preceded by leakage check, exact overlap blocks, fuzzy overlap warns

## Requirements Validated

- R009 — contract-level proof: LeakageChecker detects exact train/test contamination (blocks) and fuzzy overlap (warns), wired into loop before evaluation with archive persistence. 26 tests prove all detection paths and gate behavior.

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

None.

## Known Limitations

- `cost_usd` is always 0.0 — forward-compatible placeholder for potential LLM-based detection
- Fuzzy detection uses word-level tokenization only — character n-grams or embedding similarity could catch more subtle contamination but would add complexity

## Follow-ups

- none — S04 consumes this gate for final assembly

## Files Created/Modified

- `src/autoagent/leakage.py` — New module: `LeakageResult` frozen dataclass + `LeakageChecker` class
- `tests/test_leakage.py` — 21 unit tests covering all detection paths
- `tests/test_loop_leakage.py` — 5 integration tests for leakage gate in loop
- `src/autoagent/archive.py` — Added `leakage_check` field to `ArchiveEntry`, `from_dict()`, `Archive.add()`
- `src/autoagent/loop.py` — Added `leakage_checker` parameter, leakage gate after TLA+ gate

## Forward Intelligence

### What the next slice should know
- Leakage gate is the third gate in the loop sequence: TLA+ → leakage → evaluation. S04 (sandbox) wraps the evaluation step itself, so it slots in after the leakage gate naturally.
- `LeakageChecker` is self-contained — no imports from `loop` or `archive`. Pass it as a parameter to `OptimizationLoop`.
- The discard-on-gate-failure pattern is now used by both TLA+ and leakage gates — S04 should follow the same pattern for sandbox failures.

### What's fragile
- Fuzzy threshold (0.3 default) was chosen heuristically — real-world benchmarks may need tuning to avoid false positives on domain-specific text

### Authoritative diagnostics
- `leakage_check` dict in archive JSON entries — authoritative record of what the gate decided and why
- DEBUG log on `autoagent.leakage` — per-example Jaccard scores for threshold tuning

### What assumptions changed
- None — implementation matched the plan exactly
