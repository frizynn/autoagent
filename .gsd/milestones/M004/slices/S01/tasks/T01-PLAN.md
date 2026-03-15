---
estimated_steps: 5
estimated_files: 3
---

# T01: Build InterviewOrchestrator with vague-input detection and config generation

**Slice:** S01 — Interview Orchestrator
**Milestone:** M004

## Description

Build the core interview engine that drives a multi-turn LLM conversation to extract an optimization spec from the user. The orchestrator uses LLMProtocol to generate probing questions, detects vague/insufficient answers and requests clarification, then produces a populated ProjectConfig and context.md narrative.

This is where R007 (GSD-2 Depth Interview Phase) is primarily implemented. The interview must not passively accept garbage — it challenges vagueness with follow-up probes.

## Steps

1. **Extend ProjectConfig** — Add optional fields `search_space: list[str]`, `constraints: list[str]`, `metric_priorities: list[str]` to the frozen dataclass in `state.py`. All default to empty lists. Ensure `from_dict` ignores unknown keys (already does) and handles missing new fields gracefully. Verify existing tests still pass after this change.

2. **Build InterviewOrchestrator** — New module `interview.py`. Class takes `llm: LLMProtocol` and injectable I/O callables `input_fn` and `print_fn` (defaulting to `input` and `print` per D055, but testable). Interview runs through phases: goal, metrics, constraints, search_space, benchmark, budget, confirmation. Each phase:
   - Presents a question (LLM-generated or template)
   - Collects user answer
   - Runs vague-input detection (short answers < 10 chars, generic phrases like "better"/"good"/"improve", empty strings)
   - If vague: asks LLM to generate a probing follow-up, re-asks (max 2 retries per phase, then accepts what we have)
   - Records structured answer in interview state dict

3. **Config and context.md generation** — After all phases complete, `InterviewOrchestrator.generate_config()` produces a ProjectConfig with populated fields. `generate_context()` asks the LLM to synthesize all answers into a narrative context.md string. Both are returned as a structured result (e.g. `InterviewResult` dataclass with `config: ProjectConfig` and `context: str`).

4. **Build SequenceMockLLM** — Either extend MockLLM with an optional `responses: list[str]` that cycles through in order, or create a thin wrapper. Each `.complete()` call returns the next response in sequence. This enables deterministic multi-turn testing.

5. **Write unit tests** in `tests/test_interview.py`:
   - Happy path: all phases answered clearly → valid config with all fields
   - Vague detection: "make it better" as goal triggers follow-up probe
   - Empty answer handling: empty string triggers probe
   - Max retries: after 2 vague attempts, orchestrator accepts and moves on
   - Config output: generated ProjectConfig has correct field values from answers
   - Context output: context.md string is non-empty and contains key terms from answers
   - Backward compatibility: ProjectConfig with new fields serializes/deserializes correctly

## Must-Haves

- [ ] ProjectConfig extended with `search_space`, `constraints`, `metric_priorities` — backward compatible
- [ ] InterviewOrchestrator uses LLMProtocol for question generation and follow-ups
- [ ] Vague-input detection flags short/generic/empty answers
- [ ] Follow-up probes generated via LLM when vague input detected
- [ ] InterviewResult contains populated ProjectConfig + context.md string
- [ ] SequenceMockLLM enables deterministic multi-turn test sequences
- [ ] All unit tests pass; all existing 381 tests still pass

## Verification

- `cd /Users/fran/Documents/dev/repos/personal/autoagent && .venv/bin/python -m pytest tests/test_interview.py -v` — all new tests pass
- `cd /Users/fran/Documents/dev/repos/personal/autoagent && .venv/bin/python -m pytest tests/test_state.py -v` — existing state tests pass with extended ProjectConfig
- `cd /Users/fran/Documents/dev/repos/personal/autoagent && .venv/bin/python -m pytest tests/ -q` — full suite passes

## Observability Impact

- Signals added: InterviewOrchestrator exposes `state` dict (phase → answer mapping) and `phase` attribute for inspecting interview progress
- How a future agent inspects this: read `orchestrator.state` after any turn to see collected answers; `InterviewResult` is a frozen dataclass with clear fields
- Failure state exposed: LLM failures during follow-up generation are caught and the phase moves forward with what it has; vague detection results are available in state

## Inputs

- `src/autoagent/state.py` — existing ProjectConfig to extend
- `src/autoagent/primitives.py` — LLMProtocol interface and MockLLM pattern
- D053 (extended config + context.md), D055 (input/print I/O), boundary map fields

## Expected Output

- `src/autoagent/interview.py` — InterviewOrchestrator, InterviewResult, vague-input detection logic
- `src/autoagent/state.py` — ProjectConfig with 3 new optional fields
- `tests/test_interview.py` — 7+ unit tests covering all interview behaviors
