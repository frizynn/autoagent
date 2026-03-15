# S03: Data Leakage Detection — Research

**Date:** 2026-03-14

## Summary

S03 adds a data leakage gate to the optimization loop, directly implementing R009 ("ALWAYS CHECK IN EVERY STEP BEFORE RUNNING BENCHMARKS"). The gate inserts between TLA+ verification and evaluation — if leakage is detected, the iteration is discarded without burning eval tokens.

The implementation is pure Python with zero external dependencies. Two detection tiers per D046: exact-match blocking (hash-based — high precision, zero false positives) and fuzzy n-gram overlap warnings (configurable threshold — informational, not blocking). The `LeakageChecker` follows the same frozen-dataclass-result pattern as `TLAVerifier` and `ParetoResult`.

The codebase is well-prepared. `Benchmark` exposes `examples: list[BenchmarkExample]` where each has `.input` and `.expected`. Pipeline source is available as a string at the gate insertion point. `ArchiveEntry` already has optional dict fields for `tla_verification` and `pareto_evaluation` — adding `leakage_check` follows the identical pattern. The loop integration mirrors the TLA+ gate exactly: check → if blocked → discard with rationale → restore pipeline → continue.

## Recommendation

Implement `leakage.py` as a self-contained module with `LeakageChecker` class and `LeakageResult` frozen dataclass. Detection strategy:

1. **Exact match (blocks):** Hash each benchmark example's `(input, expected)` pair. Scan pipeline source for string literals that exactly match any example's input or expected value. Also check for serialized representations (JSON-encoded versions). If any exact match found → `blocked=True`.

2. **Fuzzy n-gram overlap (warns):** Extract n-grams (n=3,4) from benchmark examples. Compute overlap ratio between pipeline source n-grams and benchmark n-grams. If overlap exceeds threshold → append to `fuzzy_warnings`. Never blocks — advisory only per D046.

No LLM calls needed for the mechanical checks. The `cost_usd` field exists for forward-compatibility (future LLM-assisted semantic leakage analysis) but will be 0.0 for now.

Loop integration: add `leakage_checker: LeakageChecker | None = None` parameter to `OptimizationLoop.__init__()`. Gate runs after TLA+ verification, before evaluation. Archive entries gain `leakage_check: dict | None` field.

## Don't Hand-Roll

| Problem | Existing Solution | Why Use It |
|---------|------------------|------------|
| String hashing | `hashlib` (stdlib) | SHA-256 for exact match dedup — fast, collision-resistant |
| N-gram extraction | Implement from scratch (~10 lines) | Too simple for a dependency — sliding window over tokens |
| Pipeline source parsing | String search + `ast.parse()` for string literal extraction | AST gives us all string literals in the pipeline without regex fragility |

## Existing Code and Patterns

- `verification.py` `TLAVerifier` — **Primary pattern to follow.** Self-contained module with Protocol for LLM, frozen result dataclass, class with `verify()` method. Same shape: `LeakageChecker` with `check()` returning `LeakageResult`. No imports from loop.py or archive.py.
- `pareto.py` — **Another pattern reference.** Pure functions, frozen `ParetoResult`, self-contained. Leakage detection is similarly pure — takes data in, returns decision out.
- `loop.py` L337-396 — **TLA+ gate integration point.** Leakage gate inserts at ~L397 (after TLA+ gate, before evaluation at L398). Follows identical pattern: check → if blocked → discard + archive + restore + continue.
- `archive.py` `ArchiveEntry` — **Needs new field.** Add `leakage_check: dict[str, Any] | None = None` alongside existing `tla_verification` and `pareto_evaluation`. Also update `from_dict()` to deserialize it.
- `archive.py` `Archive.add()` — **Needs new parameter.** Add `leakage_check` kwarg, pass through to `ArchiveEntry`.
- `benchmark.py` `BenchmarkExample` — **Input data.** Frozen dataclass with `.input: Any` and `.expected: Any`. These are the values to check for leakage in pipeline source.
- `loop.py` `OptimizationLoop.__init__()` — **Constructor extension.** Add `leakage_checker` parameter following `tla_verifier` pattern.
- `cli.py` `cmd_run()` L166 — **CLI wiring point.** Currently doesn't wire TLAVerifier either — leakage checker follows same pattern (optional, constructed when available).
- `test_loop_verification.py` — **Test pattern to follow.** Tests TLA+ gate integration in the loop with mock verifier. Leakage tests should follow identical structure.

