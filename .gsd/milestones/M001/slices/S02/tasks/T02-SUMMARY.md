---
id: T02
parent: S02
milestone: M001
provides:
  - autoagent CLI with init/run/status subcommands via argparse
  - Console script entry point (autoagent = autoagent.cli:main)
key_files:
  - src/autoagent/cli.py
  - tests/test_cli.py
  - pyproject.toml
key_decisions:
  - Used python -m autoagent.cli for subprocess tests (sys.executable -m) to avoid PATH dependency on installed console script
  - cmd_* functions return int exit code; main() calls sys.exit() — keeps handlers testable without catching SystemExit
patterns_established:
  - CLI handlers return int exit code, main() dispatches and calls sys.exit()
  - Errors print to stderr with "Error:" prefix, exit code 1; no raw tracebacks
observability_surfaces:
  - autoagent status — primary inspection command showing phase, iteration, cost, last-updated
  - Exit codes: 0 success, 1 error (uninitialized, re-init, read failure)
  - Structured error messages to stderr for scripted health checks
duration: 15m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T02: CLI commands and console script entry point

**Built the `autoagent` CLI with init/run/status subcommands wired to StateManager, registered as installable console script.**

## What Happened

Created `src/autoagent/cli.py` with argparse-based CLI:
- `cmd_init` — creates `.autoagent/` via StateManager, handles FileExistsError for re-init
- `cmd_status` — reads state and config, prints formatted output (phase, iteration, cost, best, goal)
- `cmd_run` — validates initialized state, prints stub message (wired in S05)
- `--project-dir` flag on all commands (default: cwd)
- Top-level exception handler catches LockError and unexpected exceptions

Added `[project.scripts]` to pyproject.toml: `autoagent = "autoagent.cli:main"`.

Wrote 10 integration tests covering all commands, error paths, help output, --project-dir flag, and direct main() calls.

## Verification

- `pytest tests/test_cli.py -v` — 10/10 passed
- `pytest tests/test_state.py tests/test_cli.py -v` — 33/33 passed (full slice suite)
- `pip install -e . && autoagent --help` — shows init, status, run subcommands ✓
- End-to-end in /tmp: `autoagent init && autoagent status` — works, shows phase "initialized", iteration 0 ✓

### Slice-level verification status
- ✅ `pytest tests/test_state.py -v` — 23 passed
- ✅ `pytest tests/test_cli.py -v` — 10 passed
- ✅ `pip install -e . && autoagent --help` — entry point works

## Diagnostics

- `autoagent status --project-dir <path>` to inspect any project
- Exit code 1 + stderr message on all error paths (uninitialized, re-init, read failure)
- `.autoagent/state.json` is human-readable JSON for direct inspection

## Deviations

- Added `if __name__ == "__main__"` guard to cli.py for `python -m autoagent.cli` support — not in plan but required for subprocess-based tests

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/cli.py` — CLI with init/run/status commands, argparse setup, structured error handling
- `tests/test_cli.py` — 10 integration tests covering all commands and error paths
- `pyproject.toml` — added `[project.scripts]` entry point
- `.gsd/milestones/M001/slices/S02/tasks/T02-PLAN.md` — added Observability Impact section (pre-flight fix)
