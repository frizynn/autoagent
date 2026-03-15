# S03: Strategy Selection & Parameter Optimization

**Goal:** The meta-agent reads archive statistics and autonomously balances structural exploration vs parameter tuning, with strategy signals visible in archive rationale and parameter-only mutations as a distinct mode.
**Demo:** Over a sequence of 20+ synthetic archive entries, the stagnation detector produces graduated strategy signals — "tune parameters" when improving, "consider structural changes" when plateaued. Strategy signals appear in `_build_prompt()` output and flow through `propose()`.

## Must-Haves

- Stagnation detector analyzes sliding window of recent entries: plateau length, score variance, structural diversity
- Graduated strategy signals (not binary mode switching) — language scales with plateau severity
- `mutation_type` field on `ArchiveEntry` (optional, backward-compatible) classifying mutations as structural vs parametric
- Mutation type classification heuristic based on pipeline diff content
- `_build_prompt()` includes `## Strategy Guidance` section when strategy signals are non-empty
- `propose()` accepts and forwards `strategy_signals` parameter
- `OptimizationLoop.run()` calls stagnation detector before `propose()` and passes signals through
- Parameter optimization prompt guidance when topology is performing well
- All existing tests pass (no regressions)

## Proof Level

- This slice proves: contract + integration
- Real runtime required: no (synthetic entries, mock LLM)
- Human/UAT required: no

## Verification

- `pytest tests/test_strategy.py -v` — stagnation detector contract tests (plateau detection, score variance, structural diversity, graduated signals, mutation type influence, edge cases)
- `pytest tests/test_meta_agent.py -v` — strategy_signals prompt integration (new tests + no regressions)
- `pytest tests/test_loop_strategy.py -v` — integration tests for loop wiring (detector called, signals forwarded, mutation_type set on archive entries)
- `pytest tests/ -v` — full suite passes, no regressions
- Diagnostic: `analyze_strategy()` output for a plateau sequence includes plateau length and diversity ratio in the signal text — verifiable by calling with synthetic entries and inspecting output

## Observability / Diagnostics

- Runtime signals: Logger `autoagent.strategy` at INFO — strategy signal summary per iteration; Logger `autoagent.loop` at DEBUG — mutation_type classification result
- Inspection surfaces: `analyze_strategy()` is a pure function — callable in REPL with synthetic entries to inspect signals
- Failure visibility: Strategy signals are plain text in prompt — inspectable via `_build_prompt()` output
- Redaction constraints: none

## Integration Closure

- Upstream surfaces consumed: `ArchiveEntry` and `Archive.recent()` from `archive.py`, `_build_prompt()`/`propose()` from `meta_agent.py`, `OptimizationLoop.run()` from `loop.py`, archive summaries from S01, component vocabulary from S02
- New wiring introduced in this slice: `strategy.py` module consumed by loop; `strategy_signals` parameter threading through meta_agent; `mutation_type` field on `ArchiveEntry`
- What remains before the milestone is truly usable end-to-end: S04 (Cold-Start Pipeline Generation)

## Tasks

- [x] **T01: Build stagnation detector and mutation type infrastructure** `est:45m`
  - Why: Core logic that everything else depends on — stagnation analysis, mutation classification, and the ArchiveEntry extension must exist before wiring
  - Files: `src/autoagent/strategy.py`, `src/autoagent/archive.py`, `tests/test_strategy.py`
  - Do: Create `strategy.py` with `analyze_strategy(entries, window=10, plateau_threshold=5) -> str` that computes plateau length, score variance, and structural diversity from a sliding window, returning graduated signal text. Add `classify_mutation(diff: str) -> str` heuristic (structural vs parametric based on control flow / function call changes vs string/number-only changes). Add `mutation_type: str | None = None` field to `ArchiveEntry` with backward-compatible `from_dict()`. Configurable window size and plateau threshold. Signals must be compact (~200-500 chars).
  - Verify: `pytest tests/test_strategy.py -v` all pass; `pytest tests/ -v` no regressions
  - Done when: `analyze_strategy()` produces correct graduated signals for: plateau sequences, improving sequences, mixed sequences, all-structural vs all-parametric histories; `classify_mutation()` correctly distinguishes structural from parametric diffs; `ArchiveEntry` accepts `mutation_type` and deserializes without it

- [x] **T02: Wire strategy signals into prompt and optimization loop** `est:40m`
  - Why: Connects the detector to the meta-agent — makes strategy signals actually influence pipeline proposals
  - Files: `src/autoagent/meta_agent.py`, `src/autoagent/loop.py`, `tests/test_meta_agent.py`, `tests/test_loop_strategy.py`
  - Do: Add `strategy_signals: str = ""` parameter to `_build_prompt()` and `propose()`. In `_build_prompt()`, append `## Strategy Guidance` section when non-empty (after history sections). In `OptimizationLoop.run()`, after archive context gathering: call `analyze_strategy()` with `archive.recent(window)` entries, pass result as `strategy_signals` to `propose()`. After evaluation, classify the mutation diff via `classify_mutation()` and pass `mutation_type` to `archive.add()`. Add parameter optimization prompt text when strategy signals indicate good topology.
  - Verify: `pytest tests/test_meta_agent.py tests/test_loop_strategy.py -v` all pass; `pytest tests/ -v` no regressions
  - Done when: `_build_prompt()` output contains `## Strategy Guidance` section when signals provided; `propose()` forwards signals; loop calls detector and passes signals; archive entries have `mutation_type` set; full test suite green

## Files Likely Touched

- `src/autoagent/strategy.py` (new)
- `src/autoagent/archive.py`
- `src/autoagent/meta_agent.py`
- `src/autoagent/loop.py`
- `tests/test_strategy.py` (new)
- `tests/test_meta_agent.py`
- `tests/test_loop_strategy.py` (new)
