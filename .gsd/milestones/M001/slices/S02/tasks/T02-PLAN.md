---
estimated_steps: 4
estimated_files: 3
---

# T02: CLI commands and console script entry point

**Slice:** S02 — CLI Scaffold & Disk State
**Milestone:** M001

## Description

Build the `autoagent` CLI with `init`, `run`, and `status` subcommands using argparse. Wire each command to `StateManager` from T01. Register the console script entry point in pyproject.toml so `autoagent` is available after `pip install -e .`. This delivers R006.

## Steps

1. Create `src/autoagent/cli.py` with:
   - `main()` function as entry point — sets up argparse with subcommands
   - `--project-dir` top-level flag (default: current working directory)
   - `cmd_init(args)` — creates StateManager, calls `init_project()`, prints success message with created path. On error (already exists), prints error and exits with code 1.
   - `cmd_status(args)` — reads state and config via StateManager, prints formatted output: phase, current iteration, best iteration, total cost, last updated. If not initialized, prints error and exits with code 1.
   - `cmd_run(args)` — validates project is initialized, prints "Optimization loop not yet implemented — will be wired in S05." Exits with code 0. This is an intentional stub.
   - All commands catch `StateManager` exceptions and print user-friendly messages — no raw tracebacks.
2. Add `[project.scripts]` section to pyproject.toml: `autoagent = "autoagent.cli:main"`
3. Write `tests/test_cli.py` with integration tests using `subprocess.run` or direct function calls:
   - `autoagent init` in a temp dir creates `.autoagent/` with all expected contents
   - `autoagent init` in already-initialized dir exits with code 1 and error message
   - `autoagent status` after init shows phase "initialized" and iteration 0
   - `autoagent status` in uninitialized dir exits with code 1
   - `autoagent run` after init prints stub message and exits 0
   - `autoagent run` in uninitialized dir exits with code 1
   - `autoagent --help` shows all subcommands
4. Run `pip install -e .` and verify `autoagent --help` works from shell

## Must-Haves

- [ ] `autoagent init` creates correct `.autoagent/` structure via StateManager
- [ ] `autoagent init` refuses re-initialization with clear error
- [ ] `autoagent status` displays formatted state from disk
- [ ] `autoagent run` validates state and prints stub message
- [ ] `--project-dir` flag works for all commands
- [ ] Console script entry point registered and installable
- [ ] No raw tracebacks — structured error output

## Verification

- `pytest tests/test_cli.py -v` — all tests pass
- `pip install -e . && autoagent --help` — shows init, run, status subcommands
- `cd /tmp && mkdir aa-test && cd aa-test && autoagent init && autoagent status` — works end-to-end

## Inputs

- `src/autoagent/state.py` — StateManager from T01
- `tests/test_state.py` — T01 tests pass (state layer is solid)

## Expected Output

- `src/autoagent/cli.py` — CLI with init/run/status commands
- `tests/test_cli.py` — integration tests for all CLI paths
- `pyproject.toml` — updated with `[project.scripts]` entry point

## Observability Impact

- **`autoagent status`** becomes the primary inspection surface — shows phase, iteration, cost, and last-updated timestamp from disk state
- **Exit codes**: all commands exit 0 on success, 1 on error (uninitialized project, re-init attempt). Enables scripted health checks.
- **Structured error output**: user-facing messages to stderr, no raw tracebacks. A future agent can parse exit code + stderr to diagnose failures.
- **Inspection**: `autoagent status --project-dir <path>` can probe any project directory without cd'ing into it
