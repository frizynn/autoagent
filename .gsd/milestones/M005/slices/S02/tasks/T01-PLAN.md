---
estimated_steps: 5
estimated_files: 3
---

# T01: Python `--json` interview protocol

**Slice:** S02 — Interview Overlay with JSON Protocol
**Milestone:** M005

## Description

Add `--json` flag to `autoagent new` that wraps the existing `InterviewOrchestrator` with JSON stdin/stdout I/O functions. The orchestrator logic stays untouched — only the I/O layer changes. This establishes the bidirectional protocol contract that the TypeScript extension will consume.

The protocol is strict request-response: Python writes one JSON line, waits for one JSON line back. No interleaving possible. Messages:
- `{"type":"prompt","phase":"goal","question":"..."}` — Python asks
- `{"type":"answer","text":"..."}` — TypeScript answers
- `{"type":"confirm","summary":"..."}` — confirmation phase
- `{"type":"status","message":"..."}` — informational (no response expected)
- `{"type":"complete","config":{...},"context":"..."}` — interview done
- `{"type":"error","message":"..."}` — Python-side error
- `{"type":"abort"}` — TypeScript cancels (sent to stdin)

## Steps

1. Add `--json` flag to the `new` subparser in `_build_parser()` (mirrors `--jsonl` pattern from D065)
2. In `cmd_new()`, when `--json` is active: skip the overwrite confirmation (TUI side can check), redirect `builtins.print` to stderr (same pattern as `cmd_run --jsonl`)
3. Create `_json_input_fn(phase: str)` — a closure that emits a `prompt` JSON line to stdout with flush, then reads one line from stdin, parses as JSON, handles `{"type":"abort"}` by raising `KeyboardInterrupt`, returns the `text` field
4. Create `_json_print_fn` — emits `{"type":"status","message":"..."}` to stdout for non-question text (phase headers, LLM probes). For the confirmation summary, emit `{"type":"confirm","summary":"..."}` instead
5. Wire the JSON I/O functions into `InterviewOrchestrator(llm=llm, input_fn=json_input_fn, print_fn=json_print_fn)` and on completion emit `{"type":"complete","config":{...},"context":"..."}` to stdout. Handle the confirmation phase: the existing `_run_confirmation()` uses `input_fn` and `print_fn` — the JSON print_fn needs to detect when it's emitting the confirmation summary vs regular status text. Approach: track interview phase state to determine message type.
6. Write `tests/test_cli_json_interview.py` with tests covering: basic protocol round-trip (all 6 phases + confirmation + complete), vague input triggering follow-up probe, user abort via `{"type":"abort"}`, `EOFError` from stdin (subprocess killed), stderr redirect of print, protocol message format validation, completion event contains valid config JSON

## Must-Haves

- [ ] `--json` flag accepted by `autoagent new`
- [ ] Each interview phase emits exactly one `prompt` JSON line before blocking on stdin
- [ ] Vague-input follow-up probes work through the protocol (probe appears as a new prompt)
- [ ] Confirmation phase uses `confirm` message type
- [ ] Completion emits `complete` with full config and context
- [ ] `builtins.print` redirected to stderr in `--json` mode
- [ ] `EOFError` on stdin handled gracefully (exit with non-zero, no traceback)
- [ ] Abort message from TypeScript side triggers clean exit

## Verification

- `pytest tests/test_cli_json_interview.py -v` — ≥8 tests pass
- `pytest tests/ -q` — 479+ tests pass, no regressions
- Manual: `echo '...' | autoagent new --json 2>/dev/null` produces valid JSON lines on stdout

## Observability Impact

- Signals added: JSON protocol messages on stdout — structured, machine-parseable interview telemetry
- How a future agent inspects this: pipe `autoagent new --json 2>/dev/null` to `jq .` for protocol debugging
- Failure state exposed: `{"type":"error","message":"..."}` emitted on Python-side failures; non-zero exit code on abort

## Inputs

- `src/autoagent/interview.py` — InterviewOrchestrator with `input_fn`/`print_fn` injection (the key leverage point)
- `src/autoagent/cli.py` — `cmd_new()` function, `--jsonl` pattern from `cmd_run()` for reference
- S01 summary — `builtins.print` stderr redirect pattern, `--jsonl` flag wiring

## Expected Output

- `src/autoagent/cli.py` — `cmd_new()` extended with `--json` mode, `_build_parser()` extended with `--json` flag
- `tests/test_cli_json_interview.py` — new test file with ≥8 tests validating the JSON interview protocol
- Protocol contract established: TypeScript side can spawn `autoagent new --json` and drive the interview via strict request-response JSON lines
