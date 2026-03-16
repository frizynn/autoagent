---
id: M006
provides:
  - Complete deletion of Python optimization framework (src/autoagent/, tests/, pyproject.toml, uv.lock)
  - Extension with only go+stop subcommands dispatching LLM-as-optimizer loop
  - system.md with MODE A (conversational setup) and MODE B (project status) keyed on .autoagent/ existence
  - program.md autoresearch protocol with results.tsv format, git branch naming, simplicity criterion
  - Conversational setup contracts — prepare.py skeleton, pipeline.py contract, baseline validation
  - DashboardOverlay reading results.tsv with score summaries, git branch detection, experiment listing
  - Stop command wired to ctx.abort() with idle-state guard
  - session_start banner with project health, branch info, and dashboard hint
key_decisions:
  - D079: system.md MODE A/B keyed on .autoagent/ existence
  - D080: go prefers local .autoagent/program.md over bundled
  - D082: Extension reads prompts via readFileSync at command time
  - D083: system.md MODE A skeleton ~25 lines with argparse
  - D084: go guard checks pipeline.py and prepare.py before dispatch
  - D085: GSD dashboard-overlay pattern for AutoAgent dashboard
  - D086: Git helpers duplicated in both files to avoid circular dependency
  - D087: Overlay wiring via ctx.ui.custom with overlay options
  - D088: Stop command uses ctx.isIdle() guard before ctx.abort()
patterns_established:
  - Extension reads prompts from filesystem at command time, not at import time (D082)
  - session_start inspects .autoagent/ disk state for project health
  - go dispatches via pi.sendMessage with customType "autoagent-go"
  - Dashboard overlay with 2s disk refresh timer, box borders via borderAccent theme
  - Stop command pattern — ctx.isIdle() guard → ctx.abort() with user-visible feedback both paths
observability_surfaces:
  - session_start notification shows project status, branch info, and dashboard hint on every TUI launch
  - go guard emits "Project not ready" notification when pipeline.py or prepare.py missing
  - Dashboard refreshes from disk every 2s — changes to results.tsv reflected within one interval
  - Missing results.tsv shows "No experiments yet" in dashboard
  - stop gives "Nothing running to stop." when idle, "Experiment loop stopped." when aborting
requirement_outcomes:
  - id: R104
    from_status: active
    to_status: validated
    proof: DashboardOverlay class reads results.tsv, parses all columns, computes score summaries, refreshes on 2s timer, renders with scroll support. Ctrl+Alt+A opens as overlay. Handles missing file and git errors gracefully.
  - id: R105
    from_status: active
    to_status: validated
    proof: All listed artifacts confirmed absent on disk — src/autoagent/, tests/, pyproject.toml, uv.lock, .pi/extensions/autoagent/, 5 deleted extension modules. tsc builds cleanly.
  - id: R106
    from_status: active
    to_status: validated
    proof: index.ts has exactly 2 case statements (go, stop). go guard checks pipeline.py/prepare.py existence and returns "Project not ready" when missing. No other commands registered.
  - id: R107
    from_status: active
    to_status: validated
    proof: program.md defines results.tsv format (commit, score, status, description tab-separated). Dashboard parseResultsTsv() reads and parses the same format. Both producer and consumer implemented.
  - id: R108
    from_status: active
    to_status: validated
    proof: program.md contains explicit "The Simplicity Criterion" section with complexity-justified-keep/discard rules.
duration: 50m
verification_result: passed
completed_at: 2026-03-16
---

# M006: Autoresearch Pivot

**Deleted the entire Python optimization framework and wired the autoresearch model end-to-end — LLM follows program.md as the optimizer, conversational setup produces prepare.py + pipeline.py, dashboard reads results.tsv from disk, experiments on git branches.**

## What Happened

Three slices executed cleanly over ~50 minutes to complete the pivot from a Python optimization framework to the autoresearch model.

**S01 (Clean Slate + Loop Foundation)** deleted the entire old codebase — src/autoagent/ (OptimizationLoop, MetaAgent, Evaluator, Archive, and all supporting modules), tests/ (502 mock-only tests), pyproject.toml, uv.lock, and 5 obsolete extension modules (subprocess-manager.ts, interview-runner.ts, report-overlay.ts, dashboard-overlay.ts, types.ts). Rewrote index.ts to register only `go` and `stop` subcommands. The `go` command reads program.md (local .autoagent/ first, bundled fallback) and dispatches it to the agent via `pi.sendMessage()`. Created system.md with MODE A (no project → guide setup) and MODE B (project exists → show status), with a guard preventing the LLM from acting as a general coding assistant. Updated program.md with the simplicity criterion, branch collision handling, and results.tsv format.

**S02 (Conversational Setup + Minimal UX)** enriched system.md MODE A from 6 vague steps to 6 concrete steps with full contracts: prepare.py output format (`score: X.XXXX`), a ~25-line Python skeleton (test_cases, eval(), check(), `__main__` with argparse), pipeline.py contract (`run(input_data, context) → dict`), baseline validation (score 0.1–0.9), and explicit completion criteria. Added a guard to the `go` handler that checks for pipeline.py and prepare.py before dispatching — missing files get a "Project not ready" notification instead of a confusing error.

