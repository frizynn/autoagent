# S02: CLI Scaffold & Disk State — Research

**Date:** 2026-03-14

## Summary

S02 needs to deliver: (1) a Python CLI with `autoagent init`, `autoagent run`, `autoagent status` commands, (2) a `StateManager` that reads/writes `.autoagent/state.json` with lock file support, and (3) the `.autoagent/` directory convention that all downstream slices depend on.

The biggest finding is that PI is a Node.js agent harness (`@glittercowboy/gsd`) — there is no Python PI SDK. R006 says "PI-based CLI" but AutoAgent is a pure Python project with zero runtime dependencies. The meta-agent will later invoke LLMs directly (S05), not through PI's agent session model. The CLI itself should be a standard Python CLI registered via `[project.scripts]` in pyproject.toml.

The project currently has zero runtime dependencies and only stdlib + dev tools in the venv. This is a strong constraint worth preserving — argparse is sufficient for `init`/`run`/`status` without adding click or typer.

## Recommendation

**Build a stdlib-only Python CLI using argparse with subcommands.** Register `autoagent` as a console script entry point. Use JSON for both state and config (stdlib `json` module — zero deps, read/write, human-readable). The boundary map says `config.yaml` but YAML requires adding pyyaml; TOML has read-only stdlib support (tomllib) but needs tomli-w for writing. JSON keeps the zero-dependency story intact and is fully round-trippable.

State management should use a simple file-lock protocol: `state.lock` with PID + timestamp, stale lock detection (check if PID is alive), and atomic writes via write-to-temp + rename. This gives S06 crash recovery a solid foundation.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| CLI argument parsing | `argparse` (stdlib) | Zero deps, subcommand support, good enough for 3 commands |
| JSON serialization | `json` (stdlib) | Config and state are simple dicts — no need for schema libs |
| Atomic file writes | `tempfile.NamedTemporaryFile` + `os.replace` | OS-level atomicity on rename, prevents partial writes on crash |
| Lock files | `fcntl.flock` or PID-based lockfile | fcntl is Unix-only but sufficient; PID-based is more portable and supports stale detection |
| Path handling | `pathlib.Path` (stdlib) | Already used throughout S01 code |

## Existing Code and Patterns

- `src/autoagent/types.py` — Frozen dataclasses with `.asdict()` serialization. State types should follow this pattern (dataclass + asdict for JSON).
- `src/autoagent/pipeline.py` — `PipelineRunner` never raises, returns structured error results. CLI should follow: structured errors, no raw exceptions to the user.
- `src/autoagent/primitives.py` — Clean protocol-based design. State types should be similarly well-typed.
- `pyproject.toml` — `dependencies = []`, no `[project.scripts]`. Need to add entry point.
- `.venv/` — Python 3.11.15, `tomllib` available but read-only. `json` module preferred for read/write config.
- S01 established compile()+exec() for module loading — `init` should create a starter `pipeline.py` that's loadable by `PipelineRunner`.

## Constraints

- **Zero runtime dependencies** — project has `dependencies = []` in pyproject.toml. Adding click/typer/pyyaml would break this. Argparse + json are stdlib.
- **Python 3.11+** — can use tomllib for reading TOML, but not writing. `match` statements available.
- **PI is Node.js** — no Python PI SDK exists. R006 ("PI-based CLI") must be reinterpreted as "Python CLI with GSD-2-style commands." The meta-agent (S05) will invoke LLMs directly, not through PI.
- **S05 consumes StateManager and cli.py** — the `run` command handler must be structured so S05 can wire in the optimization loop without rewriting it.
- **S06 consumes state protocol** — lock files and state.json must support crash recovery: detect stale locks, reconstruct state from archive on disk.
- **Boundary map specifies config.yaml** — but YAML needs a dependency. Decision needed: deviate to JSON (zero deps) or add pyyaml. Recommending JSON.
- **All state on disk** — D002 decision. No databases, no in-memory-only state.
- **Directory of JSON files** — D003 decision for archive format. `.autoagent/archive/` must be created by `init`.

