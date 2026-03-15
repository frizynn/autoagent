---
estimated_steps: 5
estimated_files: 2
---

# T01: Implement LeakageChecker module with unit tests

**Slice:** S03 — Data Leakage Detection
**Milestone:** M003

## Description

Create the self-contained `leakage.py` module with `LeakageResult` frozen dataclass and `LeakageChecker` class. Two detection tiers per D046: exact-match blocking (AST string literal extraction + hash comparison) and fuzzy n-gram overlap warnings (word-level tokenization, Jaccard similarity). Comprehensive unit tests prove all detection paths.

## Steps

1. Create `src/autoagent/leakage.py` with:
   - `LeakageResult` frozen dataclass: `blocked: bool`, `exact_matches: int`, `fuzzy_warnings: list[str]`, `cost_usd: float`
   - `LeakageChecker` class with `__init__(self, fuzzy_threshold: float = 0.3)` and `check(self, benchmark: Benchmark, pipeline_source: str) -> LeakageResult`
   - Exact-match: `ast.parse()` pipeline source → `ast.walk()` collecting all `ast.Constant` string nodes → compare against serialized benchmark examples (`json.dumps(x, sort_keys=True)` and `str(x)` for each `example.input` and `example.expected`). Skip examples where both `str(input)` and `str(expected)` are < 10 chars.
   - Fuzzy: tokenize pipeline source and benchmark examples via `re.findall(r'\w+', text.lower())`, extract (3,4)-grams as tuples, compute Jaccard similarity (intersection/union of n-gram sets). Warn per example if overlap > `fuzzy_threshold`.
   - AST parse fallback: if `ast.parse()` raises `SyntaxError`, fall back to regex extraction of quoted strings (`r'''(["'])(.*?)\1'''` and triple-quote patterns).
   - `cost_usd` always 0.0 (forward-compatible for future LLM-assisted detection).
2. Create `tests/test_leakage.py` with tests:
   - Exact match: pipeline contains `"What is the capital of France?"` from benchmark → `blocked=True, exact_matches>=1`
   - No match: clean pipeline → `blocked=False, exact_matches=0, fuzzy_warnings=[]`
   - Fuzzy overlap: pipeline shares significant vocabulary with benchmark → `fuzzy_warnings` non-empty, `blocked=False`
   - Short example skip: benchmark with input "hi" and expected "hey" → not flagged even if present in source
   - Non-string data: benchmark with dict/list inputs → serialized and checked correctly
   - AST failure fallback: pipeline source with syntax errors → falls back to regex, still detects embedded strings
   - Empty benchmark (no examples) → `blocked=False`
   - Multiple exact matches → `exact_matches` counts correctly

## Must-Haves

- [ ] `LeakageResult` is `@dataclass(frozen=True)` per D011
- [ ] `leakage.py` imports nothing from `loop.py` or `archive.py`
- [ ] Exact match uses AST string literal extraction (not substring search)
- [ ] Fuzzy match never blocks — only appends to `fuzzy_warnings` (D046)
- [ ] Short examples (< 10 chars for both input and expected) skipped for exact match
- [ ] Non-string benchmark data serialized via `json.dumps(sort_keys=True)` before comparison
- [ ] Zero external dependencies — stdlib only

## Observability Impact

- **New logger:** `leakage.py` adds `logging.getLogger(__name__)` — emits INFO on check outcomes (blocked/passed, match counts), WARNING on AST parse fallback, DEBUG on per-example match details and Jaccard scores.
- **Inspection:** A future agent can inspect `LeakageResult` fields directly or read `leakage_check` dict from archive entries to understand why an iteration was blocked or warned.
- **Failure state:** AST fallback is visible via WARNING log. If no string literals are extracted (empty pipeline), the check passes cleanly with `exact_matches=0`.

## Verification

- `python3 -m pytest tests/test_leakage.py -v` — all unit tests pass
- Confirm `leakage.py` has no imports from `loop`, `archive`, `cli`, or `state` modules

## Inputs

- `src/autoagent/benchmark.py` — `Benchmark` and `BenchmarkExample` classes (input data for checker)
- `src/autoagent/verification.py` — pattern reference for self-contained module with frozen result dataclass
- S03-RESEARCH.md — detection strategy, thresholds, pitfalls

## Expected Output

- `src/autoagent/leakage.py` — complete `LeakageChecker` + `LeakageResult` module, self-contained, stdlib-only
- `tests/test_leakage.py` — comprehensive unit tests covering all detection paths and edge cases