## Constraints

- **Zero Python package dependencies** — All detection is stdlib-only (`hashlib`, `ast`, `re`, string operations). No sklearn, no nltk.
- **Frozen dataclass pattern** — `LeakageResult` must be `@dataclass(frozen=True)` per project convention (D011 pattern).
- **Self-contained module** — `leakage.py` must not import from `loop.py` or `archive.py` (same rule as verification.py, pareto.py).
- **Archive backward compatibility** — New `leakage_check` field must be optional with `None` default. `from_dict()` must handle missing key via `.get()`.
- **Budget tracking** — `LeakageResult.cost_usd` tracked in loop's `total_cost`. Currently 0.0 (no LLM calls), but the accounting must be wired.
- **D009 — every evaluation step** — The check runs on every iteration, not once at startup. Pipeline source can change each iteration and may introduce contamination.
- **D046 — exact blocks, fuzzy warns** — Hard separation between the two tiers. No configuration to make fuzzy matching block.

## Common Pitfalls

- **Checking only string literals** — Pipeline might embed benchmark data as variables, list comprehensions, or computed values. AST string literal extraction catches explicit embedding but not computed contamination. This is acceptable for the mechanical check tier — semantic analysis is a future enhancement.
- **N-gram tokenization sensitivity** — Splitting on whitespace vs. character-level n-grams changes overlap ratios dramatically. Use word-level tokenization (split on whitespace + punctuation) for interpretable thresholds.
- **False positives from short examples** — Benchmark examples with 1-2 word inputs (e.g., "hello") will match pipeline source trivially. Mitigate: skip exact-match check for inputs shorter than a minimum length (e.g., 10 chars). Or require the match to be a string literal in AST, not just a substring.
- **Serialization variations** — `"hello world"` vs `'hello world'` vs `"""hello world"""` in Python source. AST string literal extraction normalizes these. For non-AST scanning, normalize before comparison.
- **Large benchmarks** — 1000+ examples means 1000+ hashes. This is fine — hash comparison is O(n) and fast. N-gram computation is heavier but still tractable for source files.
- **Non-string benchmark data** — `.input` and `.expected` can be dicts or lists. Must serialize to string (via `json.dumps` or `str()`) before hashing/matching. Use canonical serialization (`sort_keys=True`) for dicts.

## Open Risks

- **Computed contamination** — A pipeline that reconstructs benchmark answers from partial data won't be caught by string matching. This is a known limitation of mechanical checking. R009's "could be via prompting or mechanical checks" leaves room for future LLM-assisted detection.
- **Fuzzy threshold tuning** — The n-gram overlap threshold for warnings needs empirical tuning. Starting with 0.3 (30% overlap) as warning threshold — can adjust based on false positive rate in tests.
- **Pipeline source vs runtime data** — The check examines pipeline source code, not runtime behavior. A pipeline that fetches benchmark data from a URL at runtime wouldn't be caught. This is acceptable — the gate catches the most common contamination vector (data embedded in code).
- **`cost_usd` forward-compatibility** — Currently 0.0, but if LLM-assisted analysis is added later, the budget accounting is already wired. No risk, just noting the design intent.

## Skills Discovered

| Technology | Skill | Status |
|------------|-------|--------|
| Data leakage detection | n/a | none found — domain-specific, stdlib implementation |
| Python AST analysis | n/a | stdlib `ast` module, no skill needed |

No relevant skills to suggest — the implementation is straightforward stdlib Python with no external frameworks.

## Sources

- Codebase analysis: `src/autoagent/verification.py` (pattern), `src/autoagent/pareto.py` (pattern), `src/autoagent/loop.py` (integration point), `src/autoagent/archive.py` (storage), `src/autoagent/benchmark.py` (data source)
- Architecture decisions: D009 (every-step checking), D046 (exact blocks, fuzzy warns), D043 (graceful degradation pattern)
- Requirements: R009 (data leakage guardrail — primary owner)
- M003-RESEARCH.md: leakage detection approach, pitfalls (false positives, threshold tuning)
