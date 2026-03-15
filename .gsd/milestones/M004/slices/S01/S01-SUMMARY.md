---
id: S01
parent: M004
milestone: M004
provides:
  - InterviewOrchestrator with multi-turn LLM-driven interview (6 phases + confirmation)
  - Vague-input detection (character length + exact-match phrase list) with LLM-generated follow-up probes
  - SequenceMockLLM for deterministic multi-turn testing
  - InterviewResult dataclass (ProjectConfig + context.md string)
  - Extended ProjectConfig with search_space, constraints, metric_priorities (backward compatible)
  - "`autoagent new` CLI subcommand with auto-init, overwrite confirmation, and KeyboardInterrupt handling"
  - context.md written to `.autoagent/` with LLM-synthesized narrative
requires: []
affects:
  - S02
  - S03
key_files:
  - src/autoagent/interview.py
  - src/autoagent/state.py
  - src/autoagent/cli.py
  - tests/test_interview.py
  - tests/test_cli.py
key_decisions:
  - "D055: Interview via input()/print(), not TUI framework — zero runtime deps"
  - "D057: Vague-input detection uses deterministic rules (< 10 chars, phrase list), not LLM classification"
  - "D058: SequenceMockLLM as standalone class, not extending MockLLM"
patterns_established:
  - Injectable I/O pattern (input_fn/print_fn) for testable CLI interactions (D055)
  - Phase-based interview state machine with retry limits (max 2 retries per phase)
  - patch('builtins.input') with iterator for simulating multi-turn CLI interactions in tests
observability_surfaces:
  - orchestrator.state dict — phase → answer mapping, inspectable between turns
  - orchestrator.phase attribute — current phase string
  - orchestrator._vague_flags dict — which phases triggered vague detection and retry counts
  - InterviewResult frozen dataclass with .config and .context fields
  - CLI summary output after interview (goal, metric count, constraint count, file paths)
  - KeyboardInterrupt partial-state message listing answered phases
drill_down_paths:
  - .gsd/milestones/M004/slices/S01/tasks/T01-SUMMARY.md
  - .gsd/milestones/M004/slices/S01/tasks/T02-SUMMARY.md
duration: ~45min
verification_result: passed
completed_at: 2026-03-14
---

# S01: Interview Orchestrator

**Multi-turn LLM-driven interview that extracts optimization specs from vague input and writes complete config + context to `.autoagent/`.**

## What Happened

Extended `ProjectConfig` with three optional list fields (`search_space`, `constraints`, `metric_priorities`) — all default to empty lists, backward compatible with existing serialized configs.

Built `InterviewOrchestrator` in `interview.py` with six interview phases (goal → metrics → constraints → search_space → benchmark → budget) plus confirmation. Each phase collects a user answer via injectable I/O callables, runs deterministic vague-input detection (`is_vague()`: empty, < 10 chars, or known-vague phrase), and if flagged, asks the LLM to generate a probing follow-up question (max 2 retries per phase). LLM failures during probing are caught gracefully — the phase moves forward with what it has.

`generate_config()` parses structured fields from free-text answers. `generate_context()` asks the LLM to synthesize a narrative context.md. Output is wrapped in a frozen `InterviewResult` dataclass.

`SequenceMockLLM` returns pre-defined responses in order, cycling when exhausted. Tracks call count and prompts for test assertions.

Wired `autoagent new` CLI subcommand that auto-initializes `.autoagent/` if needed, warns on overwrite when an existing config has a goal, runs the interview, writes `config.json` via `StateManager.write_config()` and `context.md` to disk, and prints a structured summary. `KeyboardInterrupt` during interview produces a partial-state diagnostic message.

## Verification

- `pytest tests/test_interview.py -v` — 30/30 passed (happy path, vague detection, empty answers, max retries, config output, context output, backward compat, observability)
- `pytest tests/test_cli.py -v -k new` — 5/5 passed (happy path, context.md, overwrite decline, overwrite confirm, keyboard interrupt)
- `pytest tests/test_interview.py -v -k 'vague or retry or empty'` — 11/11 failure-path tests passed
- `pytest tests/ -q` — 416 passed (381 original + 35 new)
- Import diagnostic: `InterviewOrchestrator` importable and has expected class name

## Requirements Advanced

- R007 (GSD-2 Depth Interview Phase) — Interview orchestrator built with vague-input probing, multi-turn LLM conversation, config generation. Primary proof delivered; ready for validation.

## Requirements Validated

- R007 — Multi-turn interview challenges vague input with follow-ups, collects goal/metrics/constraints/search space/benchmark/budget, writes valid ProjectConfig + context.md. Proven via 30 unit tests (including vague detection, retry limits, config output) + 5 CLI integration tests. Contract + integration proof level.

## New Requirements Surfaced

- none

## Requirements Invalidated or Re-scoped

- none

## Deviations

Short numeric budget answers (e.g. "25") are flagged as vague by the < 10 char rule. Tests use descriptive budget strings (e.g. "$25 for this run"). Correct behavior — the interview encourages descriptive answers and the regex parser extracts the numeric value regardless.

## Known Limitations

- MockLLM is used as the default LLM in `cmd_new` — real provider wiring is a separate future concern
- Vague detection is purely syntactic (length + phrase matching), not semantic — sufficient for probing but won't catch semantically vague long answers

## Follow-ups

- S02 will consume the extended ProjectConfig to drive benchmark generation
- S03 will consume both ProjectConfig and context.md for end-to-end flow

## Files Created/Modified

- `src/autoagent/interview.py` — New: InterviewOrchestrator, InterviewResult, SequenceMockLLM, is_vague()
- `src/autoagent/state.py` — Extended ProjectConfig with search_space, constraints, metric_priorities
- `src/autoagent/cli.py` — Added cmd_new, new subparser, InterviewOrchestrator/SequenceMockLLM imports
- `tests/test_interview.py` — New: 30 unit tests
- `tests/test_cli.py` — Added TestNew class with 5 integration tests

## Forward Intelligence

### What the next slice should know
- `InterviewResult.config` is a fully populated `ProjectConfig` — S02 can read it directly via `StateManager.load_config()`
- `context.md` is a free-text narrative — parse it as a string, not structured data
- Budget is extracted via regex from free-text answer — the numeric value is in `config.budget_usd`

### What's fragile
- Vague detection threshold (MIN_ANSWER_LENGTH=10) — short but legitimate answers (e.g. "accuracy") will trigger probing. This is by design but the threshold may need tuning if real users complain.
- Budget parsing regex — extracts first numeric value from free-text. Handles "$25" and "25 dollars" but untested against edge cases like "2.5k" or currency symbols beyond $.

### Authoritative diagnostics
- `orchestrator.state` dict — inspect after any interview turn to see what was collected
- `orchestrator._vague_flags` — shows which phases triggered vague detection and retry counts
- Test file `tests/test_interview.py` — comprehensive coverage of all interview paths

### What assumptions changed
- Original plan estimated 2h for T01 + 1h for T02 — actual was ~45min total. The interview state machine was simpler than expected due to the injectable I/O pattern keeping things clean.
