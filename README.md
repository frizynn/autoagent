# AutoAgent

**Autonomous optimization system that iteratively discovers better agentic architectures for any goal.**

[![CI](https://github.com/frizynn/autoagent/actions/workflows/ci.yml/badge.svg)](https://github.com/frizynn/autoagent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

AutoAgent takes a goal like "improve RAG effectiveness" or "minimize pipeline latency" and runs an infinite loop: a meta-agent reads the full archive of past attempts, proposes a modification to `pipeline.py` (the only mutable file), evaluates it against a benchmark, and keeps or discards the change based on metrics and constraints. The search operates at two levels:

- **Structural search** — changes pipeline topology (RAG→CAG, add rerankers, swap models, introduce debate/reflexion, or any architecture you like)
- **Parameter optimization** — tunes prompts and hyperparameters within a fixed architecture (DSPy/Optuna-style)

Inspired by:
- [autoresearch](https://github.com/karpathy/autoresearch) — Karpathy's infinite edit→run→eval→keep/discard loop with git as state
- [GSD-2](https://github.com/gsd-build/GSD-2) — fully autonomous spec-driven development with crash recovery, disk-based state, and fresh context per unit
- [ADAS](https://github.com/ShengranHu/ADAS) — automated discovery of agentic strategies ([paper](https://arxiv.org/abs/2408.08435))
- [DSPy](https://github.com/stanfordnlp/dspy) — programming with foundation models
- [TextGrad](https://github.com/zou-group/textgrad) — text-based optimization
- [Trace/OptoPrime](https://github.com/microsoft/Trace) — optimization via tracing
- [EvoPrompt](https://github.com/beeevita/EvoPrompt) — evolutionary prompt optimization
- [OPRO](https://github.com/google-deepmind/opro) — optimization by prompting
- [AgentOptimizer](https://arxiv.org/abs/2402.11359) — optimizing LLM agents
- [StateFlow](https://arxiv.org/html/2403.11322v1) — state-machine orchestration for agents
- [Stately Agent (XState)](https://github.com/statelyai/agent) — state machines for AI agents
- [TLA+ tools](https://lamport.azurewebsites.net/tla/tools.html) — formal verification
- [Genefication](https://www.mydistributed.systems/2025/01/genefication.html) — LLM drafts spec → TLC verifies → iterate
- [AWS TLA+ paper](https://lamport.azurewebsites.net/tla/formal-methods-amazon.pdf) — formal methods at scale

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│                     AutoAgent Loop                      │
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐           │
│  │ Discovery│──▶│ Propose  │──▶│ Verify   │           │
│  │ (read    │   │ (edit    │   │ (TLA+ if │           │
│  │  archive)│   │pipeline) │   │concurrent)│          │
│  └──────────┘   └──────────┘   └────┬─────┘           │
│       ▲                              │                  │
│       │         ┌──────────┐   ┌────▼─────┐           │
│       │         │  Keep /  │◀──│ Evaluate │           │
│       └─────────│  Discard │   │(benchmark)│          │
│                 └──────────┘   └──────────┘           │
│                                                         │
│  State: disk-only (crash-recoverable)                  │
│  Archive: monotonic (successes AND failures)           │
│  Budget: token/cost ceiling with auto-pause            │
└─────────────────────────────────────────────────────────┘
```

### Key Concepts

- **`pipeline.py`** — the only mutable file. Contains the agentic pipeline built from instrumented primitives (`LLM`, `Retriever`, `Tool`, `Agent`) that auto-measure latency, tokens, and cost.
- **Archive** — grows monotonically. Every attempt (success or failure) is recorded with full metrics, diffs, and rationale. The meta-agent reads the entire archive before proposing changes.
- **Two-level search** — structural changes (topology) and parameter optimization (prompts/hyperparams) operate as distinct search modes with different mutation strategies.
- **TLA+ verification** — for concurrent pipelines (parallel agents, debate protocols, shared state), a verification layer model-checks the coordination protocol before burning tokens on evaluation.
- **Disk-based state** — everything lives on disk in `.autoagent/`. Crash at any point, restart, continue. No in-memory state that can't be reconstructed.

### The Interview

Before any optimization begins, AutoAgent runs a deep interview (GSD-2 style) to understand:

1. **What you're optimizing** — the goal, metrics, constraints
2. **The evaluation setup** — benchmark data, scoring function, success criteria
3. **The search space** — what's allowed to change, what's fixed
4. **Budget and constraints** — token limits, cost ceiling, time bounds
5. **Starting point** — existing pipeline or blank slate

The orchestrator asks probing questions, investigates your codebase, checks library docs, and builds a complete specification before the first optimization cycle begins.

## Project Status

🚧 **Early development** — architecture and core loop under construction.

## Development

```bash
# Clone
git clone https://github.com/frizynn/autoagent.git
cd autoagent

# Install (Python 3.11+)
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .
ruff format --check .

# Type check
mypy src/
```

## Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Commit with [conventional commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, etc.)
4. Push and open a PR against `main`
5. CI must pass before merge

All PRs require review and passing CI. The `main` branch is protected — no direct pushes.

## License

MIT — see [LICENSE](LICENSE) for details.
