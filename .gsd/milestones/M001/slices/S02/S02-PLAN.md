# S02: CLI Scaffold & Disk State

**Goal:** `autoagent init` creates `.autoagent/` project structure with state files; `autoagent run` validates state and stubs the loop; `autoagent status` reads and displays current state from disk.
**Demo:** Run `autoagent init` in a temp directory → verify `.autoagent/` structure on disk. Run `autoagent status` → see formatted state output. Run `autoagent init` again → refused (already initialized). All via installed console script entry point.

## Must-Haves

- `StateManager` with atomic writes (write-to-temp + `os.replace`) and PID-based lock file with stale detection
- `autoagent init` creates `.autoagent/` with `config.json`, `state.json`, `archive/`, and starter `pipeline.py`
- `autoagent init` refuses to overwrite existing `.autoagent/` directory
- `autoagent status` reads and displays state from disk (iteration, phase, cost, best iteration)
- `autoagent run` validates initialized state and exits with "not yet implemented" (wired in S05)
- Console script entry point registered in `pyproject.toml`
- Starter `pipeline.py` is loadable by S01's `PipelineRunner`
- Zero runtime dependencies — argparse + json + pathlib only

## Proof Level

- This slice proves: contract
- Real runtime required: no (filesystem operations only)
- Human/UAT required: no

## Verification

- `pytest tests/test_state.py -v` — StateManager unit tests: atomic writes, lock acquire/release, stale lock detection, state round-trip
- `pytest tests/test_cli.py -v` — CLI integration tests: init creates correct structure, init refuses re-init, status displays state, run validates state
- `pip install -e . && autoagent --help` — entry point works

## Observability / Diagnostics

- Runtime signals: StateManager writes `updated_at` timestamp on every state mutation; lock file contains PID + timestamp for stale detection
- Inspection surfaces: `autoagent status` is the primary inspection command; `.autoagent/state.json` is human-readable JSON
- Failure visibility: Lock file with PID enables crash detection; `state.json` contains `phase` field for diagnosing where the loop stopped
- Redaction constraints: none (no secrets in state)

## Integration Closure

- Upstream surfaces consumed: `src/autoagent/types.py` (dataclass + asdict pattern), `PipelineRunner` contract (starter pipeline.py must be loadable)
- New wiring introduced in this slice: `[project.scripts]` entry point, `StateManager` as disk state API for all downstream slices
- What remains before the milestone is truly usable end-to-end: S03 (evaluation), S04 (archive), S05 (loop wiring into `run` command), S06 (budget + recovery)

## Tasks

- [x] **T01: StateManager with atomic writes and lock protocol** `est:45m` ✅
  - Why: All downstream slices (S04, S05, S06) depend on `StateManager` for disk state. Lock files and atomic writes are the foundation for S06 crash recovery. Must exist before CLI can use it.
  - Files: `src/autoagent/state.py`, `src/autoagent/config.py`, `tests/test_state.py`
  - Do: Implement `ProjectState` and `ProjectConfig` as dataclasses with `.asdict()`/`.from_dict()` following S01's types.py pattern. Implement `StateManager` with: find/validate `.autoagent/` directory, read/write `state.json` with atomic temp+rename, read/write `config.json`, PID-based lock file (acquire/release/stale detection via `os.kill(pid, 0)`), `init_project()` that creates directory structure. Starter `pipeline.py` content must define a `run(input_data)` function loadable by `PipelineRunner`.
  - Verify: `pytest tests/test_state.py -v` — all tests pass
  - Done when: StateManager round-trips state and config to disk atomically, lock protocol works including stale detection, init creates correct directory structure

- [x] **T02: CLI commands and console script entry point** `est:45m` ✅
  - Why: Delivers R006 — the user-facing `autoagent` command with `init`, `run`, `status` subcommands. Wires StateManager into real CLI handlers.
  - Files: `src/autoagent/cli.py`, `tests/test_cli.py`, `pyproject.toml`
  - Do: Build argparse CLI with subcommands: `init` (calls `StateManager.init_project()`, prints success/error), `status` (reads state, formats and prints iteration/phase/cost/best), `run` (validates initialized state, prints "not yet implemented — wired in S05"). Add `[project.scripts] autoagent = "autoagent.cli:main"` to pyproject.toml. CLI should use structured error handling — no raw tracebacks to user. Add `--project-dir` flag (default: cwd) for all commands.
  - Verify: `pytest tests/test_cli.py -v` — all tests pass. `pip install -e . && autoagent --help` shows subcommands.
  - Done when: `autoagent init` creates correct `.autoagent/` structure, `autoagent status` displays formatted state, `autoagent run` validates and stubs, entry point is installed and working

## Files Likely Touched

- `src/autoagent/state.py`
- `src/autoagent/config.py`
- `src/autoagent/cli.py`
- `tests/test_state.py`
- `tests/test_cli.py`
- `pyproject.toml`
