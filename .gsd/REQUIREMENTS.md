# Requirements

This file is the explicit capability and coverage contract for the project.

## Active

### R101 — Autoresearch Loop
- Class: core-capability
- Status: active
- Description: The LLM follows program.md as an autonomous loop: read code → think → edit pipeline.py → commit → run prepare.py eval → keep/revert → repeat forever. No Python framework in between.
- Why it matters: This is the entire product — the LLM's own intelligence is the optimizer
- Source: user
- Primary owning slice: M006/S01
- Supporting slices: none
- Validation: go command dispatches program.md to the agent via pi.sendMessage(); loop protocol fully defined in program.md. Awaits end-to-end runtime proof with real LLM.
- Notes: Directly follows Karpathy's autoresearch pattern

### R102 — Conversational Setup
- Class: primary-user-loop
- Status: active
- Description: No rigid interview form. User describes what they want to optimize through conversation. The LLM helps write prepare.py and baseline pipeline.py. Setup through talking, not through commands.
- Why it matters: User-friendly — no commands to memorize, no forms to fill
- Source: user
- Primary owning slice: M006/S02
- Supporting slices: none
- Validation: system.md MODE A contains full prepare.py contract (score: X.XXXX format), ~25-line skeleton, pipeline.py contract (run(input_data, context) → dict), baseline validation step, and completion criteria. Awaits live LLM conversation testing for full validation.
- Notes: Replaces the old InterviewOrchestrator rigid phase system

