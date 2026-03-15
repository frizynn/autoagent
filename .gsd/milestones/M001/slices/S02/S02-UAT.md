# S02: CLI Scaffold & Disk State — UAT

**Milestone:** M001
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: All deliverables are filesystem operations and CLI output — no runtime services, no network, no UI

## Preconditions

- Python 3.11+ available
- `pip install -e .` completed successfully in the repo root
- Clean temp directory for testing (no pre-existing `.autoagent/`)

## Smoke Test

Run `autoagent --help` — should print usage with init, status, run subcommands and exit 0.

## Test Cases

### 1. Init creates correct directory structure

1. `cd $(mktemp -d)`
2. `autoagent init`
3. **Expected:** Prints "Initialized autoagent project at <path>/.autoagent", exit 0
4. `ls -la .autoagent/`
5. **Expected:** Contains `state.json`, `config.json`, `pipeline.py`, `archive/` directory
6. `cat .autoagent/state.json`
7. **Expected:** Valid JSON with `version: 1`, `current_iteration: 0`, `phase: "initialized"`, `total_cost_usd: 0.0`, `updated_at` is ISO timestamp
8. `cat .autoagent/config.json`
9. **Expected:** Valid JSON with `version: 1`, `goal: ""`, `benchmark` object, `pipeline_path: "pipeline.py"`

### 2. Init refuses re-initialization

1. In the same directory from test 1
2. `autoagent init`
3. **Expected:** Prints "Error: project already initialized at <path>/.autoagent" to stderr, exit 1
4. `cat .autoagent/state.json`
5. **Expected:** Original state.json unchanged (same updated_at timestamp)

### 3. Status displays formatted state

1. In an initialized project directory
2. `autoagent status`
3. **Expected:** Output includes all of: "Phase: initialized", "Current iteration: 0", "Best iteration: —", "Total cost (USD): $0.0000", "Last updated:" with a timestamp, "Goal: (not set)"
4. Exit code 0

### 4. Status fails on uninitialized directory

1. `cd $(mktemp -d)`
2. `autoagent status`
3. **Expected:** Prints "Error:" message about uninitialized project to stderr, exit 1

### 5. Run validates initialization

1. In an initialized project directory
2. `autoagent run`
3. **Expected:** Prints message about not yet implemented / wired in S05, exit 0

### 6. Run fails on uninitialized directory

1. `cd $(mktemp -d)`
2. `autoagent run`
3. **Expected:** Prints "Error:" message about uninitialized project to stderr, exit 1

### 7. --project-dir flag works

1. `cd $(mktemp -d)`
2. `autoagent init --project-dir .`
3. `autoagent status --project-dir .`
4. **Expected:** Init succeeds, status shows correct output — both using explicit --project-dir instead of relying on cwd

### 8. Starter pipeline.py is valid Python

1. In an initialized project directory
2. `python3 -c "exec(open('.autoagent/pipeline.py').read()); result = run({'query': 'test'}); print(result)"`
3. **Expected:** Returns a dict with an 'answer' key, no import errors, no syntax errors

## Edge Cases

### Re-init after partial directory

1. `cd $(mktemp -d)`
2. `mkdir .autoagent`
3. `echo '{}' > .autoagent/state.json`
4. `autoagent init`
5. **Expected:** Refuses to init (detects existing .autoagent/), exit 1

### Status with corrupted state.json

1. In an initialized project
2. `echo 'not json' > .autoagent/state.json`
3. `autoagent status`
4. **Expected:** Prints an error message (not a raw Python traceback), exit 1

### Help with no subcommand

1. `autoagent` (no arguments)
2. **Expected:** Prints help/usage message showing available subcommands

## Failure Signals

- Raw Python tracebacks in CLI output (should always be structured "Error:" messages)
- Exit code 0 on error paths
- Missing files in .autoagent/ after init
- state.json with unexpected or missing fields
- `autoagent` command not found after `pip install -e .`

## Requirements Proved By This UAT

- R006 — CLI commands work: `autoagent init` scaffolds project, `autoagent status` reads state, `autoagent run` validates state. Standard Python CLI with GSD-2-style UX.
- R005 (partial) — State files are human-readable JSON, atomic writes confirmed by unit tests, lock protocol confirmed by unit tests. Full crash recovery proven in S06.

## Not Proven By This UAT

- R005 full crash recovery (kill mid-iteration, restart) — requires S06
- R006 PI SDK integration — reinterpreted as standard Python CLI (D017)
- Actual optimization loop execution — `autoagent run` is a stub until S05
- Lock protocol under real concurrency — proven by unit tests with mock PIDs, not live process contention

## Notes for Tester

- `autoagent run` printing "not yet implemented" is correct behavior for this slice — it's wired in S05
- The `--project-dir` flag defaults to cwd, so most tests don't need it explicitly
- State.json `updated_at` uses UTC ISO format
- Config uses JSON (not YAML) despite boundary map saying config.yaml — this is intentional (D015)
