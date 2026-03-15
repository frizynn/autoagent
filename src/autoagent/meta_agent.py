"""MetaAgent — reads archive history, proposes pipeline mutations via LLM.

Constructs a structured prompt from the current pipeline source, goal,
benchmark description, and archive history (top-K kept, recent discards).
Calls an LLM, extracts valid pipeline.py source from the response, and
validates it compiles with a callable ``run`` function.

The meta-agent tracks its own LLM cost via the LLM instance's
MetricsCollector, keeping it separate from pipeline evaluation cost.
"""

from __future__ import annotations

import re
import types
from dataclasses import dataclass, field
from typing import Any

from autoagent.archive import ArchiveEntry
from autoagent.primitives import LLMProtocol, MetricsCollector


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProposalResult:
    """Outcome of a single MetaAgent.propose() call.

    Attributes:
        proposed_source: Extracted pipeline source (empty string on failure).
        rationale: LLM-provided rationale or error description.
        cost_usd: LLM cost for this proposal call.
        success: Whether the proposal produced valid, runnable source.
        error: Structured error string when success=False; None otherwise.
    """

    proposed_source: str = ""
    rationale: str = ""
    cost_usd: float = 0.0
    success: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# Fence-stripping regex
# ---------------------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(
    r"```(?:python)?\s*\n(.*?)```",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# MetaAgent
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Component vocabulary — static prompt artifact for structural search
# ---------------------------------------------------------------------------

_PATTERNS: list[dict[str, str]] = [
    {
        "name": "RAG",
        "description": "Retrieve relevant context, then generate an answer grounded in that context.",
        "skeleton": '''\
def run(input_data, primitives=None):
    query = input_data.get("question", "")
    docs = primitives.retriever.retrieve(query)
    context = "\\n".join(docs)
    prompt = f"Context:\\n{context}\\n\\nQuestion: {query}\\nAnswer:"
    answer = primitives.llm.complete(prompt)
    return {"answer": answer}''',
    },
    {
        "name": "CAG",
        "description": "Cache all context upfront and generate from the full cache — no retrieval step at inference.",
        "skeleton": '''\
def run(input_data, primitives=None):
    query = input_data.get("question", "")
    context = input_data.get("full_context", "")
    prompt = f"Context:\\n{context}\\n\\nQuestion: {query}\\nAnswer:"
    answer = primitives.llm.complete(prompt)
    return {"answer": answer}''',
    },
    {
        "name": "Debate",
        "description": "Two LLM calls argue opposing positions; a third judges and synthesizes the final answer.",
        "skeleton": '''\
def run(input_data, primitives=None):
    query = input_data.get("question", "")
    arg_for = primitives.llm.complete(f"Argue FOR: {query}")
    arg_against = primitives.llm.complete(f"Argue AGAINST: {query}")
    prompt = f"For: {arg_for}\\nAgainst: {arg_against}\\nSynthesize a balanced answer:"
    answer = primitives.llm.complete(prompt)
    return {"answer": answer}''',
    },
    {
        "name": "Reflexion",
        "description": "Generate an answer, critique it, then revise — self-correcting loop.",
        "skeleton": '''\
def run(input_data, primitives=None):
    query = input_data.get("question", "")
    draft = primitives.llm.complete(f"Answer: {query}")
    critique = primitives.llm.complete(f"Critique this answer:\\n{draft}")
    revised = primitives.llm.complete(
        f"Original: {draft}\\nCritique: {critique}\\nRevised answer:"
    )
    return {"answer": revised}''',
    },
    {
        "name": "Ensemble",
        "description": "Generate multiple independent answers, then merge or vote to pick the best.",
        "skeleton": '''\
def run(input_data, primitives=None):
    query = input_data.get("question", "")
    answers = [
        primitives.llm.complete(f"Answer (attempt {i}): {query}")
        for i in range(3)
    ]
    merged = primitives.llm.complete(
        f"Candidates:\\n" + "\\n".join(answers) + "\\nBest answer:"
    )
    return {"answer": merged}''',
    },
    {
        "name": "Reranking",
        "description": "Retrieve broadly, then use the LLM to score and rerank results before generating.",
        "skeleton": '''\
def run(input_data, primitives=None):
    query = input_data.get("question", "")
    docs = primitives.retriever.retrieve(query, top_k=10)
    ranked_prompt = f"Rank these by relevance to '{query}':\\n"
    ranked_prompt += "\\n".join(f"{i}. {d}" for i, d in enumerate(docs))
    ranking = primitives.llm.complete(ranked_prompt)
    answer = primitives.llm.complete(f"Using best docs:\\n{ranking}\\nAnswer: {query}")
    return {"answer": answer}''',
    },
]


