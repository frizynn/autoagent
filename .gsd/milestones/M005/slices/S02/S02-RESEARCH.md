# S02: Interview Overlay with JSON Protocol — Research

**Date:** 2026-03-14

## Summary

This slice adds a bidirectional JSON request-response protocol to the Python interview (`--json` mode on `autoagent new`) and a TypeScript interview overlay that drives the 6-phase interview using pi's native `ctx.ui.input()` and `ctx.ui.select()` dialogs. The Python side emits JSON prompts to stdout and reads JSON answers from stdin; the TypeScript side renders each phase as a TUI dialog and pipes the user's answer back.

The interview flow is well-understood: 6 phases (goal, metrics, constraints, search_space, benchmark, budget) + confirmation. Each phase has a question, collects an answer, runs vague-input detection, and optionally triggers LLM-generated follow-up probes (max 2 retries). The existing `InterviewOrchestrator` already accepts `input_fn` and `print_fn` callables — the `--json` mode wraps these to read/write JSON instead of terminal I/O.

**Primary recommendation:** Keep the Python `--json` mode thin — replace `input_fn` and `print_fn` with JSON stdin/stdout versions. The TypeScript side doesn't need a custom overlay component; it can use a sequential series of `ctx.ui.input()` / `ctx.ui.select()` calls in a command handler, with a progress notification between phases. This is simpler than a full custom overlay and produces a more native-feeling experience.

## Recommendation

**Two-task structure:**

1. **Python `--json` mode for `autoagent new`** — Add `--json` flag to `cmd_new`. Wrap the `InterviewOrchestrator` with JSON I/O: emit `{"type":"prompt","phase":"goal","question":"..."}` to stdout, read `{"type":"answer","text":"..."}` from stdin. Emit follow-up probes the same way. Emit `{"type":"complete","config":{...},"context":"..."}` at end. Keep the orchestrator logic untouched — just swap `input_fn`/`print_fn`.

2. **TypeScript interview command** — Add `new` subcommand to `/autoagent`. Spawn `autoagent new --json` with bidirectional stdio. For each prompt received, call `ctx.ui.input()` to collect the answer, then write the JSON response to stdin. Show phase progress via `ctx.ui.notify()`. On completion, parse the final config event and notify success.

**Why not a custom overlay?** The interview is sequential input collection, not a persistent dashboard. Pi's `ctx.ui.input()` and `ctx.ui.select()` are purpose-built for this — modal dialogs with text input, placeholders, and escape-to-cancel. A custom overlay would re-implement what these already do. The dashboard overlay (S01) was needed because it's a persistent, updating view — the interview is a one-shot flow.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| Multi-phase user input collection | `ctx.ui.input(title, placeholder)` from pi extension API | Native TUI dialog with escape handling, consistent UX |
| Confirmation step | `ctx.ui.select(title, ["Yes", "No"])` | Native select dialog |
| Progress feedback between phases | `ctx.ui.notify(message, "info")` | Non-blocking notification |
| JSON line parsing from subprocess | Node.js `readline.createInterface()` on stdout | Already proven in SubprocessManager (S01) |
| Writing JSON to subprocess stdin | `proc.stdin.write(JSON.stringify(msg) + "\n")` | Standard Node.js |
| Vague-input detection + follow-up probes | `InterviewOrchestrator` with `input_fn`/`print_fn` injection | Core logic already works — just swap I/O functions |

## Existing Code and Patterns

- `src/autoagent/interview.py` — `InterviewOrchestrator.__init__` accepts `input_fn` and `print_fn` callables. The `--json` mode creates custom callables that do JSON stdin/stdout instead of terminal I/O. **This is the key leverage point — no changes to orchestrator logic.**
- `src/autoagent/interview.py` `PHASES` — 6 phases defined as `(phase_key, template_question)` tuples. The `--json` mode emits these to stdout for the TypeScript side to render.
- `src/autoagent/interview.py` `is_vague()` — Vague-input detection is deterministic (length + phrase matching). Runs in Python, not TypeScript. TypeScript just relays answers.
- `src/autoagent/cli.py` `cmd_new()` — Currently uses bare `InterviewOrchestrator(llm=llm)`. Will add `--json` flag that wraps I/O. Pattern mirrors `cmd_run`'s `--jsonl` flag (D065).
- `.pi/extensions/autoagent/index.ts` — Command handler with `args[0]` switch. S01 forward intelligence says: "add `new` case for S02". 
- `.pi/extensions/autoagent/subprocess-manager.ts` — **Not directly reusable for interview.** SubprocessManager is a singleton for `run --jsonl` with unidirectional stdout. Interview needs bidirectional stdin/stdout on a separate subprocess. Create a lightweight `InterviewRunner` function (not a class) that spawns, drives the protocol, and returns the result.
- `~/.gsd/agent/extensions/gsd/commands.ts` lines 318-398 — GSD preferences wizard uses sequential `ctx.ui.input()` and `ctx.ui.select()` calls to collect multi-field configuration. **Exact pattern for the interview overlay.**

