# S01: Interview Orchestrator — UAT

**Milestone:** M004
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: Interview produces deterministic outputs via MockLLM — config.json and context.md are verifiable artifacts. No live runtime or human judgment required.

## Preconditions

- Python 3.11+ with `uv` available
- Project installed in dev mode (`uv run` works)
- No `.autoagent/` directory in the test working directory (or willingness to overwrite)

## Smoke Test

```bash
uv run python3 -c "from autoagent.interview import InterviewOrchestrator, SequenceMockLLM; print('imports ok')"
uv run python3 -m pytest tests/test_interview.py tests/test_cli.py -q
```
Expected: imports succeed, 35 tests pass.

## Test Cases

### 1. Happy-path interview produces valid config

1. Run `uv run python3 -m pytest tests/test_interview.py::TestHappyPath -v`
2. **Expected:** All 8 tests pass — InterviewOrchestrator completes all phases, produces InterviewResult with populated config (goal, metric_priorities, constraints, search_space, budget) and phase set to "complete".

### 2. Vague input triggers follow-up probes

1. Run `uv run python3 -m pytest tests/test_interview.py::TestVagueInputTriggersProbe -v`
2. **Expected:** 2 tests pass — vague goal ("ok") and empty answer ("") both trigger LLM follow-up probes, resulting in more LLM calls than phases (call_count > number of phases).

### 3. Max retries stops probing after 2 attempts

1. Run `uv run python3 -m pytest tests/test_interview.py::TestMaxRetries -v`
2. **Expected:** 1 test passes — after 2 vague retries, the phase accepts whatever answer was given and moves on.

### 4. Config serialization roundtrip

1. Run `uv run python3 -m pytest tests/test_interview.py::TestConfigOutput -v`
2. **Expected:** 2 tests pass — generated config has correct field values, and serialization to JSON + deserialization produces identical config.

### 5. Context.md generation

1. Run `uv run python3 -m pytest tests/test_interview.py::TestContextOutput -v`
2. **Expected:** 2 tests pass — context string is non-empty and contains key terms from the interview answers.

### 6. Backward compatibility with existing configs

1. Run `uv run python3 -m pytest tests/test_interview.py::TestBackwardCompatibility -v`
2. **Expected:** 2 tests pass — configs without the new fields deserialize with empty list defaults; configs with unknown extra keys are handled gracefully.

### 7. CLI `autoagent new` creates config and context

1. Run `uv run python3 -m pytest tests/test_cli.py::TestNew::test_cmd_new_creates_config -v`
2. Run `uv run python3 -m pytest tests/test_cli.py::TestNew::test_cmd_new_writes_context_md -v`
3. **Expected:** Both pass — `autoagent new` writes valid `config.json` with goal/metrics/constraints and non-empty `context.md` to `.autoagent/`.

### 8. CLI overwrite behavior

1. Run `uv run python3 -m pytest tests/test_cli.py::TestNew::test_cmd_new_already_initialized_with_goal -v`
2. Run `uv run python3 -m pytest tests/test_cli.py::TestNew::test_cmd_new_already_initialized_overwrite -v`
3. **Expected:** Both pass — declining overwrite leaves existing config unchanged; confirming overwrite runs the interview and updates config.

### 9. CLI keyboard interrupt

1. Run `uv run python3 -m pytest tests/test_cli.py::TestNew::test_cmd_new_keyboard_interrupt -v`
2. **Expected:** Passes — KeyboardInterrupt during interview produces clean exit with partial-state diagnostic message.

## Edge Cases

### Vague detection boundary: exactly 10 characters

1. Run `uv run python3 -m pytest tests/test_interview.py::TestVagueDetection -v`
2. **Expected:** 6 tests pass — answers with < 10 chars are vague, ≥ 10 chars are not (unless on the vague phrase list). Empty and whitespace-only answers are always vague.

### SequenceMockLLM exhaustion

1. Run `uv run python3 -m pytest tests/test_interview.py::TestSequenceMockLLM -v`
2. **Expected:** 5 tests pass — responses cycle when exhausted, call count tracked, prompts recorded, empty response list raises error.

### Observability surfaces are inspectable

1. Run `uv run python3 -m pytest tests/test_interview.py::TestObservability -v`
2. **Expected:** 2 tests pass — `orchestrator.state` dict and `orchestrator._vague_flags` are populated and inspectable after interview completes.

## Failure Signals

- `ModuleNotFoundError: No module named 'autoagent'` — package not installed, use `uv run`
- Any test in `test_interview.py` failing — interview state machine or vague detection broken
- `test_cmd_new_creates_config` failing — CLI wiring to InterviewOrchestrator broken
- `test_cmd_new_writes_context_md` failing — context.md file write path broken
- Backward compatibility tests failing — ProjectConfig schema change broke deserialization
- Total test count below 416 — regression in existing functionality

## Requirements Proved By This UAT

- R007 — GSD-2 Depth Interview Phase: multi-turn interview challenges vague input, collects structured optimization spec, writes valid config + context.md

## Not Proven By This UAT

- Real LLM interview quality — MockLLM tests prove the mechanics, not the quality of follow-up questions with a real model (non-gating per roadmap)
- Benchmark generation from interview output — S02 scope
- End-to-end flow from interview to optimization to report — S03 scope

## Notes for Tester

- All tests use MockLLM/SequenceMockLLM — no real LLM calls, no API keys needed
- Budget answer tests use descriptive strings ("$25 for this run") not bare numbers ("25") because bare numbers trip vague detection (< 10 chars). This is intentional.
- CLI tests use `-k new` not `-k interview` — the test class is `TestNew`
