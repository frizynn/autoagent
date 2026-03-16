# S02: Conversational Setup + Minimal UX — Research

**Date:** 2026-03-15
**Status:** Complete

## Summary

S02 is a prompt-engineering-heavy slice with lightweight extension wiring. The LLM handles setup through natural conversation — MODE A in system.md already defines this flow. The gaps are: (1) system.md doesn't give the LLM enough specifics about prepare.py's output contract, (2) the LLM can't access bundled program.md to copy it into `.autoagent/`, (3) the `go` command dispatches blindly even without a project, and (4) there's no prepare.py template/example for the LLM to reference.

The approach is: enrich system.md MODE A with the prepare.py output contract and a prepare.py skeleton, have the extension handle program.md provisioning (copy bundled → `.autoagent/`), guard `go` against missing project files, and refine session_start messaging to be more conversational for the no-project case.

This is a low-implementation, high-quality-of-prompting slice. The risk — evaluator generation quality — lives entirely in how well system.md guides the LLM through the conversation.

## Recommendation

**Approach: Enrich prompts + minimal extension guards. No new UI components.**

The setup conversation is handled by the LLM through MODE A — no custom overlays, no interview forms, no wizard. The extension's job is: (1) inject the right context into the system prompt, (2) provision program.md into `.autoagent/` when setup completes, and (3) prevent `go` from running without required files.

System.md MODE A needs three additions:
- The exact `prepare.py eval` output contract (score/total_examples/passed/failed/duration_ms format)
- A prepare.py skeleton showing the expected structure (test cases list + eval function + CLI entry point)
- A pipeline.py contract (must define `run(input_data, context)` returning a dict with "output" key)

Program.md provisioning: the extension should copy bundled program.md to `.autoagent/program.md` when it detects that `.autoagent/` exists but `program.md` doesn't. This can happen in `session_start` or as a helper the LLM calls. Simpler option: the LLM writes it directly since system.md can include the full protocol, but that's a lot of content to put in the system prompt. Better option: extension copies it via a post-setup helper or `go` command can do it.

Actually, simplest correct approach: when the LLM creates `.autoagent/` during setup, the extension's `go` command already checks for local `.autoagent/program.md` first and falls back to bundled. So the LLM doesn't need to copy program.md at all — `go` reads the bundled one. The only reason to copy it is if the user wants to customize the protocol. system.md step 4 ("Copy program.md") can be removed — the protocol works without it.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| System prompt injection | `before_agent_start` event in index.ts | Already wired by S01 — just update system.md content |
| Project state detection | `session_start` handler in index.ts | Already reads `.autoagent/` disk state — refine messages |
| Program.md dispatch | `go` command with bundled fallback | Already works — add a guard for missing project files |
| User conversation | LLM's native tool-use (read/write/bash) | The LLM writes files directly — no custom tooling needed |

## Existing Code and Patterns

- `tui/src/resources/extensions/autoagent/index.ts` — Extension entry point. session_start reads .autoagent/ state, before_agent_start injects system.md, go dispatches program.md. All three need minor modifications.
- `tui/src/resources/extensions/autoagent/prompts/system.md` — MODE A/B system prompt. MODE A needs enrichment with prepare.py contract and skeleton. This is the primary deliverable.
- `tui/src/resources/extensions/autoagent/prompts/program.md` — Experiment protocol. Defines results.tsv format, git branch protocol, simplicity criterion. Read by `go` command. Already correct — no changes needed.
- `git show 28be038:tui/src/resources/extensions/autoagent/templates/pipeline.py` — Old baseline pipeline template (deleted by S01). Shows the expected pipeline.py shape: `run(input_data, context)` → `{"output": ...}`. system.md should reference this contract.

## Constraints

