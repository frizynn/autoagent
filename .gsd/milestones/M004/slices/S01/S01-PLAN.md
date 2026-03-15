# S01: Interview Orchestrator

**Goal:** `autoagent new` runs a multi-turn LLM-driven interview that challenges vague input, extracts a meaningful optimization spec, and writes a complete config + context file.
**Demo:** Run `autoagent new` with MockLLM sequences simulating vague → clarified user input. Output: valid `config.json` with extended fields and `context.md` in `.autoagent/`.

## Must-Haves

- InterviewOrchestrator uses LLMProtocol to generate probing questions from user answers
- Vague input detection — "make it better" or empty answers trigger follow-up probes, not acceptance
- Interview collects: goal, metrics, constraints, search space preferences, benchmark info, budget
- Extended ProjectConfig with optional fields: `search_space`, `constraints`, `metric_priorities`
- `context.md` written to `.autoagent/` with rich narrative context for the meta-agent
- `autoagent new` CLI subcommand that runs the interview and writes config
- Existing 381 tests still pass

## Proof Level

- This slice proves: contract + integration
- Real runtime required: no (MockLLM sequences)
- Human/UAT required: no (interview quality spot-check is non-gating per roadmap)

## Verification

- `python3 -m pytest tests/test_interview.py -v` — unit tests for InterviewOrchestrator (vague detection, multi-turn flow, config generation, context.md output)
- `python3 -m pytest tests/test_cli.py -v -k interview` — CLI integration test for `autoagent new`
- `python3 -m pytest tests/ -q` — all 381+ tests pass
- Diagnostic: `python3 -c "from autoagent.interview import InterviewOrchestrator; o = InterviewOrchestrator.__new__(InterviewOrchestrator); print(o.__class__.__name__)"` — class importable and has expected attributes
- Failure-path: `python3 -m pytest tests/test_interview.py -v -k 'vague or retry or empty'` — vague-input and failure-handling tests pass independently

## Observability / Diagnostics

- Runtime signals: InterviewOrchestrator tracks interview phase and collected answers as structured dict
- Inspection surfaces: interview state dict is inspectable between turns; `context.md` and `config.json` are human-readable artifacts
- Failure visibility: LLM call failures surface with the prompt that failed; vague-input detection exposes which answers were flagged
- Redaction constraints: none (no secrets in interview flow)

## Integration Closure

- Upstream surfaces consumed: `ProjectConfig` and `StateManager` from `autoagent.state`, `LLMProtocol` from `autoagent.primitives`
- New wiring introduced in this slice: `autoagent new` CLI subcommand → InterviewOrchestrator → StateManager.write_config() + context.md file write
- What remains before the milestone is truly usable end-to-end: S02 (benchmark generation when none provided), S03 (reporting + full assembly)

## Tasks

- [x] **T01: Build InterviewOrchestrator with vague-input detection and config generation** `est:2h`
  - Why: Core domain logic — the interview state machine that drives multi-turn conversation, detects vague answers, and produces structured output. This is where R007 lives.
  - Files: `src/autoagent/interview.py`, `src/autoagent/state.py`, `tests/test_interview.py`
  - Do: (1) Extend ProjectConfig with optional `search_space: list[str]`, `constraints: list[str]`, `metric_priorities: list[str]` fields — frozen dataclass, backward-compatible defaults. (2) Build InterviewOrchestrator class that takes an LLMProtocol and runs a multi-turn interview via injectable I/O callables (not raw input/print — testable). Interview phases: goal → metrics → constraints → search space → benchmark → budget → confirmation. LLM generates follow-up questions; vague-input detector flags short/generic answers for probing. (3) Output: populated ProjectConfig + context.md string. (4) Build SequenceMockLLM (or extend MockLLM) to support ordered response sequences for multi-turn testing. (5) Write unit tests covering: happy path through all phases, vague input triggers follow-ups, config output has all fields populated, context.md contains narrative summary, empty/missing answers handled gracefully.
  - Verify: `python3 -m pytest tests/test_interview.py -v` passes, all existing tests still pass
  - Done when: InterviewOrchestrator produces valid ProjectConfig + context.md from MockLLM conversation sequences, with vague-input probing proven by test

- [x] **T02: Wire `autoagent new` CLI command with end-to-end integration test** `est:1h`
  - Why: Connects the interview to the user-facing CLI and proves the full flow from command invocation to config files on disk. Closes R007 at integration level.
  - Files: `src/autoagent/cli.py`, `tests/test_cli.py`
  - Do: (1) Add `new` subcommand to argparse that instantiates InterviewOrchestrator with stdin/stdout I/O and a configurable LLMProtocol (MockLLM default for now). (2) `cmd_new` creates `.autoagent/` if needed (reuse StateManager.init_project or extend), runs interview, writes config.json via StateManager.write_config(), writes context.md to `.autoagent/context.md`. (3) Handle already-initialized project (prompt overwrite or error). (4) Integration test: simulate user input via monkeypatched stdin, verify config.json and context.md written correctly.
  - Verify: `python3 -m pytest tests/test_cli.py -v -k interview_or_new` passes, full test suite passes
  - Done when: `autoagent new` produces config.json + context.md in `.autoagent/` from simulated interview, proven by CLI integration test

## Files Likely Touched

- `src/autoagent/interview.py` (new — InterviewOrchestrator)
- `src/autoagent/state.py` (extend ProjectConfig)
- `src/autoagent/cli.py` (add `new` subcommand)
- `tests/test_interview.py` (new — unit tests)
- `tests/test_cli.py` (add integration tests)
