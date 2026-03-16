# S01: program.md and evaluation harness

**Goal:** The core protocol files exist and work: `program.md` defines how the agent runs experiments, the evaluation harness validates pipelines, and a toy problem proves the flow works manually.
**Demo:** Agent reads `program.md`, edits `pipeline.py`, runs `python prepare.py eval`, gets a metric back, and can log a result to `results.tsv`.

## Must-Haves

- `program.md` — complete experiment protocol the agent follows (autoresearch pattern)
- `prepare.py` — evaluation harness template with `eval` subcommand that outputs a metric
- `pipeline.py` — baseline template with a `run()` function
- `results.tsv` — format defined and initialized with header
- The system prompt tells the agent to read `program.md` on `/autoagent go`
- A toy problem proves the harness works end-to-end

## Proof Level

- This slice proves: integration
- Real runtime required: yes
- Human/UAT required: yes (agent manually follows program.md once)

## Verification

- `python prepare.py eval` runs against baseline `pipeline.py` and outputs a metric
- `results.tsv` header exists and format is correct
- `python -m pytest tests/ -v` — all existing tests pass (496+)
- Manual: tell the agent to read `program.md` and run one experiment

## Tasks

- [ ] **T01: program.md experiment protocol** `est:45m`
  - Why: This is the core "skill" — the instructions the agent follows to run experiments
  - Files: `tui/src/resources/extensions/autoagent/prompts/program.md`
  - Do: Write the experiment protocol inspired by autoresearch's program.md but adapted for autoagent. Cover: setup, experimentation loop (edit → run → eval → keep/discard), output format, logging to results.tsv, git workflow, NEVER STOP rule, what to do when stuck (research escalation). Also update system.md to reference program.md.
  - Verify: Read the file and confirm it covers all protocol aspects
  - Done when: A human reading it could follow the protocol manually

- [ ] **T02: Evaluation harness and toy problem** `est:45m`
  - Why: The agent needs a `prepare.py eval` command that scores a pipeline and outputs a metric
  - Files: `src/autoagent/harness.py`, `tests/test_harness.py`
  - Do: Create a minimal evaluation harness: `python prepare.py eval` loads `pipeline.py`, runs it against test cases, outputs metric in parseable format. Create a toy problem (string transformation or simple math) with prepare.py + pipeline.py + a few test cases. Write tests proving the harness works.
  - Verify: `python prepare.py eval` outputs a metric line like `score: 0.75`
  - Done when: The harness runs, scores a baseline, and the agent can grep the metric

- [ ] **T03: Wire /autoagent go and update system prompt** `est:30m`
  - Why: The `/autoagent go` command needs to read program.md and dispatch the agent
  - Files: `tui/src/resources/extensions/autoagent/index.ts`, `tui/src/resources/extensions/autoagent/prompts/system.md`
  - Do: Add `/autoagent go` subcommand to the extension. It reads `program.md` from `.autoagent/` (or from bundled prompts if no project-level one exists), injects it via `pi.sendMessage({ content, display: false }, { triggerTurn: true })`. Update system.md to describe the agent-driven loop. Rebuild the TUI.
  - Verify: `/autoagent go` dispatches the agent with program.md content
  - Done when: Agent receives the protocol and starts following it

## Files Likely Touched

- `tui/src/resources/extensions/autoagent/prompts/program.md`
- `tui/src/resources/extensions/autoagent/prompts/system.md`
- `tui/src/resources/extensions/autoagent/index.ts`
- `src/autoagent/harness.py`
- `tests/test_harness.py`