## Constraints

- **Strict request-response protocol** — Python writes one JSON line, waits for one JSON line. No interleaving. TypeScript must not write before reading. Deadlock-safe by construction.
- **SubprocessManager is for `run` only** — It's a singleton (D070) and uses `stdio: ["ignore", "pipe", "pipe"]`. Interview needs stdin pipe. Create a separate function, not extend SubprocessManager.
- **`PYTHONUNBUFFERED=1` required** (D068) — Same as S01 subprocess spawning.
- **Interview currently uses MockLLM** — Follow-up probes and context generation use MockLLM. The JSON protocol must work regardless of LLM backend (mock or real).
- **`cmd_new` already handles auto-init, overwrite confirmation, benchmark generation** — The `--json` mode must either replicate these behaviors in the protocol or handle them differently. Recommendation: `--json` mode skips overwrite confirmation (the TUI side handles it) and emits benchmark generation status as protocol events.
- **`ctx.ui.input()` returns `string | undefined`** — `undefined` means user pressed Escape. Must handle cancellation gracefully by sending a cancel message to stdin and killing the subprocess.

## Common Pitfalls

- **Stdin deadlock** — If Python's `input_fn` blocks waiting for stdin and TypeScript hasn't written yet (waiting for user), that's fine — both sides block on their respective I/O. But if TypeScript writes before Python reads, the data buffers. Only dangerous if TypeScript writes multiple lines before Python reads any — protocol prevents this since it's strict request-response.
- **Partial JSON lines on stdout** — Same risk as S01. Use readline interface to buffer until newline. Already solved pattern.
- **Subprocess exit mid-interview** — If Python crashes during the interview, the readline `close` event fires. TypeScript must handle this as an interview abort, not hang waiting for the next prompt.
- **Benchmark generation output** — `cmd_new` currently prints benchmark generation status to stdout. In `--json` mode, these must go to stderr or be emitted as JSON protocol events, not raw text on stdout (same pattern as `cmd_run --jsonl` redirecting print to stderr).
- **Overwrite confirmation** — `cmd_new` currently asks "Overwrite existing configuration?" via terminal `input()`. In `--json` mode, this must be part of the protocol (emit a confirm prompt) or skipped (always overwrite when invoked via `--json`, since the TUI side can check first).
- **User cancels mid-phase** — `ctx.ui.input()` returns `undefined` on Escape. TypeScript should send a cancel/abort message and kill the subprocess. Python should handle `EOFError` from stdin gracefully.

## Open Risks

- **Protocol version evolution** — No protocol versioning exists yet. If the interview phases change (new phase added, phase renamed), the TypeScript side could misinterpret messages. Mitigation: include a protocol version in the first message (`{"type":"protocol","version":1}`). Low risk for now since both sides are in the same repo.
- **Follow-up probe latency with real LLM** — Currently MockLLM returns instantly. With a real LLM, generating a follow-up probe could take 2-5 seconds. The TypeScript side should show a loading indicator while waiting for the next prompt. `ctx.ui.notify("Analyzing your answer...", "info")` is sufficient.
- **Error recovery** — If the Python subprocess crashes mid-interview, partial answers are lost. No persistent draft state. Acceptable for now — interviews take < 2 minutes and can be restarted.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Pi extensions | (none) | No pi-specific extension skill exists — GSD extension source is the authoritative reference |
| TUI design | `hyperb1iss/hyperskills@tui-design` (111 installs) | available — generic, not pi-specific. Not needed — interview uses pi's built-in input/select dialogs |

No skill installation recommended.

## Sources

- Pi extension API types — `ExtensionUIContext.input()`, `.select()`, `.notify()` signatures (source: `@gsd/pi-coding-agent/dist/core/extensions/types.d.ts`)
- GSD preferences wizard — sequential `ctx.ui.input()` / `ctx.ui.select()` pattern for multi-field collection (source: `~/.gsd/agent/extensions/gsd/commands.ts` lines 310-405)
- InterviewOrchestrator — `input_fn`/`print_fn` injection points, 6 phases, vague-input detection (source: `src/autoagent/interview.py`)
- S01 SubprocessManager — readline-based JSONL parsing, `PYTHONUNBUFFERED=1` pattern (source: `.pi/extensions/autoagent/subprocess-manager.ts`)
- S01 forward intelligence — "add `new` and `report` cases for S02/S03", "SubprocessManager is singleton — interview needs separate subprocess mode" (source: S01-SUMMARY.md)