def build_component_vocabulary() -> str:
    """Return a structured text block listing available primitives and patterns.

    This is a static prompt artifact — compact reference for the meta-agent to
    understand what building blocks are available when proposing pipeline
    mutations.  Adding a new pattern is as simple as appending to ``_PATTERNS``.

    Returns a string targeting ~1.5-2K tokens (~6-8K chars).
    """
    lines: list[str] = []

    # -- Primitives --
    lines.append("### Available Primitives")
    lines.append("")
    lines.append(
        "All pipeline code receives a `primitives` object. Use it for all LLM and retrieval calls."
    )
    lines.append("")
    lines.append(
        "- `primitives.llm.complete(prompt: str, **kwargs) -> str` — "
        "Send a prompt to the configured LLM. Returns the response text."
    )
    lines.append(
        "- `primitives.retriever.retrieve(query: str, **kwargs) -> list[str]` — "
        "Retrieve relevant documents for a query. Returns a list of text chunks."
    )
    lines.append("")

    # -- Patterns --
    lines.append("### Architectural Patterns")
    lines.append("")
    for pat in _PATTERNS:
        lines.append(f"**{pat['name']}** — {pat['description']}")
        lines.append("```python")
        lines.append(pat["skeleton"])
        lines.append("```")
        lines.append("")

    # -- Anti-patterns --
    lines.append("### Anti-Patterns (never do these)")
    lines.append("")
    lines.append("- Do NOT `import openai` or `import anthropic` — use `primitives.llm.complete()`")
    lines.append("- Do NOT hardcode API keys or model names in pipeline code")
    lines.append("- Do NOT bypass the `primitives` parameter — it provides metrics tracking and provider abstraction")
    lines.append("- The `run()` function signature is always: `def run(input_data, primitives=None)`")

    return "\n".join(lines)


