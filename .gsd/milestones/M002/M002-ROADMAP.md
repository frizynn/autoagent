# M002: Search Intelligence

**Vision:** Transform the working-but-dumb optimization loop into a genuinely intelligent search process — structural mutations, parameter tuning, archive compression that scales, and cold-start generation from nothing.

## Success Criteria

- Cold-start: `autoagent run` with no initial pipeline.py generates a first pipeline from goal + benchmark and improves it over 10+ iterations
- Structural search: the meta-agent proposes topology changes (component swaps, pattern introductions) not just parameter tweaks, and at least one structural change improves metrics
- Archive at 50+ iterations produces coherent, context-window-fitting summaries (~3K tokens) that preserve top-K results, failure clusters, and unexplored regions
- Exploration/exploitation: when scores plateau, the meta-agent shifts toward structural exploration; when a structural improvement lands, it shifts toward parameter tuning — strategy signals visible in archive rationale
- Parameter optimization: the meta-agent can propose parameter-only mutations (prompt wording, temperature, chunk sizes) within a fixed topology

## Key Risks / Unknowns

- **Archive compression fidelity** — Compressing 200 iterations into a summary that preserves breakthrough signals is a lossy operation. If the wrong information is discarded, the meta-agent gets dumber as it runs longer. This is the most novel engineering in M002.
- **Structural search quality** — Can prompt-based structural mutations produce valid, genuinely novel topologies? Or will the meta-agent shuffle the same patterns? This is the core product risk.
- **Stagnation detection calibration** — What signals indicate the search is stuck? Plateau length, score variance, diff diversity — these need to be tuned without oscillating between explore/exploit.

## Proof Strategy

- Archive compression fidelity → retire in S01 by building the summarizer with explicit section structure (top-K, failure clusters, unexplored regions, trends) and proving it produces coherent summaries from 50+ synthetic archive entries that fit ~3K tokens
- Structural search quality → retire in S02 by enriching the meta-agent prompt with a component vocabulary and architectural pattern menu, then proving the meta-agent proposes topology changes visible in archive diffs
- Stagnation detection → retire in S03 by implementing sliding-window archive statistics and graduated prompt signals, then proving strategy shifts are visible in archive rationale over 20+ iterations

## Verification Classes

- Contract verification: pytest unit tests for summarizer output structure/token budget, component vocabulary injection, stagnation detection logic, cold-start pipeline validation
- Integration verification: `autoagent run` executing with enriched meta-agent prompt, archive summaries replacing raw entries past threshold, cold-start generating and optimizing from scratch
- Operational verification: none (same process model as M001)
- UAT / human verification: none

## Milestone Definition of Done

This milestone is complete only when all are true:

- All 4 slices are complete with passing tests
- Archive summarizer produces structured summaries from 50+ entries that fit context window
- Meta-agent prompt includes component vocabulary, archive summaries, and strategy signals
- Cold-start generates a valid pipeline from goal + benchmark and the loop improves it
- `autoagent run` exercises the full M002 stack end-to-end (cold-start or existing pipeline)
- All M001 tests still pass (no regressions)
- Final acceptance scenarios verified: cold-start 10+ iterations, structural mutation that improves score, archive compression at 50+ iterations

## Requirement Coverage

- Covers: R011 (structural search), R012 (parameter optimization), R013 (autonomous strategy), R015 (cold-start), R016 (archive compression), R024 (exploration/exploitation)
- Partially covers: none
- Leaves for later: R007 (M004), R009 (M003), R010 (M003), R014 (M003), R018 (M001 ongoing), R020 (M003), R021 (M003), R023 (M004)
- Orphan risks: none

## Slices

- [x] **S01: Archive Compression & Summarization** `risk:high` `depends:[]`
  > After this: `autoagent run` on a project with 50+ iterations uses LLM-generated archive summaries (~3K tokens) instead of raw entries in the meta-agent prompt. Summaries show top-K kept, failure clusters, unexplored regions, and score trends. Compression cost tracked in budget.

- [x] **S02: Structural Search & Component Vocabulary** `risk:high` `depends:[]`
  > After this: the meta-agent prompt includes a component vocabulary (available primitives + architectural patterns like RAG, CAG, debate, reflexion, ensemble, reranking) and produces topology-changing mutations visible in archive diffs — not just parameter tweaks.

- [ ] **S03: Strategy Selection & Parameter Optimization** `risk:medium` `depends:[S01,S02]`
  > After this: the meta-agent reads archive statistics (plateau length, score variance, structural diversity) and autonomously balances between structural exploration and parameter tuning. Strategy signals visible in archive rationale. Parameter-only mutations (prompt wording, temperature, chunk sizes) are a distinct mutation mode.

- [ ] **S04: Cold-Start Pipeline Generation** `risk:medium` `depends:[S02]`
  > After this: `autoagent run` with no initial pipeline.py generates a first pipeline from goal + benchmark using the component vocabulary, validates it compiles with a callable run(), and begins optimizing. Serves as integration proof — exercises full M002 stack from scratch.

## Boundary Map

### S01 (Archive Compression)

Produces:
- `ArchiveSummarizer` class (or module) with `summarize(entries: list[ArchiveEntry]) -> str` returning structured summary text
- Summary regeneration logic: regenerate every N iterations or when archive grows past last summary's coverage
- Compression cost tracking through existing `MetricsCollector` / `calculate_cost()` path
- `OptimizationLoop` integration: past iteration threshold, `_build_prompt()` receives summary string instead of raw `kept_entries`/`discarded_entries`

Consumes:
- `Archive.query()` and `ArchiveEntry` from M001
- `LLMProtocol` for summarization LLM calls
- `MetricsCollector` for cost tracking

### S01 → S03

Produces:
- Archive summary with score trend data and structural diversity signals that S03 uses for stagnation detection

### S02 (Structural Search)

Produces:
- Component vocabulary: structured text listing available primitives (`LLMProtocol`, `RetrieverProtocol`) and architectural patterns (RAG, CAG, debate, reflexion, ensemble, reranking) with usage examples
- Enriched `MetaAgent._build_prompt()` with vocabulary section and structural mutation guidance
- Pattern examples showing correct primitive usage in different topologies

Consumes:
- `MetaAgent._build_prompt()` from M001
- `primitives.py` protocol definitions

### S02 → S03

Produces:
- Component vocabulary and structural mutation capability that S03 balances against parameter optimization

### S02 → S04

Produces:
- Component vocabulary and pipeline generation examples that S04 uses for cold-start generation

### S03 (Strategy Selection)

Produces:
- Stagnation detection: sliding-window analysis of archive entries (plateau length, score variance, diff diversity)
- Strategy signals injected into `_build_prompt()`: graduated guidance from "tune parameters" to "consider structural changes"
- Mutation type tagging: `mutation_type` field on `ArchiveEntry` (structural vs parametric) for richer analysis
- Parameter optimization prompt sections: encourage parameter-focused mutations when topology is good

Consumes:
- Archive summaries from S01 (trend data, structural diversity)
- Component vocabulary from S02 (what structural options exist)
- `Archive.query()` for recent entries analysis

### S04 (Cold-Start)

Produces:
- Cold-start pipeline generation in `MetaAgent` (or new method): given goal + benchmark description + component vocabulary, generate initial `pipeline.py`
- CLI integration: `autoagent run` detects missing pipeline.py and triggers cold-start before entering the optimization loop
- Validation: cold-start pipelines pass same `_validate_source()` checks as mutations

Consumes:
- Component vocabulary from S02
- `MetaAgent._validate_source()` from M001
- `OptimizationLoop.run()` entry point
