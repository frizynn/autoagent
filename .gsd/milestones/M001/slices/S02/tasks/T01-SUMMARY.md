---
id: T01
parent: S02
milestone: M001
provides:
  - StateManager class with full read/write/lock/init API
  - ProjectState and ProjectConfig frozen dataclasses
  - Starter pipeline.py template loadable by PipelineRunner
key_files:
  - src/autoagent/state.py
  - tests/test_state.py
key_decisions:
  - Combined state types and manager into single state.py (no separate config.py) — keeps the state layer cohesive
  - Starter pipeline accepts optional primitives arg (run(input_data, primitives=None)) matching PipelineRunner's actual call signature
patterns_established:
  - Frozen dataclasses with asdict()/from_dict() for JSON-serializable state types
  - Atomic writes via NamedTemporaryFile + os.replace + fsync for all state mutations
  - PID-based lock files with stale detection via os.kill(pid, 0)
observability_surfaces:
  - state.json contains phase and updated_at for loop state diagnosis
  - state.lock contains PID + timestamp for crash detection
  - Stale lock with dead PID indicates prior crash
duration: 15m
verification_result: passed
completed_at: 2026-03-14
blocker_discovered: false
---

# T01: StateManager with atomic writes and lock protocol

**Implemented the disk state layer with atomic JSON writes, PID-based locking, and project initialization for `.autoagent/`.**

## What Happened

Built `src/autoagent/state.py` containing:
- `ProjectState` and `ProjectConfig` as frozen dataclasses following the `types.py` pattern (asdict + from_dict with unknown-key tolerance)
- `StateManager` class with init_project, read/write state+config (atomic via temp+os.replace+fsync), acquire/release lock with stale PID detection, is_initialized query
- `STARTER_PIPELINE` constant defining a `run(input_data, primitives=None)` function compatible with PipelineRunner's compile()+exec() loading
- `LockError` exception for lock acquisition failures

Wrote 23 tests covering all must-haves: init creates structure, init refuses re-init, state/config round-trips, atomic write verification (mock os.replace), crash simulation (os.replace fails → original intact + no temp residue), lock acquire/release/stale/corrupt, is_initialized edge cases, and starter pipeline loadability.

## Verification

- `pytest tests/test_state.py -v` — 23/23 passed
- `python -c "from autoagent.state import StateManager"` — importable

Slice-level checks:
- ✅ `pytest tests/test_state.py -v` — passes
- ⬜ `pytest tests/test_cli.py -v` — not yet created (T02)
- ⬜ `pip install -e . && autoagent --help` — entry point not yet registered (T02)

## Diagnostics

- Read `.autoagent/state.json` for phase/updated_at to diagnose loop state
- Read `.autoagent/state.lock` for PID/timestamp to detect crashes
- `StateManager.is_initialized()` for quick health check
- Stale lock (dead PID) is auto-detected and overwritten on next acquire

## Deviations

- Task plan listed `src/autoagent/config.py` as a separate file — combined into `state.py` since ProjectConfig is a small dataclass tightly coupled with StateManager. Keeps the state layer in one module.
- Starter pipeline signature is `run(input_data, primitives=None)` with two args (not one). PipelineRunner passes both input_data and primitives context — the starter must accept both to avoid TypeError at runtime.

## Known Issues

None.

## Files Created/Modified

- `src/autoagent/state.py` — StateManager, ProjectState, ProjectConfig, STARTER_PIPELINE, LockError
- `tests/test_state.py` — 23 unit tests for state layer
