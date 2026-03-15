---
estimated_steps: 5
estimated_files: 2
---

# T01: Build MetaAgent with prompt construction and source extraction

**Slice:** S05 — The Optimization Loop
**Milestone:** M001

## Description

Build `MetaAgent` — the component that reads archive history, constructs a mutation prompt, calls an LLM, and extracts valid pipeline.py source from the response. This is the highest-risk component in S05: the proof strategy requires runnable mutations ≥50% of the time, which means robust source extraction (markdown fence stripping, compile validation, run callable check) is critical.

The meta-agent uses `OpenAILLM` (or `MockLLM` for tests) from the primitives layer for its own LLM calls, with a separate `MetricsCollector` so its cost is tracked independently from pipeline evaluation cost.

## Steps

1. Create `src/autoagent/meta_agent.py` with:
   - `ProposalResult` dataclass (proposed_source, rationale, cost_usd, success, error)
   - `MetaAgent` class accepting an LLM instance, goal string, and optional config
   - `_build_prompt()` method: takes current pipeline source, archive entries (top-K kept sorted by score, recent N discards), benchmark description, goal; returns a structured system+user prompt instructing the LLM to output a complete pipeline.py with `def run(input_data, primitives=None)` signature
   - `_extract_source()` method: strips ```python fences, handles multiple code blocks (take the longest), strips leading/trailing whitespace
   - `_validate_source()` method: `compile()` the source; check the compiled module has a callable `run`; return error string or None
   - `propose()` method: calls _build_prompt with archive+pipeline, calls LLM.complete(), extracts source, validates; returns ProposalResult with success/failure
   - Cost tracking via the LLM instance's MetricsCollector

2. Handle edge cases in extraction:
   - Response with no code block → treat entire response as source (may fail validation)
   - Response with multiple code blocks → use the longest one (most likely the full pipeline)
   - Empty response → ProposalResult(success=False, error="empty response")

3. Handle validation edge cases:
   - Source that compiles but has no `run` → ProposalResult(success=False, error="missing run() function")
   - Source where `run` isn't callable → same treatment
   - SyntaxError from compile → ProposalResult(success=False, error="syntax error: {detail}")

4. Write comprehensive unit tests in `tests/test_meta_agent.py`:
   - Prompt construction includes goal, current pipeline, archive history
   - Source extraction: clean source (no fences), single fenced block, multiple fenced blocks (picks longest), empty response
   - Validation: valid pipeline, syntax error, missing run, run not callable
   - Full propose() flow with MockLLM returning valid pipeline source
   - Full propose() flow with MockLLM returning invalid Python
   - Cost tracking: MetricsCollector on the LLM captures the meta-agent call

5. Verify all tests pass and no regressions in full suite

## Must-Haves

- [ ] MetaAgent.propose() returns ProposalResult with valid pipeline source when LLM returns good code
- [ ] MetaAgent.propose() returns ProposalResult(success=False) with error when LLM returns invalid Python
- [ ] Markdown fence stripping handles ```python ... ``` blocks correctly
- [ ] Compile validation catches syntax errors before evaluation
- [ ] Run callable validation catches missing/non-callable run
- [ ] Prompt includes goal, current pipeline source, and archive history context
- [ ] Meta-agent LLM cost is tracked via its own MetricsCollector, not mixed with pipeline costs

## Verification

- `pytest tests/test_meta_agent.py -v` — all tests pass
- `python -c "from autoagent.meta_agent import MetaAgent, ProposalResult"` — boundary contract importable
- No regressions: `pytest tests/ -v` shows all existing tests still pass

## Observability Impact

- **New signal:** `ProposalResult.error` — structured error string when `success=False` (syntax errors, missing run, empty response). Future agents inspect this to understand why a mutation was discarded.
- **New signal:** `ProposalResult.cost_usd` — per-proposal LLM cost, read from the MetaAgent's own MetricsCollector. Enables cost attribution separate from pipeline evaluation.
- **Failure visibility:** All extraction/validation failures produce a `ProposalResult` with `success=False` and a descriptive `error` — never silent swallowing. Compile errors include the Python error detail.
- **Inspection surface:** `MetaAgent._build_prompt()` output is a plain string — can be logged/inspected to debug prompt quality without running the LLM.

## Inputs

- `src/autoagent/primitives.py` — MockLLM for testing, OpenAILLM for production, MetricsCollector for cost tracking
- `src/autoagent/archive.py` — Archive.query() for reading history, ArchiveEntry for prompt context
- `tests/fixtures/toy_pipeline.py` — reference for valid pipeline.py format

## Expected Output

- `src/autoagent/meta_agent.py` — MetaAgent class with propose(), ProposalResult dataclass
- `tests/test_meta_agent.py` — Unit tests covering prompt construction, extraction, validation, and end-to-end propose flow
