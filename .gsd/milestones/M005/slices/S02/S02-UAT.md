# S02: Interview Overlay with JSON Protocol — UAT

**Milestone:** M005
**Written:** 2026-03-14

## UAT Type

- UAT mode: mixed (artifact-driven for protocol contract, live-runtime for TUI experience)
- Why this mode is sufficient: Protocol correctness is proven by 17 pytest tests. TUI dialog rendering requires human visual confirmation in a running pi instance.

## Preconditions

- Python virtualenv active with autoagent installed (`pip install -e .`)
- pi installed and able to load project-local extensions from `.pi/extensions/`
- No existing `.autoagent/` directory in the test project (or willingness to overwrite)

## Smoke Test

Run `autoagent new --json 2>/dev/null` in terminal, type `{"type":"answer","text":"test"}` + Enter for each prompt. Verify JSON lines appear on stdout with `type` field in each.

## Test Cases

### 1. Full interview round-trip via JSON protocol

1. Run: `echo -e '{"type":"answer","text":"Improve RAG accuracy"}\n{"type":"answer","text":"Accuracy score"}\n{"type":"answer","text":"Under 5 seconds latency"}\n{"type":"answer","text":"Swap retrievers, add rerankers"}\n{"type":"answer","text":"50 QA pairs in benchmark.json"}\n{"type":"answer","text":"$10 budget, 20 iterations"}\n{"type":"answer","text":"yes"}' | autoagent new --json 2>/dev/null | jq .`
2. Verify each line is valid JSON with a `type` field
3. Verify `prompt` messages appear for all 6 phases (goal, metrics, constraints, search_space, benchmark, budget)
4. Verify a `confirm` message appears with a `summary` field
5. Verify the final message is `{"type":"complete",...}` with `config` and `context` fields
6. **Expected:** 8+ JSON lines (6 prompts + 1 confirm + 1 complete, plus possible status messages), `config.json` and `context.md` written to `.autoagent/`

### 2. Vague input triggers follow-up probe

1. Run `autoagent new --json 2>/dev/null` interactively
2. On first prompt, send: `{"type":"answer","text":"idk"}`
3. **Expected:** A second `prompt` message appears for the same phase with a follow-up question (not immediately moving to the next phase)

### 3. Abort mid-interview

1. Run `autoagent new --json 2>/dev/null` interactively
2. After receiving first prompt, send: `{"type":"abort"}`
3. **Expected:** Process exits with non-zero exit code, no `complete` event, no files written to `.autoagent/`

### 4. EOF on stdin

1. Run: `echo '{"type":"answer","text":"test"}' | autoagent new --json 2>/dev/null`
2. **Expected:** Process exits gracefully (no Python traceback on stderr) after stdin is exhausted

### 5. stderr redirect in JSON mode

1. Run: `autoagent new --json 2>stderr.txt` and pipe answers on stdin
2. **Expected:** stdout contains only valid JSON lines. `stderr.txt` contains human-readable banners/headers that would normally appear on stdout in interactive mode.

### 6. `/autoagent new` in pi — happy path

1. Open pi in the project directory
2. Type `/autoagent new` and press Enter
3. **Expected:** A native pi input dialog appears with the first interview question (about the project goal)
4. Type an answer and press Enter
5. **Expected:** Subsequent dialogs appear for metrics, constraints, search space, benchmark, and budget
6. On the confirmation dialog, select "Yes"
7. **Expected:** A success notification appears. `config.json` and `context.md` exist in `.autoagent/`

### 7. `/autoagent new` in pi — user cancels with Escape

1. Open pi in the project directory
2. Type `/autoagent new` and press Enter
3. When the first input dialog appears, press Escape
4. **Expected:** Interview terminates cleanly. No error notification. No files written to `.autoagent/`. Python subprocess is killed (no orphan process).

### 8. `/autoagent new` in pi — subprocess crash

1. Temporarily break the Python CLI (e.g., rename `src/autoagent/cli.py` or corrupt PATH)
2. Type `/autoagent new` in pi
3. **Expected:** An error/warning notification appears indicating the interview subprocess failed, with diagnostic context (not a silent failure)
4. Restore the CLI

## Edge Cases

### Confirmation rejection (user says No)

1. Complete all 6 phases via `--json` protocol
2. On confirm message, send: `{"type":"answer","text":"no"}`
3. **Expected:** Interview restarts from the beginning (new prompt for phase 1), not a complete event

### Very long answers

1. Send a prompt answer with 500+ characters
2. **Expected:** Protocol handles it without truncation or parsing errors — the full text appears in the resulting config

### Invalid JSON on stdin

1. Run `autoagent new --json` and send a malformed line (e.g., `not json`)
2. **Expected:** Process exits with an error event or non-zero exit code — does not hang or corrupt state

## Failure Signals

- Python traceback appearing on stdout (should only be on stderr in `--json` mode)
- Stale/orphan Python processes after interview cancellation (`ps aux | grep "autoagent new"`)
- Missing `type` field in any JSON line on stdout
- `complete` event with empty or malformed `config` object
- Pi showing no dialog after `/autoagent new` (extension not loaded or subprocess not spawning)
- Silent failure — no notification after subprocess crash

## Requirements Proved By This UAT

- R006 — `/autoagent new` works as a pi TUI command with native dialogs (test cases 6, 7)
- R007 — Full 6-phase interview with vague-input follow-ups works through JSON protocol (test cases 1, 2)

## Not Proven By This UAT

- Real LLM quality of interview questions (tests use MockLLM — interview substance depends on LLM provider)
- Performance under slow network/LLM conditions (no latency simulation)
- Concurrent interview + optimization run (S03 scope — `/autoagent stop` and status wiring)

## Notes for Tester

- Test cases 1-5 can be run without pi — they test the Python protocol directly from terminal
- Test cases 6-8 require pi with the extension loaded — verify `.pi/extensions/autoagent/index.ts` is discovered
- The interview uses MockLLM by default — follow-up probes will be generic, not contextually intelligent
- If `.autoagent/` already exists, the JSON mode skips overwrite confirmation (writes directly) — delete it between test runs for clean state
