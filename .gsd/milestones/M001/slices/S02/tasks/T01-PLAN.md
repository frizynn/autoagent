---
estimated_steps: 5
estimated_files: 3
---

# T01: StateManager with atomic writes and lock protocol

**Slice:** S02 — CLI Scaffold & Disk State
**Milestone:** M001

## Description

Implement the disk state layer that all downstream slices depend on. `StateManager` owns the `.autoagent/` directory: reading/writing `state.json` and `config.json` atomically, managing a PID-based lock file for exclusive access, and initializing new projects. This is the data layer — no CLI here, just the API that CLI and loop will consume.

## Steps

1. Create `src/autoagent/state.py` with:
   - `ProjectState` frozen dataclass (version, current_iteration, best_iteration_id, total_cost_usd, phase, started_at, updated_at) with `asdict()` and `from_dict()` class method
   - `ProjectConfig` frozen dataclass (version, goal, benchmark dict, budget_usd, pipeline_path) with `asdict()` and `from_dict()`
   - `StateManager` class taking a `project_dir: Path` parameter:
     - `init_project(goal: str = "")` — creates `.autoagent/`, `config.json`, `state.json`, `archive/`, starter `pipeline.py`. Raises if `.autoagent/` already exists.
     - `read_state() -> ProjectState` — reads and deserializes state.json
     - `write_state(state: ProjectState)` — atomic write via `tempfile.NamedTemporaryFile` + `os.replace`
     - `read_config() -> ProjectConfig` — reads config.json
     - `write_config(config: ProjectConfig)` — atomic write
     - `acquire_lock()` — writes PID + timestamp to `state.lock`, checks for stale locks via `os.kill(pid, 0)`
     - `release_lock()` — removes `state.lock`
     - `is_initialized() -> bool` — checks `.autoagent/` exists with required files
2. Create starter pipeline.py content as a string constant — must define `run(input_data)` that returns a dict, compatible with `PipelineRunner`'s compile()+exec() loading
3. Write `tests/test_state.py` with tests for:
   - `init_project` creates all expected files/dirs
   - `init_project` raises on existing `.autoagent/`
   - State round-trip: write → read returns equal data
   - Config round-trip: write → read returns equal data
   - Atomic write: verify temp file approach (mock crash scenario)
   - Lock acquire/release cycle
   - Stale lock detection: write a lock with dead PID, verify acquire succeeds
   - `is_initialized()` returns False for empty dir, True after init

## Must-Haves

- [ ] Atomic writes via temp + `os.replace` for both state.json and config.json
- [ ] PID-based lock file with stale detection (`os.kill(pid, 0)`)
- [ ] `init_project()` creates complete `.autoagent/` structure
- [ ] `init_project()` refuses to overwrite existing project
- [ ] Starter `pipeline.py` defines `run(input_data)` loadable by PipelineRunner
- [ ] Zero runtime dependencies — stdlib only

## Verification

- `pytest tests/test_state.py -v` — all tests pass
- `python -c "from autoagent.state import StateManager"` — importable

## Observability Impact

- Signals added: `state.json` contains `phase` and `updated_at` for loop state diagnosis; `state.lock` contains PID + timestamp for crash detection
- How a future agent inspects this: read `.autoagent/state.json` directly or via `StateManager.read_state()`
- Failure state exposed: stale lock file with dead PID indicates prior crash; `phase` field shows where loop stopped

## Inputs

- `src/autoagent/types.py` — frozen dataclass + `asdict()` pattern to follow
- S02-RESEARCH.md — proposed schemas for state.json and config.json
- S01 pipeline loading contract — starter pipeline.py must have a module-level `run(input_data)` function

## Expected Output

- `src/autoagent/state.py` — StateManager class with full read/write/lock/init API
- `tests/test_state.py` — comprehensive unit tests for state layer
