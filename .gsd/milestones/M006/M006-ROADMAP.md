# M006: Autoresearch Pivot

**Vision:** Delete the old Python optimization framework entirely and wire the autoresearch model end-to-end. The LLM itself is the optimizer — it follows program.md, edits pipeline.py, runs prepare.py eval, keeps or reverts via git. Conversational setup, minimal commands, multi-experiment on git branches, dashboard from disk.

## Success Criteria

- Old Python framework completely removed — no src/autoagent/, no tests/, no pyproject.toml
- `/autoagent go` dispatches the LLM to follow program.md and iterate autonomously
- Conversational setup produces working prepare.py + pipeline.py from natural language
- Multiple experiments on separate git branches with independent results.tsv
- Dashboard overlay shows experiment progress from results.tsv
- Only two commands: `/autoagent go` and `/autoagent stop`

## Key Risks / Unknowns

- **Dashboard without JSONL stream** — must switch from subprocess event stream to file-watching results.tsv
- **Evaluator generation quality** — LLM must produce a prepare.py that actually measures what the user cares about
- **Git branch edge cases** — dirty working tree, concurrent branch operations, experiment isolation

## Proof Strategy

- Dashboard without JSONL → retire in S03 by proving dashboard updates from results.tsv file reads
- Evaluator generation → retire in S02 by proving conversational setup produces a prepare.py that scores a baseline pipeline
- Git branch management → retire in S03 by proving experiments on separate branches with independent logs

## Verification Classes

- Contract verification: file deletion confirmed, extension commands work, program.md dispatched
- Integration verification: real LLM call via Pi SDK runs the loop, git operations create/switch branches
- Operational verification: none (local dev only)
- UAT / human verification: conversational setup quality, dashboard usability

## Milestone Definition of Done

This milestone is complete only when all are true:

- Old framework deleted (src/autoagent/, tests/, pyproject.toml, .pi/extensions/)
- `/autoagent go` runs a real autoresearch loop with actual LLM calls
- Conversational setup from natural language to working prepare.py + pipeline.py
- Git branch per experiment with keep/discard via git operations
- Dashboard overlay reads results.tsv and shows iteration progress
- Only `/autoagent go` and `/autoagent stop` as commands — everything else contextual
- TUI builds and launches cleanly

## Requirement Coverage

- Covers: R101, R102, R103, R104, R105, R106, R107, R108
- Partially covers: none
- Leaves for later: none
- Orphan risks: none

## Slices

- [x] **S01: Clean Slate + Loop Foundation** `risk:high` `depends:[]`
  > After this: old Python framework deleted, `/autoagent go` dispatches the LLM to follow program.md — agent edits pipeline.py, runs prepare.py eval, keeps/discards via git, logs to results.tsv

- [ ] **S02: Conversational Setup + Minimal UX** `risk:medium` `depends:[S01]`
  > After this: launch autoagent with no project, describe what to optimize, LLM writes prepare.py + baseline pipeline.py through conversation. Only `go` and `stop` commands visible.

- [ ] **S03: Multi-Experiment + Dashboard** `risk:medium` `depends:[S01]`
  > After this: each experiment on its own git branch, switch between them, dashboard overlay reads results.tsv and shows iteration progress with scores and decisions

## Boundary Map

### S01 → S02

Produces:
- `program.md` — the autoresearch protocol the LLM follows
- `templates/pipeline.py` — baseline pipeline template
- `/autoagent go` command — dispatches program.md to the agent session via `pi.sendMessage()`
- `/autoagent stop` command — interrupts the running loop
- `system.md` — system prompt telling the LLM it's AutoAgent
- Clean repo with no Python framework artifacts

Consumes:
- nothing (first slice)

### S01 → S03

Produces:
- `program.md` protocol — defines results.tsv format, git branch naming, keep/discard behavior
- `/autoagent go` command — the loop that S03's dashboard tracks
- `results.tsv` format — commit, score, status, description (tab-separated)

Consumes:
- nothing (first slice)

### S02 → S03

Produces:
- Contextual session_start behavior — detects whether project exists
- Updated system prompt with setup guidance

Consumes from S01:
- program.md, templates/pipeline.py, system.md