## Common Pitfalls

- **Non-atomic writes to state.json** — If the process is killed mid-write, state.json is corrupted. Must use write-to-temp + `os.replace()` for atomicity. This is the #1 crash recovery concern.
- **Lock file stale detection** — A simple lockfile without PID checking becomes a permanent block after crash. Store PID in lock, check `os.kill(pid, 0)` on acquisition.
- **Config format lock-in** — Choosing YAML now means adding pyyaml. If we later want TOML for pyproject.toml alignment, that's a second format. JSON is universal and zero-dep.
- **Hardcoded .autoagent/ path** — The project root detection must be explicit (cwd or flag), not magic directory traversal. Keep it simple: `.autoagent/` in cwd, with `--project-dir` override.
- **init overwriting existing state** — `autoagent init` in a directory that already has `.autoagent/` should refuse or prompt, not silently overwrite.
- **run command blocking** — The `run` command in S02 is a stub (loop wired in S05). Make it clear it's a placeholder that validates state and prints "not yet implemented" rather than silently doing nothing.

## Open Risks

- **R006 reinterpretation** — The requirement says "PI-based CLI" but PI has no Python SDK. We're building a standard Python CLI instead. This may need explicit acknowledgment as a deviation or re-scoping of R006.
- **Config schema evolution** — The config format will grow as S05/S06 add fields (goal, budget, provider). Starting with a minimal schema that's extensible is important. Avoid over-specifying now.
- **Lock file portability** — `fcntl.flock` is Unix-only. PID-based lockfile with `os.kill(pid, 0)` works on macOS/Linux but not Windows. Acceptable for now (development tool, not Windows target).
- **Starter pipeline.py contents** — `init` creates a starter pipeline.py that must be valid for `PipelineRunner`. Need to decide: minimal hello-world, or toy RAG similar to test fixture?

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Python CLI | `0xdarkmatter/claude-mods@python-cli-patterns` (29 installs) | available — not needed, argparse is sufficient |
| Python CLI | `wdm0006/python-skills@building-python-clis` (19 installs) | available — not needed |

No skills are needed for this slice — it's stdlib Python (argparse, json, pathlib, dataclasses).

## Sources

- PI is a Node.js package `@glittercowboy/gsd` v0.57.1 (source: `/Users/fran/.hermes/node/lib/node_modules/gsd-pi/pkg/package.json`)
- Python 3.11 tomllib is read-only (source: stdlib docs — `tomllib` has no write API)
- S01 established compile()+exec() pattern for pipeline loading (source: S01-SUMMARY.md, D014)
- D002 mandates disk-only state, D003 mandates directory-of-files archive (source: DECISIONS.md)

## .autoagent/ Directory Layout (Proposed)

```
.autoagent/
  config.json          # project config: goal, benchmark, budget, provider settings
  state.json           # current loop state: iteration, best_id, total_cost, phase
  state.lock           # PID-based lock file for exclusive access
  archive/             # iteration entries (S04 populates)
  pipeline.py          # the mutable pipeline file (created by init, mutated by meta-agent)
```

## state.json Schema (Proposed)

```json
{
  "version": 1,
  "current_iteration": 0,
  "best_iteration_id": null,
  "total_cost_usd": 0.0,
  "phase": "initialized",
  "started_at": null,
  "updated_at": "2026-03-14T12:00:00Z"
}
```

## config.json Schema (Proposed)

```json
{
  "version": 1,
  "goal": "",
  "benchmark": {
    "dataset_path": "",
    "scoring_function": ""
  },
  "budget_usd": null,
  "pipeline_path": "pipeline.py"
}
```

## Requirements Targeted

- **R006 (PI-Based CLI)** — Primary owner. Reinterpreted as Python CLI with GSD-2-style subcommands since PI has no Python SDK.
- **R005 (Crash-Recoverable Disk State)** — Supporting. StateManager with atomic writes and lock files provides the foundation; S06 adds full recovery logic.
