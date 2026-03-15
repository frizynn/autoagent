---
estimated_steps: 5
estimated_files: 3
---

# T01: Build stagnation detector and mutation type infrastructure

**Slice:** S03 — Strategy Selection & Parameter Optimization
**Milestone:** M002

## Description

Create the core strategy analysis logic: a stagnation detector that reads recent archive entries and produces graduated strategy signals, a mutation classifier that distinguishes structural from parametric diffs, and the `mutation_type` field extension on `ArchiveEntry`. All three are independently testable with synthetic data — no LLM calls, no loop integration.

## Steps

1. Add `mutation_type: str | None = None` field to `ArchiveEntry` in `archive.py`. Update `from_dict()` to use `.get("mutation_type")` for backward compatibility. Update `asdict()` output (handled automatically by dataclasses.asdict). Verify existing archive tests still pass.

2. Create `src/autoagent/strategy.py` with `classify_mutation(diff: str) -> str` — returns `"structural"` if the diff adds/removes function definitions, new primitive calls (`primitives.`), control flow changes (if/else/for/while/try/return at different indentation), or new imports; returns `"parametric"` otherwise (string literal changes, number changes, variable renames). Use simple line-by-line heuristics, not AST parsing.

3. In same module, create `analyze_strategy(entries: list[ArchiveEntry], window: int = 10, plateau_threshold: int = 5) -> str` that:
   - Takes at most `window` most recent entries (already sorted newest-first from `Archive.recent()`)
   - Computes plateau length: consecutive most-recent iterations without primary_score improvement over the window's best
   - Computes score variance across the window (low variance = stuck)
   - Computes structural diversity: ratio of structural vs parametric mutations in the window (using `mutation_type` field, falling back to `classify_mutation(pipeline_diff)` when None)
   - Returns graduated signal text: no signal when improving, mild "consider parameter tuning" when improving with good topology, escalating "consider structural changes" as plateau length grows, with specific numbers ("scores plateaued for N iterations")

4. Write `tests/test_strategy.py` with tests covering:
   - `classify_mutation`: structural diff (new function def, new import, control flow change), parametric diff (string change, number change), empty diff
   - `analyze_strategy`: empty entries → empty string, improving sequence → parameter tuning suggestion, plateau of 5+ → structural exploration signal, plateau of 8+ → stronger signal, all-parametric history during plateau → suggests structural, all-structural history during plateau → suggests parameter tuning, entries without mutation_type → falls back to diff classification
   - Edge cases: single entry, window larger than entries, all identical scores

5. Run full test suite to verify no regressions from `ArchiveEntry` field addition.

## Must-Haves

- [ ] `mutation_type` field on `ArchiveEntry` with default `None`, backward-compatible deserialization
- [ ] `classify_mutation()` distinguishes structural from parametric diffs using line-level heuristics
- [ ] `analyze_strategy()` produces graduated signals based on plateau length, score variance, and structural diversity
- [ ] Signals are compact (~200-500 chars) and use graduated language, not binary mode switching
- [ ] All tests in `test_strategy.py` pass
- [ ] No regressions in existing test suite

## Verification

- `pytest tests/test_strategy.py -v` — all strategy tests pass
- `pytest tests/ -v` — full suite green, no regressions from ArchiveEntry changes

## Observability Impact

- Signals added/changed: `classify_mutation()` and `analyze_strategy()` are pure functions — no runtime signals yet (added in T02)
- How a future agent inspects this: Call `analyze_strategy()` or `classify_mutation()` directly with synthetic data in REPL
- Failure state exposed: Strategy signal text includes plateau length and diversity ratio — diagnostic info embedded in output

## Inputs

- `src/autoagent/archive.py` — `ArchiveEntry` dataclass (frozen, L83-98), `from_dict()` (L109-120)
- `tests/test_meta_agent.py` — `_make_entry()` helper pattern for creating test entries
- S03-RESEARCH.md — stagnation detection approach, calibration strategy, pitfall warnings

## Expected Output

- `src/autoagent/strategy.py` — new module with `classify_mutation()` and `analyze_strategy()` functions
- `src/autoagent/archive.py` — `ArchiveEntry` with `mutation_type` field, updated `from_dict()`
- `tests/test_strategy.py` — comprehensive test suite for strategy logic (~12-15 tests)
