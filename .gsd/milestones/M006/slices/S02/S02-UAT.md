# S02: Conversational Setup + Minimal UX — UAT

**Milestone:** M006
**Written:** 2026-03-15

## UAT Type

- UAT mode: mixed (artifact-driven for content contracts, live-runtime for conversational quality)
- Why this mode is sufficient: Content contracts can be verified by grep. The go guard is a code path testable by file presence. Conversational quality requires a real LLM interaction which is out of scope for automated verification.

## Preconditions

- TUI builds cleanly (`cd tui && npx tsc --noEmit` — zero errors)
- No `.autoagent/` directory in the test working directory (for MODE A tests)
- For MODE B tests: `.autoagent/` with pipeline.py and prepare.py present

## Smoke Test

Run `bash .gsd/milestones/M006/slices/S02/verify-s02.sh` from repo root — all 12 checks pass.

## Test Cases

### 1. system.md prepare.py output contract

1. Open `tui/src/resources/extensions/autoagent/prompts/system.md`
2. Locate MODE A step 2
3. **Expected:** Contains exact format `score: X.XXXX` and shows `total_examples`, `passed`, `failed` output lines

### 2. system.md prepare.py skeleton completeness

1. Read the skeleton code block in MODE A step 2
2. **Expected:** Contains `test_cases` list, `def check(result, expected)`, `def eval()`, `if __name__ == "__main__"` with argparse. Approximately 25 lines, not bloated.

### 3. system.md pipeline.py contract

1. Locate MODE A step 3
2. **Expected:** Contains `def run(input_data, context) -> dict` and specifies return value must include `{"output": ...}`

### 4. system.md baseline validation

1. Locate MODE A step 5
2. **Expected:** Instructs running `cd .autoagent && python prepare.py`, checking score is between 0.1 and 0.9, with guidance for score = 0.0 (broken) and score = 1.0 (too easy)

### 5. system.md "Copy program.md" step removed

1. Search system.md for "Copy program.md" or "Copy `program.md`"
2. **Expected:** Not found. The old step 4 is gone. program.md is handled by the go command's bundled fallback.

### 6. system.md completion criteria

1. Locate MODE A step 6
2. **Expected:** Lists all conditions: prepare.py exists and runs, pipeline.py exists and defines run(), results.tsv exists with header, baseline score 0.1–0.9

### 7. go command rejects without pipeline.py

1. Start the TUI (or inspect index.ts code path)
2. Ensure no `.autoagent/pipeline.py` exists
3. Run `/autoagent go`
4. **Expected:** Notification appears with "Project not ready — missing pipeline.py" (and prepare.py if also missing). No experiment loop dispatched.

### 8. go command rejects without prepare.py

1. Create `.autoagent/pipeline.py` but NOT `.autoagent/prepare.py`
2. Run `/autoagent go`
3. **Expected:** Notification appears with "Project not ready — missing prepare.py". No experiment loop dispatched.

### 9. go command dispatches when both files exist

1. Create `.autoagent/pipeline.py` and `.autoagent/prepare.py`
2. Run `/autoagent go`
3. **Expected:** "Starting autonomous experiment loop..." notification. Agent receives program.md content and begins following it.

## Edge Cases

### Both files missing

1. No `.autoagent/` directory at all
2. Run `/autoagent go`
3. **Expected:** Notification says "missing pipeline.py and prepare.py"

### Only results.tsv missing (not a blocker)

1. `.autoagent/pipeline.py` and `.autoagent/prepare.py` exist but no results.tsv
2. Run `/autoagent go`
3. **Expected:** go command dispatches normally — results.tsv is not part of the go guard (it's created during setup, the LLM will create it if missing)

## Failure Signals

- `verify-s02.sh` reports any FAIL — content contract broken
- `tsc --noEmit` has errors — TypeScript compilation broken
- go command dispatches without pipeline.py/prepare.py — guard not working
- system.md still mentions "Copy program.md" — old step not removed
- Skeleton in system.md doesn't include `score: X.XXXX` format — output contract missing

## Requirements Proved By This UAT

- R102 (Conversational Setup) — system.md provides enough structure for the LLM to guide setup, but full validation requires real LLM conversations
- R106 (Minimal Command Surface) — go command contextually refuses without project files, showing setup guidance instead of a generic error

## Not Proven By This UAT

- Actual conversational quality — whether a real LLM produces correct prepare.py files from the enriched MODE A prompt (requires live testing)
- End-to-end experiment loop — that's S01's scope and was already verified
- Multi-experiment branches and dashboard — S03 scope

## Notes for Tester

- The verify-s02.sh script is the primary automated gate. If it passes, the content contracts are solid.
- For the go command guard tests (7-9), you need the TUI running. Alternatively, read index.ts and trace the code path — the guard is at the top of the `case "go"` block.
- The skeleton quality is a judgment call — look at it and ask: would an LLM given this skeleton produce a correct prepare.py? The structure should be clear and the output format unambiguous.