class MetaAgent:
    """Proposes pipeline mutations by prompting an LLM with archive context.

    Parameters
    ----------
    llm:
        An object satisfying ``LLMProtocol`` (has ``.complete()`` and
        optionally ``.collector``).
    goal:
        The optimization goal in natural language.
    top_k_kept:
        Number of top-scoring kept entries to include in the prompt.
    recent_discards:
        Number of recent discard entries to include in the prompt.
    """

    def __init__(
        self,
        llm: LLMProtocol,
        goal: str,
        *,
        top_k_kept: int = 3,
        recent_discards: int = 3,
    ) -> None:
        self.llm = llm
        self.goal = goal
        self.top_k_kept = top_k_kept
        self.recent_discards = recent_discards

    # -- prompt construction -----------------------------------------------

    def _build_prompt(
        self,
        current_source: str,
        kept_entries: list[ArchiveEntry],
        discarded_entries: list[ArchiveEntry],
        benchmark_description: str = "",
        archive_summary: str = "",
    ) -> str:
        """Build a structured prompt for the LLM.

        Returns a single string combining system instructions and user
        context.  The prompt is plain text — inspectable for debugging
        prompt quality without calling the LLM.
        """
        sections: list[str] = []

        # System instructions
        sections.append(
            "You are an expert Python developer optimizing a data pipeline.\n"
            "Your task: given the current pipeline source, optimization goal, "
            "and history of past iterations, propose an improved version.\n\n"
            "RULES:\n"
            "1. Output a COMPLETE Python module — not a diff, not a fragment.\n"
            "2. The module MUST define: def run(input_data, primitives=None)\n"
            "3. Wrap your code in a single ```python ... ``` block.\n"
            "4. After the code block, briefly explain your changes (1-3 sentences).\n"
            "5. Consider changing the pipeline's architecture — not just tuning "
            "parameters — when the current approach has fundamental limitations."
        )

        # Goal
        sections.append(f"## Goal\n{self.goal}")

        # Component vocabulary — always included (static reference)
        sections.append(f"## Component Vocabulary\n{build_component_vocabulary()}")

        # Benchmark
        if benchmark_description:
            sections.append(f"## Benchmark\n{benchmark_description}")

        # Current pipeline
        sections.append(
            f"## Current Pipeline\n```python\n{current_source}\n```"
        )

        # History — either compressed summary or raw entries
        if archive_summary:
            sections.append(f"## Archive Summary\n{archive_summary}")
        else:
            # History — top kept
            if kept_entries:
                kept_lines: list[str] = []
                for entry in kept_entries:
                    score = entry.evaluation_result.get("primary_score", "?")
                    kept_lines.append(
                        f"- Iteration {entry.iteration_id} (score={score}): "
                        f"{entry.rationale}"
                    )
                sections.append(
                    "## Top Kept Iterations\n" + "\n".join(kept_lines)
                )

            # History — recent discards
            if discarded_entries:
                discard_lines: list[str] = []
                for entry in discarded_entries:
                    discard_lines.append(
                        f"- Iteration {entry.iteration_id}: "
                        f"{entry.rationale}"
                    )
                sections.append(
                    "## Recent Discarded Iterations (avoid these mistakes)\n"
                    + "\n".join(discard_lines)
                )

        return "\n\n".join(sections)

    # -- source extraction -------------------------------------------------

    @staticmethod
    def _extract_source(response: str) -> str:
        """Extract pipeline source from an LLM response.

        Strategy:
        - Find all ```python (or ```) fenced code blocks.
        - If multiple, use the longest (most likely the full pipeline).
        - If none, treat the entire response as source.
        - Strip leading/trailing whitespace.
        """
        blocks = _CODE_BLOCK_RE.findall(response)
        if blocks:
            # Pick the longest code block
            source = max(blocks, key=len)
        else:
            source = response
        return source.strip()

    # -- validation --------------------------------------------------------

    @staticmethod
    def _validate_source(source: str) -> str | None:
        """Validate extracted source compiles and has a callable ``run``.

        Returns None on success, or a structured error string on failure.
        """
        # Compile check
        try:
            code = compile(source, "<proposed_pipeline>", "exec")
        except SyntaxError as exc:
            detail = str(exc)
            return f"syntax error: {detail}"

        # Execute into a temporary module to check for run()
        module = types.ModuleType("_proposed_pipeline")
        try:
            exec(code, module.__dict__)
        except Exception as exc:
            return f"execution error: {exc}"

        run_attr = getattr(module, "run", None)
        if run_attr is None:
            return "missing run() function"
        if not callable(run_attr):
            return "run is not callable"

        return None

    # -- propose -----------------------------------------------------------

    def propose(
        self,
        current_source: str,
        kept_entries: list[ArchiveEntry] | None = None,
        discarded_entries: list[ArchiveEntry] | None = None,
        benchmark_description: str = "",
        archive_summary: str = "",
    ) -> ProposalResult:
        """Propose a pipeline mutation.

        Builds a prompt, calls the LLM, extracts source, validates it.
        Returns a ``ProposalResult`` with ``success=True`` and the
        proposed source on success, or ``success=False`` with a
        structured ``error`` on failure.

        Cost is tracked via the LLM's MetricsCollector (if present).
        """
        kept = kept_entries or []
        discarded = discarded_entries or []

        # Snapshot collector state to compute incremental cost
        collector: MetricsCollector | None = getattr(self.llm, "collector", None)
        cost_before = (
            collector.aggregate().cost_usd if collector else 0.0
        )

        prompt = self._build_prompt(
            current_source, kept, discarded, benchmark_description,
            archive_summary=archive_summary,
        )

        # Call LLM
        response = self.llm.complete(prompt)

        # Compute incremental cost
        cost_after = (
            collector.aggregate().cost_usd if collector else 0.0
        )
        call_cost = cost_after - cost_before

        # Empty response
        if not response or not response.strip():
            return ProposalResult(
                success=False,
                error="empty response",
                cost_usd=call_cost,
            )

        # Extract source
        source = self._extract_source(response)

        # Validate
        validation_error = self._validate_source(source)
        if validation_error is not None:
            return ProposalResult(
                proposed_source=source,
                rationale=response,
                cost_usd=call_cost,
                success=False,
                error=validation_error,
            )

        # Extract rationale — text after the code block
        rationale = _CODE_BLOCK_RE.sub("", response).strip()
        if not rationale:
            rationale = "No rationale provided."

        return ProposalResult(
            proposed_source=source,
            rationale=rationale,
            cost_usd=call_cost,
            success=True,
            error=None,
        )


def _extract_rationale(response: str) -> str:
    """Pull non-code-block text from the response as rationale."""
    text = _CODE_BLOCK_RE.sub("", response).strip()
    return text if text else "No rationale provided."
