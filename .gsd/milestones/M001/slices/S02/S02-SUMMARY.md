---
id: S02
parent: M001
milestone: M001
provides:
  - StateManager with atomic writes, PID-based lock protocol, and project initialization
  - ProjectState and ProjectConfig frozen dataclasses for disk-persisted state
  - autoagent CLI (init/run/status) via argparse with console script entry point
  - Starter pipeline.py template loadable by PipelineRunner
requires: []
affects:
  - S05
  - S06
key_files:
  - src/autoagent/state.py
  - src/autoagent/cli.py
  - tests/test_state.py
  - tests/test_cli.py
  - pyproject.toml
key_decisions:
  - D015: JSON config instead of YAML — stdlib-only, zero dependencies
  - D016: argparse instead of click/typer — zero runtime dependencies
  - D017: Standard Python CLI, not PI SDK — PI is Node.js, no Python SDK exists
  - Combined state types and manager into single state.py instead of separate config.py
patterns_established:
  - Frozen dataclasses with asdict()/from_dict() for JSON-serializable state types
  - Atomic writes via NamedTemporaryFile + os.replace + fsync for all state mutations
  - PID-based lock files with stale detection via os.kill(pid, 0)
  - CLI handlers return int exit code; main() calls sys.exit() — keeps handlers testable
  - Errors print to stderr with "Error:" prefix, exit code 1; no raw tracebacks
observability_surfaces:
  - autoagent status — primary inspection command (phase, iteration, cost, best, goal)
  - .autoagent/state.json — human-readable JSON with phase and updated_at
  - .autoagent/state.lock — PID + timestamp for crash detection
  - Exit codes: 0 success, 1 error
drill_down_paths:
  - .gsd/milestones/M001/slices/S02/tasks/T01-SUMMARY.md
  - .gsd/milestones/M001/slices/S02/tasks/T02-SUMMARY.md
duration: 30m
verification_result: passed
completed_at: 2026-03-14
---

# S02: CLI Scaffold & Disk State

**Disk state layer with atomic writes and PID-based locking, plus `autoagent` CLI with init/run/status subcommands as an installable console script.**

## What Happened

Built the state management layer in `src/autoagent/state.py`: `ProjectState` and `ProjectConfig` frozen dataclasses with `asdict()`/`from_dict()` (unknown-key tolerant), `StateManager` with atomic JSON writes (NamedTemporaryFile + os.replace + fsync), PID-based lock file protocol with stale detection, and `init_project()` that creates the full `.autoagent/` directory structure (state.json, config.json, archive/, pipeline.py).

Built the CLI in `src/autoagent/cli.py`: argparse with init/run/status subcommands, `--project-dir` flag on all commands, structured error handling (no raw tracebacks). Registered `[project.scripts] autoagent = "autoagent.cli:main"` in pyproject.toml.

The starter pipeline.py defines `run(input_data, primitives=None)` matching PipelineRunner's actual call signature from S01.

## Verification

- `pytest tests/test_state.py -v` — 23/23 passed (atomic writes, lock protocol, init structure, round-trips, stale detection, starter pipeline loadability)
- `pytest tests/test_cli.py -v` — 10/10 passed (init creates structure, init refuses re-init, status after init, status uninitialized, run after init, run uninitialized, help, --project-dir, main direct calls)
- `pip install -e . && autoagent --help` — entry point shows init/status/run subcommands
- End-to-end: `autoagent init && autoagent status` in /tmp — correct output, re-init refused with exit code 1

## Requirements Advanced

- R006 (PI-Based CLI) — Delivered `autoagent init`, `autoagent status`, `autoagent run` as working CLI commands. Reinterpreted as standard Python CLI since PI is Node.js (D017).
- R005 (Crash-Recoverable Disk State) — Foundation laid: atomic writes, PID-based lock files, stale detection. Full crash recovery wired in S06.

## Requirements Validated

None — R006 is partially proven (commands work, but the meta-agent integration via PI SDK is deferred to M004/S05). Full validation requires S05/S06 wiring.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

- R006 — "PI-Based CLI" reinterpreted as standard Python CLI (D017). PI is a Node.js agent harness with no Python SDK. The GSD-2-style command UX is preserved; the PI SDK integration aspect moves to M004/S05 if needed.

## Deviations

- No separate `config.py` — combined into `state.py` since ProjectConfig is a small dataclass tightly coupled with StateManager.
- Config format is JSON, not YAML (D015) — boundary map said `config.yaml` but YAML requires pyyaml dependency, violating zero-dependency constraint.
- Starter pipeline signature is `run(input_data, primitives=None)` with two args — matches PipelineRunner's actual call convention discovered in S01.

## Known Limitations

- `autoagent run` is a stub ("not yet implemented") — wired in S05 when the optimization loop exists.
- No config editing commands — config.json is manually editable or programmatically set by downstream slices.
- Lock protocol uses os.kill(pid, 0) which only detects dead PIDs on the same host — sufficient for single-machine use.

## Follow-ups

None — all known work is already planned in S05 (loop wiring) and S06 (budget + recovery).

## Files Created/Modified

- `src/autoagent/state.py` — StateManager, ProjectState, ProjectConfig, STARTER_PIPELINE, LockError
- `src/autoagent/cli.py` — CLI with init/run/status commands, argparse setup, structured error handling
- `tests/test_state.py` — 23 unit tests for state layer
- `tests/test_cli.py` — 10 integration tests for CLI commands
- `pyproject.toml` — added `[project.scripts]` entry point

## Forward Intelligence

### What the next slice should know
- `StateManager` is the sole API for `.autoagent/` disk state — import from `autoagent.state`
- `ProjectState` fields: version, current_iteration, best_iteration_id, total_cost_usd, phase, started_at, updated_at
- `ProjectConfig` fields: version, goal, benchmark (dict with dataset_path, scoring_function), budget_usd, pipeline_path
- Lock must be acquired before writing state in concurrent scenarios (S05 loop, S06 recovery)

### What's fragile
- Starter pipeline.py template is a string constant in state.py — if PipelineRunner's calling convention changes, update STARTER_PIPELINE

### Authoritative diagnostics
- `autoagent status` for quick project health check
- `.autoagent/state.json` phase field: "initialized" means never run, will change to "running"/"paused"/"completed" in S05/S06
- `.autoagent/state.lock` with dead PID = prior crash

### What assumptions changed
- Assumed PI SDK would provide CLI framework — PI is Node.js only, used argparse instead (D017)
- Assumed config.yaml — used config.json to stay zero-dependency (D015)