- **No Python build system** — There's no pyproject.toml, no dependencies. prepare.py and pipeline.py must be standalone Python scripts using only stdlib (or user-specified deps).
- **Pi SDK extension API only** — The extension is a single index.ts with types from `@gsd/pi-coding-agent`. No npm dependencies, no build step. Changes are prompt files + minor TS edits.
- **D082: readFileSync at command time** — Prompts are read fresh every invocation. Safe to edit system.md between commands without restart.
- **D079: MODE A/B keyed on .autoagent/ existence** — The behavioral split is binary. Once `.autoagent/` exists, the LLM switches to MODE B. Setup must create `.autoagent/` as its final step.
- **prepare.py eval output format** — program.md defines: `score: X.XXXX`, `total_examples: N`, `passed: N`, `failed: N`, `duration_ms: N`. prepare.py must produce exactly this format. The LLM must know this during setup.
- **pipeline.py contract** — Must define `run(input_data, context)` that returns a result. program.md says "The only constraint is that pipeline.py must define a `run(input_data, context)` function that returns a result."
- **tsc must pass** — Extension must compile cleanly with `tsc --noEmit` from the tui directory (or via the repo's tsconfig).

## Common Pitfalls

- **Vague prepare.py without real test cases** — The LLM might write a prepare.py that scores trivially (always 1.0 or always 0.0). system.md must instruct the LLM to validate the baseline scores between 0.1 and 0.9 before declaring setup complete.
- **Missing output format** — If prepare.py doesn't print `score: X.XXXX` exactly, program.md's `grep "^score:" eval.log` step fails. The skeleton in system.md must show the exact print format.
- **program.md not in .autoagent/** — This is fine: `go` falls back to bundled. But if the user later wants to customize, they need a local copy. Decided: don't copy by default. Document in system.md that the protocol is built-in.
- **go dispatching without project** — Currently `go` dispatches even with no `.autoagent/`. The LLM then follows program.md but has no pipeline.py or prepare.py. Add a guard: check for `.autoagent/pipeline.py` and `.autoagent/prepare.py` before dispatching.
- **System prompt becoming too long** — Adding the prepare.py skeleton and contract to system.md must be concise. A 30-line skeleton is fine; a 200-line tutorial is not. Keep it tight.
- **MODE A → MODE B transition mid-conversation** — The LLM creates `.autoagent/` during setup. But the mode check happens in `before_agent_start`, which runs once at session start. The LLM must self-enforce MODE B behavior after creating the files. system.md should say: "Once you've created all files, tell the user to run `/autoagent go` and stop offering setup."

## Open Risks

- **Evaluator generation quality** — This is the risk this slice is supposed to retire. The quality depends entirely on system.md MODE A guidance. If the prompt is too vague, the LLM writes bad evaluators. If it's too prescriptive, it forces a rigid structure that doesn't fit all domains. The skeleton approach (show structure, let LLM fill domain logic) is the best balance. Can only be validated by actually running setup conversations.
- **Baseline score validation** — system.md says "validate the baseline scores between 0.1 and 0.9" but the LLM might not actually run the baseline before declaring done. Adding an explicit "run `python3 prepare.py eval` and verify the score is reasonable" step mitigates this.

## Implementation Plan

### Task breakdown estimate

This is a single-task slice. All changes are in three files:

1. **system.md MODE A rewrite** (~60% of effort)
   - Add prepare.py output contract with exact format
   - Add prepare.py skeleton (test_cases list, eval function, `__main__` entry point)
   - Add pipeline.py contract (run function signature, return format)
   - Add baseline validation step (run eval, check score is 0.1–0.9)
   - Remove "Copy program.md" step (go command handles this via bundled fallback)
   - Add explicit completion criteria ("setup is done when all three exist and baseline scores reasonably")

2. **index.ts `go` guard** (~20% of effort)
   - Check `.autoagent/pipeline.py` and `.autoagent/prepare.py` exist before dispatching
   - If missing, notify user to set up project first (conversational prompt)
   - Refine session_start messaging for clarity

3. **Verification** (~20% of effort)
   - tsc --noEmit passes
   - system.md contains prepare.py contract, skeleton, baseline validation step
   - go command refuses dispatch when pipeline.py or prepare.py missing
   - session_start messaging is clear and actionable

### What doesn't need to change

- **program.md** — Already correct. Defines the loop protocol, results.tsv format, simplicity criterion.
- **before_agent_start** — Already injects system.md. No changes needed.
- **stop command** — Remains a no-op placeholder (S03 wires real interrupt).
- **Ctrl+Alt+A shortcut** — Remains placeholder (S03 wires dashboard).
- **Extension structure** — No new files, no new modules.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Pi SDK (extension API) | none | Proprietary — no public skills exist |
| Python evaluation harness | none | Domain-specific — no generic skill applies |

## Sources

- Pi SDK extension types (`@gsd/pi-coding-agent/src/core/extensions/types.ts`) — ExtensionAPI, ExtensionUIContext, sendMessage API, before_agent_start event
- S01 Summary — boundary map, patterns established, forward intelligence
- program.md — experiment protocol contract, output format, simplicity criterion
- system.md — current MODE A/B definitions
- Old pipeline.py template (git show 28be038) — expected pipeline structure