### R103 — Multi-Experiment via Git Branches
- Class: core-capability
- Status: active
- Description: Each experiment lives on a git branch (autoagent/<name>). Keep = advance branch. Discard = git reset --hard HEAD~1. Multiple experiments coexist in one repo.
- Why it matters: Users want to try different optimization strategies without losing work
- Source: user
- Primary owning slice: M006/S03
- Supporting slices: M006/S01
- Validation: program.md defines autoagent/run-<date> naming with collision counter. Dashboard lists autoagent/* branches. session_start shows current experiment branch. Awaits runtime proof of branch creation/switching.
- Notes: Git history IS the experiment archive — no separate archive system needed

## Validated

### R104 — Live Dashboard for Agent Loop (validated by M006/S03)
- Class: primary-user-loop
- Status: validated
- Description: Dashboard overlay (Ctrl+Alt+A) shows current experiment progress — iterations, scores, keeps/discards. Reads results.tsv from disk since there's no JSONL subprocess anymore.
- Why it matters: Users need to see what's happening without interrupting the loop
- Source: user
- Primary owning slice: M006/S03
- Supporting slices: none
- Validation: DashboardOverlay class reads results.tsv, parses all columns, computes score summaries (best/latest/keeps/discards/crashes), refreshes on 2s timer, renders with scroll support (↑↓/j/k/g/G). Ctrl+Alt+A opens as centered overlay (80% width). Handles missing file ("No experiments yet") and git errors gracefully. Box borders via borderAccent theme.
- Notes: File-watching based instead of JSONL stream based

### R105 — Dead Code Removal (validated by M006/S01)
- Class: constraint
- Status: validated
- Description: Delete the entire Python optimization framework — OptimizationLoop, MetaAgent, Evaluator, Archive, Pareto, TLA+, Leakage, Sandbox, Summarizer, BenchmarkGenerator, InterviewOrchestrator, MockLLM, OpenAILLM, all 502 tests, the old Pi extension at .pi/extensions/, pyproject.toml, src/autoagent/, tests/.
- Why it matters: Dead code is confusion — the old framework never ran a real optimization and is fully replaced by the autoresearch model
- Source: user
- Primary owning slice: M006/S01
- Supporting slices: none
- Validation: All listed artifacts confirmed absent on disk — src/autoagent/, tests/, pyproject.toml, uv.lock, .pi/extensions/autoagent/, subprocess-manager.ts, interview-runner.ts, report-overlay.ts, dashboard-overlay.ts, types.ts. tsc builds cleanly without them.
- Notes: User explicitly said "delete all unused things"

### R106 — Minimal Command Surface (validated by M006/S02)
- Class: primary-user-loop
- Status: validated
- Description: Two commands max — /autoagent go (start loop) and /autoagent stop. Everything else is contextual — launch shows status, no project triggers conversational setup.
- Why it matters: User-friendly and simple, not that much commands
- Source: inferred
- Primary owning slice: M006/S02
- Supporting slices: M006/S01
- Validation: index.ts has exactly 2 case statements (go, stop). go command guards against missing pipeline.py/prepare.py with contextual "Project not ready" notification. No other commands registered.
- Notes: User's exact words — "user friendly and simple, not that much commands, only necessary"

### R107 — Results Tracking in TSV (validated by M006/S03)
- Class: core-capability
- Status: validated
- Description: results.tsv is the experiment log. Tab-separated: commit, score, status (keep/discard/crash), description. Simple, human-readable, grep-friendly.
- Why it matters: The experiment record must be simple and inspectable — no JSON blobs, no databases
- Source: autoresearch
- Primary owning slice: M006/S01
- Supporting slices: M006/S03
- Validation: program.md defines results.tsv format (commit, score, status, description tab-separated). Dashboard parseResultsTsv() reads and parses the same format. Both producer and consumer implemented and verified.
- Notes: Dashboard reads this file for progress display

### R108 — Simplicity Criterion (validated by M006/S01)
- Class: quality-attribute
- Status: validated
- Description: program.md includes the simplicity criterion — improvements must justify their complexity. Removing code for equal results is a win. Small improvements with ugly complexity are rejected.
- Why it matters: Prevents the optimizer from accumulating cruft — keeps pipeline.py readable
- Source: autoresearch
- Primary owning slice: M006/S01
- Supporting slices: none
- Validation: program.md contains explicit "The Simplicity Criterion" section with complexity-justified keep/discard rules.
- Notes: Karpathy's exact framing — "A 0.001 improvement that adds 20 ugly lines? Probably not worth it."

## Deferred

(none)

## Out of Scope

### R109 — Python Optimization Framework
- Class: anti-feature
- Status: out-of-scope
- Description: No Python OptimizationLoop, MetaAgent, Evaluator, Archive, or any intermediary framework between the LLM and the code it optimizes
- Why it matters: The autoresearch model is simpler and more powerful — the LLM IS the optimizer
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: Explicitly deleted in M006

### R110 — Rigid Interview Forms
- Class: anti-feature
- Status: out-of-scope
- Description: No phase-based interview (goal → metrics → constraints → search_space → benchmark → budget). Setup is conversational.
- Why it matters: Forms feel bureaucratic — conversation is natural and user-friendly
- Source: user
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: Replaced by R102

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R101 | core-capability | active | M006/S01 | none | go dispatches program.md; awaits runtime proof |
| R102 | primary-user-loop | active | M006/S02 | none | system.md MODE A contracts complete; awaits live testing |
| R103 | core-capability | active | M006/S03 | M006/S01 | protocol defined, dashboard lists branches; awaits runtime proof |
| R104 | primary-user-loop | validated | M006/S03 | none | DashboardOverlay reads results.tsv, Ctrl+Alt+A overlay, 2s refresh |
| R105 | constraint | validated | M006/S01 | none | all artifacts absent; tsc builds cleanly |
| R106 | primary-user-loop | validated | M006/S02 | M006/S01 | exactly 2 commands (go, stop); go guard verified |
| R107 | core-capability | validated | M006/S01 | M006/S03 | format defined in program.md; parsed by dashboard |
| R108 | quality-attribute | validated | M006/S01 | none | program.md Simplicity Criterion section |
| R109 | anti-feature | out-of-scope | none | none | n/a |
| R110 | anti-feature | out-of-scope | none | none | n/a |

## Coverage Summary

- Active requirements: 3 (R101, R102, R103)
- Validated requirements: 5 (R104, R105, R106, R107, R108)
- Deferred: 0
- Out of scope: 2 (R109, R110)
- Unmapped active requirements: 0