**S03 (Multi-Experiment + Dashboard)** built dashboard.ts — a DashboardOverlay class following the GSD pattern with constructor(tui, theme, onClose), box borders via borderAccent, and a 2-second setInterval refresh from disk. Three module-level helpers parse results.tsv, detect the current git branch, and list autoagent/* experiment branches. The overlay shows score summaries (best/latest/keeps/discards/crashes), experiment branch list, and last 20 results rows with scroll support. Wired Ctrl+Alt+A to open the dashboard, replaced stop's placeholder with ctx.isIdle() → ctx.abort(), and enhanced session_start with branch detection and dashboard hint.

The extension is now two files: `index.ts` (commands, events, shortcut wiring) and `dashboard.ts` (overlay component), plus prompts in `system.md` and `program.md`.

## Cross-Slice Verification

**Old framework completely removed** — src/autoagent/, tests/, pyproject.toml, uv.lock, .pi/extensions/autoagent/ all confirmed absent on disk. PASS.

**`/autoagent go` dispatches LLM to follow program.md** — go command reads program.md (local then bundled fallback), dispatches via pi.sendMessage() with content prefix "Read and follow this experiment protocol exactly." Guard checks pipeline.py and prepare.py existence first. PASS.

**Conversational setup produces working prepare.py + pipeline.py** — system.md MODE A contains full prepare.py contract (score: X.XXXX format), ~25-line skeleton, pipeline.py contract (run → dict), baseline validation, and completion criteria. The LLM has all the information needed to guide setup. PASS (contract-level; live conversation testing is UAT).

**Multiple experiments on separate git branches** — program.md defines `autoagent/run-<date>` naming with collision counter. Dashboard lists autoagent/* branches via git. session_start shows current branch. PASS (protocol-level; actual branch creation is LLM runtime behavior).

**Dashboard overlay shows experiment progress** — DashboardOverlay reads results.tsv every 2s, shows scores/keeps/discards/crashes, experiment branches, results table. Ctrl+Alt+A opens as overlay. Handles missing file gracefully. PASS.

**Only go and stop commands** — index.ts has exactly 2 case statements: "go" and "stop". No other commands registered. PASS.

**TUI builds cleanly** — tsc --noEmit passes with zero errors (verified in S01 and S02). PASS.

## Requirement Changes

- R104: active → validated — DashboardOverlay reads results.tsv, parses all columns, computes score summaries, refreshes on 2s timer, Ctrl+Alt+A opens as overlay, handles missing file and git errors gracefully
- R105: active → validated — all listed artifacts confirmed absent on disk; tsc builds cleanly without them
- R106: active → validated — only go and stop commands exist (2 case statements in index.ts), go guard provides contextual "Project not ready" rejection
- R107: active → validated — program.md defines results.tsv format, dashboard parseResultsTsv() reads and parses it; producer and consumer both implemented
- R108: active → validated — program.md contains explicit "The Simplicity Criterion" section with complexity-justified keep/discard rules
- R101: remains active — code infrastructure complete (go dispatches program.md), awaits end-to-end runtime proof with real LLM
- R102: remains active — system.md MODE A has full contracts and skeleton, awaits live conversation testing
- R103: remains active — protocol defined in program.md, dashboard lists branches, awaits runtime proof of branch creation/switching

## Forward Intelligence

### What the next milestone should know
- The extension is two files: `index.ts` (commands, events, shortcut wiring) and `dashboard.ts` (overlay component). Prompts live in `prompts/system.md` and `prompts/program.md`.
- `go` dispatches program.md content via `pi.sendMessage()` with customType "autoagent-go" — the LLM receives the full protocol as a single message
- system.md MODE A/B switching is based solely on `existsSync(join(cwd, '.autoagent'))` — creating that directory transitions the agent's behavior
- R101, R102, R103 are contract-complete but not yet validated with real LLM runtime testing — the next milestone should prioritize end-to-end proof if validation is a goal

### What's fragile
- system.md fallback on read failure uses an inline string — if it drifts from the file, behavior diverges silently
- `getCurrentBranch()` is duplicated in dashboard.ts and index.ts — changes to one must be mirrored
- TSV parsing assumes header starts with "commit" — other header formats will be included as data rows
- The 2s setInterval refresh calls execSync for git on every tick — slow git repos could lag the UI

### Authoritative diagnostics
- session_start notification — shows exact project state on every TUI launch; first thing to check if behavior seems wrong
- `grep 'case "' index.ts` — confirms only go and stop commands exist
- Dashboard overlay (Ctrl+Alt+A) — shows results.tsv parsing, branch detection, score summaries in real time
- `tsc --noEmit` in tui/ — zero errors confirms extension integrity

### What assumptions changed
- .pi/extensions/autoagent/ was expected to exist and need deletion — it was already absent
- src/ directory cleanup was not originally planned but was necessary after deleting src/autoagent/
- No assumptions were violated in S02 or S03 — both executed exactly as planned

## Files Created/Modified

- `src/autoagent/` — DELETED (entire Python optimization framework)
- `tests/` — DELETED (502 mock-only tests)
- `pyproject.toml` — DELETED
- `uv.lock` — DELETED
- `tui/src/resources/extensions/autoagent/subprocess-manager.ts` — DELETED
- `tui/src/resources/extensions/autoagent/interview-runner.ts` — DELETED
- `tui/src/resources/extensions/autoagent/report-overlay.ts` — DELETED
- `tui/src/resources/extensions/autoagent/dashboard-overlay.ts` — DELETED
- `tui/src/resources/extensions/autoagent/types.ts` — DELETED
- `tui/src/resources/extensions/autoagent/index.ts` — rewritten (go+stop commands, session_start, before_agent_start, Ctrl+Alt+A dashboard, stop wired to ctx.abort())
- `tui/src/resources/extensions/autoagent/dashboard.ts` — NEW (DashboardOverlay with TSV parsing, git helpers, score summaries, scroll, 2s refresh)
- `tui/src/resources/extensions/autoagent/prompts/system.md` — rewritten (MODE A/B, prepare.py contract/skeleton, pipeline.py contract, baseline validation)
- `tui/src/resources/extensions/autoagent/prompts/program.md` — updated (simplicity criterion, branch collision handling, results.tsv format)
