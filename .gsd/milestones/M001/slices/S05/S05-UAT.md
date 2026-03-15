# S05: The Optimization Loop — UAT

**Milestone:** M001
**Written:** 2026-03-14

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: The optimization loop is fully testable via pytest with MockLLM — real LLM calls are a manual verification for mutation quality, not loop correctness

## Preconditions

- Python 3.11+ with venv activated (`.venv/bin/python`)
- Project dependencies installed (`pip install -e .`)
- Working directory: project root
- All upstream slices (S01–S04) passing: `pytest tests/ -v` shows 173 passed

## Smoke Test

Run `pytest tests/test_loop.py tests/test_meta_agent.py -v` — all 35 tests pass.

## Test Cases

### 1. MetaAgent prompt includes archive history

1. Create a MetaAgent with MockLLM and goal "improve accuracy"
2. Call `_build_prompt()` with current source, a kept archive entry (score=0.8), and a discarded entry
3. **Expected:** Prompt contains the goal string, current pipeline source, kept entry's score and rationale, discard entry's rationale. System instructions mention outputting a complete Python module with `def run`.

### 2. MetaAgent extracts source from fenced markdown

1. Configure MockLLM to return a response wrapped in ` ```python\ndef run(input_data, primitives=None):\n    return {"answer": "test"}\n``` `
2. Call `meta_agent.propose()`
3. **Expected:** `ProposalResult.success` is True, `proposed_source` contains `def run(input_data` without markdown fence markers

### 3. MetaAgent rejects invalid Python

1. Configure MockLLM to return `def run(: broken syntax`
2. Call `meta_agent.propose()`
3. **Expected:** `ProposalResult.success` is False, `error` contains "syntax error"

### 4. MetaAgent rejects missing run function

1. Configure MockLLM to return valid Python without a `run` function (e.g., `x = 42`)
2. Call `meta_agent.propose()`
3. **Expected:** `ProposalResult.success` is False, `error` contains "missing run"

### 5. MetaAgent tracks cost independently

1. Create MetaAgent with a MockLLM that has its own MetricsCollector
2. Call `propose()` twice
3. **Expected:** `ProposalResult.cost_usd` reflects incremental cost per call, not cumulative

### 6. Loop runs ≥3 iterations with correct keep/discard

1. Create OptimizationLoop with max_iterations=5 and a SequentialMockMetaAgent that returns pipelines with scores [0.5, 0.3, 0.8, 0.6, 0.9]
2. Run the loop
3. **Expected:** 5 archive entries exist. Entries with scores 0.5 (first, always kept), 0.8, 0.9 are kept. Entries with scores 0.3, 0.6 are discarded. `state.best_iteration_id` points to the 0.9 iteration.

### 7. Loop persists state after each iteration

1. Run loop with max_iterations=3
2. After completion, read state from disk
3. **Expected:** `current_iteration` equals 3, `phase` is "completed", `total_cost_usd` > 0, `best_iteration_id` is set

### 8. Loop handles MetaAgent failures gracefully

1. Create a mock MetaAgent that fails on iteration 2 (returns ProposalResult with success=False)
2. Run loop with max_iterations=3
3. **Expected:** All 3 iterations complete. Iteration 2 is archived as discard with rationale starting with "proposal_error:". Pipeline on disk still reflects the best successful iteration.

### 9. Pipeline on disk reflects current best

1. Run loop with max_iterations=3 where iteration 1 scores 0.7 and iteration 2 scores 0.4
2. Read pipeline.py from disk after loop completes
3. **Expected:** Pipeline.py content matches iteration 1's source (the best), not iteration 2's (the discard that was reverted)

### 10. CLI --max-iterations flag works

1. Run `autoagent run --help`
2. **Expected:** Output includes `--max-iterations` option with description

## Edge Cases

### Empty archive (first iteration)

1. Start loop with no archive entries and no prior iterations
2. **Expected:** First iteration runs successfully. MetaAgent receives empty history in prompt. First successful evaluation is always kept regardless of score.

### All proposals fail

1. Create a mock MetaAgent that always returns success=False
2. Run loop with max_iterations=3
3. **Expected:** 3 discard entries in archive. Pipeline on disk is unchanged from initial. best_iteration_id remains None or initial.

### Multiple fenced code blocks in LLM response

1. Configure MockLLM to return a response with two fenced code blocks — a short one and a longer one containing `def run`
2. Call `meta_agent.propose()`
3. **Expected:** Extraction picks the longest code block (the one with `def run`)

## Failure Signals

- Any test in `test_loop.py` or `test_meta_agent.py` fails
- `pytest tests/ -v` shows regressions in upstream test files
- Archive entries missing rationale, metrics, or decision fields
- State file shows `phase: "running"` after loop completion (should be "completed")
- Lock file persists after loop completion (should be released)
- Pipeline on disk doesn't match the best-scoring iteration's source

## Requirements Proved By This UAT

- R001 — Autonomous optimization loop runs ≥3 iterations with keep/discard decisions
- R002 — Single-file mutation constraint enforced (only pipeline.py written/restored)
- R004 — Every iteration (success or failure) archived with metrics and rationale
- R008 — Every iteration evaluated against benchmark

## Not Proven By This UAT

- Real LLM mutation quality (≥50% valid proposals) — requires manual test with OpenAI API key
- Budget ceiling and auto-pause — deferred to S06
- Crash recovery (kill/restart/resume) — deferred to S06
- Fire-and-forget overnight operation — deferred to S06

## Notes for Tester

- All test cases can be verified by running `pytest tests/test_meta_agent.py tests/test_loop.py -v` — the test suite covers every case above
- To manually verify real LLM integration, set OPENAI_API_KEY and modify cmd_run to use OpenAILLM instead of MockLLM, then run `autoagent init && autoagent run --max-iterations 3` with a toy benchmark
- The SequentialMockMetaAgent pattern in test_loop.py is worth reading — it shows how deterministic test scenarios are constructed
