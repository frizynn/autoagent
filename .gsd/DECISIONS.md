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
| D011 | M001/S01 | pattern | MetricsSnapshot immutability | Frozen dataclass | Snapshots are point-in-time records — mutations would break collector aggregation and audit trail | No |
| D012 | M001/S01 | pattern | Cost calculation as standalone function | `calculate_cost()` free function with optional config override | Reusable by any provider without coupling to collector; override dict keeps pricing testable and user-configurable | Yes — if dynamic pricing API needed |
| D013 | M001/S01 | pattern | Protocol aliases (LLM, Retriever) | Module-level aliases for LLMProtocol/RetrieverProtocol | Slice plan expects `from autoagent.primitives import LLM, Retriever` — aliases satisfy that without renaming the Protocol classes | Yes — could rename protocols directly |
| D014 | M001/S01 | pattern | Pipeline module loading via compile()+exec() | Source-level compile instead of importlib.util.spec_from_file_location | importlib's SourceFileLoader uses bytecode cache (.pyc) which returns stale code when the same path is loaded twice in one process — compile()+exec() reads source directly, guaranteeing fresh loads | No |
| D015 | M001/S02 | pattern | Config format | JSON instead of YAML | Boundary map says config.yaml but YAML requires pyyaml dependency. JSON is stdlib-only (`json` module), fully round-trippable, and preserves zero-dependency constraint. TOML has stdlib read (tomllib) but no stdlib write. | Yes — if config complexity demands YAML |
| D016 | M001/S02 | pattern | CLI framework | argparse (stdlib) instead of click/typer | Zero runtime dependencies constraint. argparse handles 3 subcommands fine. | Yes — if CLI grows significantly |
| D017 | M001/S02 | pattern | R006 reinterpretation | Python CLI via argparse, not PI SDK | PI is a Node.js agent harness with no Python SDK. R006 "PI-based CLI" reinterpreted as standard Python CLI with GSD-2-style commands. | No |
| D018 | M001/S03 | pattern | Per-example timeout implementation | ThreadPoolExecutor with shutdown(wait=False, cancel_futures=True) | Context manager's `__exit__` blocks waiting for timed-out threads. Explicit shutdown with wait=False returns immediately after timeout, keeping evaluation wall-clock time proportional to timeout, not pipeline execution time. | No |
| D019 | M001/S03 | pattern | Custom scorer loading | compile()+exec() matching pipeline loader pattern | Consistent with D014 — same dynamic module loading approach for scorers as for pipelines. No caching, fresh load every time. | No |
| D020 | M001/S04 | pattern | EvaluationResult storage format | Dict (not object) in ArchiveEntry JSON | Frozen dataclasses can't be deserialized from JSON directly. Store as dict, reconstruct on demand via evaluation_result_obj property. Keeps JSON files human-readable and self-contained. | Yes — if schema migration is needed |
| D021 | M001/S04 | pattern | Corrupted archive entry handling | Raise ValueError with filename context | Silent skipping would hide data loss. Explicit errors with filename let operators identify and fix corrupted entries. Archive is append-only — corruption is always a bug. | No |
| D022 | M001/S05 | pattern | LLM response source extraction | Pick longest fenced code block | Multiple code blocks in LLM responses are common (explanations + code). Longest block is most likely the complete module. Fallback: treat entire response as source. | Yes — if structured output format used |
| D023 | M001/S05 | pattern | Pipeline source validation depth | Compile + exec into temp module + check run() callable | AST parse alone misses runtime issues (e.g., `run = 42` passes syntax but isn't callable). Exec into temp module catches these. | No |
| D024 | M001/S05 | pattern | First iteration always kept | best_score starts None; any score ≥ None → keep | First successful evaluation must be kept to establish a baseline. Comparing against None naturally handles this. | No |
| D025 | M001/S05 | pattern | MetaAgent failure archive entries | Zero-score EvaluationResult stubs with "proposal_error:" rationale | Archive entries must be structurally complete for query/filter. Stub results keep the schema consistent while marking failures clearly. | No |
| D026 | M001/S06 | pattern | Budget estimation method | Global average cost (total_cost / total_iterations) | More accurate for resumed runs than session-only average — uses full cost history across restarts. | Yes — if iteration costs vary widely |
| D027 | M001/S06 | pattern | Pipeline restoration on resume | Restore from archive's best kept entry, not disk | Disk may have stale/proposed source from mid-iteration crash. Archive is the source of truth for the last known-good pipeline. | No |
