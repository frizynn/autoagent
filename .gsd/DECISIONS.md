# Decisions Register

<!-- Append-only. Never edit or remove existing rows.
     To reverse a decision, add a new row that supersedes it.
     Read this file at the start of any planning or research phase. -->

| # | When | Scope | Decision | Choice | Rationale | Revisable? |
|---|------|-------|----------|--------|-----------|------------|
| D001 | M001 | arch | Pipeline mutation scope | Single file (pipeline.py) | Mirrors autoresearch's train.py constraint — prevents search space explosion, keeps diffs reviewable | No |
| D002 | M001 | arch | State storage | Disk-only (.autoagent/ directory) | Crash-recoverable, human-readable, no database dependency — GSD-2 pattern | No |
| D003 | M001 | arch | Archive format | Directory of JSON files + pipeline snapshots | Human-readable, crash-recoverable, git-friendly — one file per iteration | Yes — if performance degrades at scale |
| D004 | M001 | pattern | Meta-agent LLM provider | User's coding agent subscription (Claude Code Max, Codex, etc.) | Provider-agnostic like GSD-2 — system doesn't impose LLM choice | No |
| D005 | M001 | arch | Search strategy autonomy | Meta-agent decides structural vs parameter freely | No explicit phase switching — ADAS-like autonomous decision-making per user preference | No |
| D006 | M001 | arch | Evaluation approach | Multi-metric vector (primary + latency + tokens + cost) | Pareto evaluation prevents reward hacking — user's top concern | No |
| D007 | M001 | pattern | Budget model | Hard dollar ceiling with auto-pause | Simple, predictable — user said "hard ceiling" explicitly | No |
| D008 | M001 | arch | TLA+ verification scope | All pipelines (sequential and concurrent) | User chose universal gate, not concurrency-only — lightweight properties for sequential, full model-checking for concurrent | Yes — if overhead is too high for sequential |
| D009 | M001 | pattern | Data leakage checking | Every evaluation step, not one-time | User's exact words: "ALWAYS CHECK IN EVERY STEP BEFORE RUNNING BENCHMARKS" | No |
| D010 | M001 | scope | Primitive abstraction depth | Thin wrappers with instrumentation | Avoid becoming a framework (R030 anti-feature) — primitives add measurement, not behavior | Yes — if users need richer abstractions |
