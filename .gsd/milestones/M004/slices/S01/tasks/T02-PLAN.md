---
estimated_steps: 4
estimated_files: 2
---

# T02: Wire `autoagent new` CLI command with end-to-end integration test

**Slice:** S01 — Interview Orchestrator
**Milestone:** M004

## Description

Connect the InterviewOrchestrator to the CLI as the `autoagent new` subcommand. The command initializes the project directory if needed, runs the interview, writes `config.json` via StateManager, and writes `context.md` to `.autoagent/`. Integration test proves the full flow with simulated user input and MockLLM.

## Steps

1. **Add `new` subcommand to CLI** — Register `new` in `build_parser()`. `cmd_new` creates an InterviewOrchestrator with stdin/stdout I/O functions and a MockLLM (placeholder — real LLM provider wiring is a future concern). If `.autoagent/` doesn't exist, run `StateManager.init_project()` first. If it does exist and config already has a goal, print a warning and ask for confirmation via input.

2. **Wire interview output to disk** — After interview completes, write `result.config` via `StateManager.write_config()`. Write `result.context` to `sm.aa_dir / "context.md"`. Print a summary of what was configured (goal, metric count, constraint count).

3. **Handle edge cases** — Non-interactive terminal detection (if useful), keyboard interrupt during interview (clean exit with partial state message), LLM provider not configured (clear error message).

4. **Write CLI integration tests** — Add tests to `tests/test_cli.py`:
   - `test_cmd_new_creates_config`: monkeypatch stdin with pre-canned answers, verify config.json written with expected fields
   - `test_cmd_new_writes_context_md`: verify context.md file exists and is non-empty
   - `test_cmd_new_already_initialized`: verify behavior when project already exists
   - Use SequenceMockLLM from T01 for deterministic LLM responses

## Must-Haves

- [ ] `autoagent new` subcommand registered and dispatched
- [ ] Interview runs and writes config.json + context.md to `.autoagent/`
- [ ] Already-initialized project handled gracefully
- [ ] CLI integration test proves full flow with simulated input
- [ ] All 381+ tests pass

## Verification

- `cd /Users/fran/Documents/dev/repos/personal/autoagent && .venv/bin/python -m pytest tests/test_cli.py -v -k "new"` — new CLI tests pass
- `cd /Users/fran/Documents/dev/repos/personal/autoagent && .venv/bin/python -m pytest tests/ -q` — full suite passes

## Inputs

- `src/autoagent/interview.py` — InterviewOrchestrator and InterviewResult from T01
- `src/autoagent/cli.py` — existing CLI structure with init/run/status commands
- `src/autoagent/state.py` — StateManager for project directory and config persistence

## Expected Output

- `src/autoagent/cli.py` — extended with `cmd_new` and `new` subcommand parser
- `tests/test_cli.py` — 3+ new integration tests for `autoagent new`

## Observability Impact

- **New CLI surface:** `autoagent new` prints a summary line after interview completion showing goal, metric count, and constraint count — visible in stdout.
- **Disk artifacts:** `config.json` and `context.md` written to `.autoagent/` are human-readable inspection surfaces for verifying interview output.
- **Failure visibility:** KeyboardInterrupt during interview prints partial-state message to stderr. Already-initialized project with existing goal prints a warning and prompts for confirmation.
- **Future agent inspection:** After `autoagent new` completes, read `.autoagent/config.json` to verify structured config and `.autoagent/context.md` for the narrative. Non-zero exit code signals failure.
