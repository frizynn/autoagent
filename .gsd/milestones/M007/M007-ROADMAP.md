# M007: Agent-Driven Optimization Loop

**Vision:** `autoagent` is a single command that opens a chat TUI. You describe what you want to optimize. The agent asks clarifying questions, sets up the project (`program.md` + `prepare.py` + `pipeline.py`), then enters an infinite experiment loop — modifying `pipeline.py`, running the evaluation, keeping or discarding based on the metric, and repeating. It never stops until you stop it. When it stalls, it researches harder. Progress is visualized in a dashboard overlay.

## Success Criteria

- Typing `autoagent` in a directory with no project starts a conversational setup
- The agent creates `program.md`, `prepare.py` (fixed evaluation), and `pipeline.py` (baseline)
- `/autoagent go` kicks off the autonomous experiment loop
- The agent modifies `pipeline.py`, runs evaluation, logs results, keeps/discards — looping forever
- Results are logged to `results.tsv` with commit hash, metric, status, description
- When stuck, the agent searches the web, reads docs, tries combining near-misses, tries radical changes
- `/autoagent dashboard` (or `Ctrl+Alt+A`) shows progress chart + iteration table from `results.tsv`
- Each experiment is a git commit on a dedicated branch
- The agent NEVER stops to ask — it runs until interrupted

## Key Risks / Unknowns

- Can the Pi SDK agent maintain a long-running loop without context exhaustion? GSD solves this with fresh sessions per unit — may need the same pattern here.
- Research quality depends entirely on the LLM's ability to generate good mutations and self-correct.
- Evaluation harness must be user-defined and robust — bad `prepare.py` = garbage metrics.

## Proof Strategy

- Long-running loop → retire in S02 by proving 10+ iterations run autonomously without stalling
- Research quality → retire in S03 by proving the agent uses web search and prior results to improve

## Verification Classes

- Contract verification: manual test — run 10+ iterations on a toy problem
- Integration verification: conversational setup → loop → dashboard → results
- Operational verification: crash recovery, context window management
- UAT / human verification: visual check of dashboard + results quality

## Milestone Definition of Done

- User types `autoagent`, configures a project via conversation, and the agent runs experiments autonomously
- Dashboard shows progress chart from `results.tsv`
- 10+ iterations complete without human intervention on a toy problem
- Agent demonstrates research behavior when stuck (web search, combining ideas)
- All existing Python tests still pass (496+)

## Slices

- [ ] **S01: program.md and evaluation harness** `risk:high` `depends:[]`
  > After this: `program.md` defines the agent's experiment loop protocol, `prepare.py` template works for a toy problem, agent can run one experiment manually
- [ ] **S02: Autonomous loop via /autoagent go** `risk:high` `depends:[S01]`
  > After this: `/autoagent go` starts the agent in NEVER STOP mode, it loops experiments with keep/discard on a git branch, results logged to results.tsv
- [ ] **S03: Research escalation and dashboard** `risk:medium` `depends:[S02]`
  > After this: Agent searches web and analyzes past results when stuck, dashboard overlay shows progress chart from results.tsv
- [ ] **S04: Conversational setup** `risk:low` `depends:[S01]`
  > After this: User types `autoagent` with no project, agent asks what to optimize, generates program.md + prepare.py + pipeline.py

## Boundary Map

### S01 → S02

Produces:
- `program.md` template with experiment loop protocol
- `prepare.py` template with evaluation harness
- `pipeline.py` baseline template
- `results.tsv` format specification

Consumes:
- nothing (first slice)

### S02 → S03

Produces:
- `/autoagent go` command that dispatches the agent in loop mode
- Git branch management (create branch, commit per experiment, revert on discard)
- Results logging to `results.tsv`

Consumes:
- `program.md` protocol from S01

### S01 → S04

Produces:
- Template files that the setup flow generates

Consumes:
- nothing (first slice)
