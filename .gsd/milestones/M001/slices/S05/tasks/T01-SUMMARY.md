---
id: T01
parent: S05
milestone: M001
provides:
  - MetaAgent class with propose(), _build_prompt(), _extract_source(), _validate_source()
  - ProposalResult dataclass
key_files:
  - src/autoagent/meta_agent.py
  - tests/test_meta_agent.py
key_decisions:
  - Source extraction picks longest code block when multiple fenced blocks present
  - Validation executes compiled code into a temp module to check run() callability
  - Cost tracking uses incremental diff on collector aggregate (before/after propose call)
patterns_established:
  - MetaAgent uses LLM's collector directly; cost isolation is structural (separate collector instances)
observability_surfaces:
  - ProposalResult.error — structured error string on failure (syntax error detail, missing run, empty response)
  - ProposalResult.cost_usd — per-proposal LLM cost from MetricsCollector
duration: 15m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: Build MetaAgent with prompt construction and source extraction

**Built MetaAgent: reads archive history, constructs mutation prompt, calls LLM, extracts+validates pipeline source with robust fence stripping and compile checks.**

## What Happened

Created `MetaAgent` class that accepts an LLM instance and goal string. The `_build_prompt()` method constructs a structured prompt with system instructions, goal, benchmark description, current pipeline source, top-K kept entries (sorted by score), and recent discards. The prompt explicitly instructs the LLM to output a complete module with `def run(input_data, primitives=None)`.

`_extract_source()` strips markdown fences using a regex, picks the longest block when multiple are present, and falls back to treating the entire response as source. `_validate_source()` compiles the source and executes it into a temporary module to verify a callable `run` exists.

`propose()` orchestrates the flow: build prompt → call LLM → extract → validate → return `ProposalResult`. Cost is tracked incrementally via the LLM's `MetricsCollector`.

Wrote 25 tests covering all layers: prompt construction (6 tests), source extraction (6 tests), validation (5 tests), full propose flow (7 tests), and import contract (1 test).

## Verification

- `pytest tests/test_meta_agent.py -v` — 25/25 passed
- `python -c "from autoagent.meta_agent import MetaAgent, ProposalResult"` — OK
- `pytest tests/ -v` — 162/162 passed, zero regressions

### Slice-level verification status (T01 is intermediate):
- ✅ `pytest tests/test_meta_agent.py -v` — passes
- ⬜ `pytest tests/test_loop.py -v` — not yet created (T02)
- ✅ `pytest tests/ -v` — full suite passes
- ✅ MetaAgent failure paths produce structured errors in ProposalResult.error

## Diagnostics

- `ProposalResult.error` contains structured error strings: `"syntax error: ..."`, `"missing run() function"`, `"run is not callable"`, `"empty response"`
- `ProposalResult.cost_usd` gives per-proposal LLM cost; inspect the LLM's `MetricsCollector.snapshots` for full call details
- `MetaAgent._build_prompt()` returns plain text — can be called directly to inspect/debug prompt quality

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/meta_agent.py` — MetaAgent class with ProposalResult dataclass
- `tests/test_meta_agent.py` — 25 unit tests covering prompt, extraction, validation, propose flow, cost tracking
- `.gsd/milestones/M001/slices/S05/S05-PLAN.md` — added failure-path verification step (pre-flight fix)
- `.gsd/milestones/M001/slices/S05/tasks/T01-PLAN.md` — added Observability Impact section (pre-flight fix)
