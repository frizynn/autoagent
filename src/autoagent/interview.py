"""InterviewOrchestrator — multi-turn LLM-driven interview for extracting optimization specs.

Drives a structured conversation through phases (goal, metrics, constraints,
search_space, benchmark, budget, confirmation), detects vague/insufficient
answers and generates follow-up probes via LLMProtocol, then produces a
populated ProjectConfig and context.md narrative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from autoagent.primitives import LLMProtocol
from autoagent.state import ProjectConfig

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Phrases that signal a vague answer (case-insensitive substring match).
VAGUE_PHRASES: tuple[str, ...] = (
    "better",
    "good",
    "improve",
    "faster",
    "nice",
    "great",
    "fine",
    "okay",
    "not sure",
    "don't know",
    "i guess",
    "whatever",
    "something",
    "anything",
)

#: Minimum character length for a non-vague answer.
MIN_ANSWER_LENGTH = 10

#: Maximum follow-up retries per phase before accepting what we have.
MAX_RETRIES_PER_PHASE = 2

# Phase definitions: (phase_key, template_question)
PHASES: list[tuple[str, str]] = [
    (
        "goal",
        "What is the primary goal of your optimization project? "
        "Be as specific as possible about what you're trying to achieve.",
    ),
    (
        "metrics",
        "What metrics will you use to measure success? "
        "List the key performance indicators and how they should be prioritized.",
    ),
    (
        "constraints",
        "What constraints does this project have? "
        "Consider budget limits, time constraints, hardware requirements, "
        "data availability, or regulatory requirements.",
    ),
    (
        "search_space",
        "What approaches, techniques, or parameter ranges should be explored? "
        "Describe the search space — what should the optimizer try?",
    ),
    (
        "benchmark",
        "Do you have a benchmark dataset and scoring function? "
        "Describe the dataset path and how results should be scored.",
    ),
    (
        "budget",
        "What is your budget for this optimization run in USD? "
        "This controls how many iterations and LLM calls will be made.",
    ),
]


# ---------------------------------------------------------------------------
# Vague-input detection
# ---------------------------------------------------------------------------


def is_vague(answer: str) -> bool:
    """Return True if *answer* is empty, too short, or contains only vague phrases.

    Detection rules:
    - Empty or whitespace-only → vague
    - Shorter than MIN_ANSWER_LENGTH characters (stripped) → vague
    - Entire answer (stripped) is a single vague phrase → vague
    """
    stripped = answer.strip()
    if not stripped:
        return True
    if len(stripped) < MIN_ANSWER_LENGTH:
        return True
    # Check if the whole answer is just a known vague phrase
    lower = stripped.lower()
    for phrase in VAGUE_PHRASES:
        if lower == phrase:
            return True
    return False


# ---------------------------------------------------------------------------
# InterviewResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InterviewResult:
    """Structured output of a completed interview.

    Attributes
    ----------
    config : ProjectConfig
        Populated configuration from interview answers.
    context : str
        Narrative context.md string synthesized by the LLM.
    """

    config: ProjectConfig
    context: str


# ---------------------------------------------------------------------------
# SequenceMockLLM
# ---------------------------------------------------------------------------


class SequenceMockLLM:
    """Mock LLM that returns responses from a pre-defined sequence.

    Each call to :meth:`complete` returns the next response in order.
    When the sequence is exhausted, it cycles back to the beginning.

    Satisfies :class:`LLMProtocol`.
    """

    def __init__(self, responses: list[str]) -> None:
        if not responses:
            raise ValueError("responses must be non-empty")
        self.responses = list(responses)
        self._index = 0
        self.call_count = 0
        self.prompts: list[str] = []

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Return the next response in the sequence."""
        self.prompts.append(prompt)
        self.call_count += 1
        response = self.responses[self._index % len(self.responses)]
        self._index += 1
        return response


# ---------------------------------------------------------------------------
# InterviewOrchestrator
# ---------------------------------------------------------------------------


class InterviewOrchestrator:
    """Drives a multi-turn LLM interview to extract an optimization spec.

    Parameters
    ----------
    llm : LLMProtocol
        Language model used for generating probing follow-ups and context.
    input_fn : callable
        Function to collect user input (default: builtin ``input``).
        Signature: ``(prompt: str) -> str``.
    print_fn : callable
        Function to display text to the user (default: builtin ``print``).
        Signature: ``(text: str) -> None``.
    """

    def __init__(
        self,
        llm: LLMProtocol,
        input_fn: Callable[..., str] | None = None,
        print_fn: Callable[..., None] | None = None,
    ) -> None:
        self.llm = llm
        self.input_fn: Callable[..., str] = input_fn or input
        self.print_fn: Callable[..., None] = print_fn or print
        self.state: dict[str, str] = {}
        self.phase: str = "not_started"
        self._vague_flags: dict[str, int] = {}  # phase → retry count

    # -- public API --------------------------------------------------------

    def run(self) -> InterviewResult:
        """Execute the full interview and return structured results.

        Walks through each phase, collecting answers and probing vague input.
        After all phases, generates a ProjectConfig and context narrative.
        """
        self.print_fn("\n=== AutoAgent Project Interview ===\n")

        for phase_key, template_question in PHASES:
            self.phase = phase_key
            self._run_phase(phase_key, template_question)

        # Confirmation phase
        self.phase = "confirmation"
        self._run_confirmation()

        self.phase = "complete"
        return InterviewResult(
            config=self.generate_config(),
            context=self.generate_context(),
        )

    # -- phase execution ---------------------------------------------------

    def _run_phase(self, phase_key: str, question: str) -> None:
        """Run a single interview phase with vague-input detection."""
        self.print_fn(f"\n--- {phase_key.replace('_', ' ').title()} ---")
        self.print_fn(question)

        answer = self.input_fn("> ").strip()
        retries = 0

        while is_vague(answer) and retries < MAX_RETRIES_PER_PHASE:
            retries += 1
            self._vague_flags[phase_key] = retries

            # Ask LLM to generate a probing follow-up
            try:
                probe = self.llm.complete(
                    f"The user was asked: '{question}'\n"
                    f"They answered: '{answer}'\n"
                    f"This answer is too vague. Generate a specific, probing "
                    f"follow-up question that helps them give a more concrete, "
                    f"actionable answer. Be direct and helpful."
                )
            except Exception:
                # LLM failure during probe — accept what we have
                break

            self.print_fn(probe)
            answer = self.input_fn("> ").strip()

        self.state[phase_key] = answer

    def _run_confirmation(self) -> None:
        """Show collected answers and ask for confirmation."""
        self.print_fn("\n--- Summary ---")
        for key, value in self.state.items():
            label = key.replace("_", " ").title()
            self.print_fn(f"  {label}: {value}")

        self.print_fn("\nDoes this look correct? (yes/no)")
        confirmation = self.input_fn("> ").strip().lower()
        self.state["confirmed"] = confirmation

    # -- output generation -------------------------------------------------

    def generate_config(self) -> ProjectConfig:
        """Build a ProjectConfig from collected interview answers."""
        # Parse budget
        budget: float | None = None
        budget_str = self.state.get("budget", "").strip()
        if budget_str:
            # Extract numeric value from budget string
            numbers = re.findall(r"[\d.]+", budget_str)
            if numbers:
                try:
                    budget = float(numbers[0])
                except ValueError:
                    pass

        # Parse benchmark
        benchmark_answer = self.state.get("benchmark", "")
        benchmark: dict[str, Any] = {
            "dataset_path": "",
            "scoring_function": "",
        }
        if benchmark_answer:
            benchmark["description"] = benchmark_answer

        # Parse list fields — split on commas, newlines, or semicolons
        def parse_list(text: str) -> list[str]:
            if not text.strip():
                return []
            items = re.split(r"[,;\n]+", text)
            return [item.strip() for item in items if item.strip()]

        return ProjectConfig(
            goal=self.state.get("goal", ""),
            benchmark=benchmark,
            budget_usd=budget,
            search_space=parse_list(self.state.get("search_space", "")),
            constraints=parse_list(self.state.get("constraints", "")),
            metric_priorities=parse_list(self.state.get("metrics", "")),
        )

    def generate_context(self) -> str:
        """Ask the LLM to synthesize interview answers into a context.md narrative."""
        answers_summary = "\n".join(
            f"- {key.replace('_', ' ').title()}: {value}"
            for key, value in self.state.items()
            if key != "confirmed"
        )

        try:
            context = self.llm.complete(
                f"Based on the following interview answers about an optimization "
                f"project, write a concise context document (in markdown) that "
                f"summarizes the project goals, metrics, constraints, and approach. "
                f"This will be used by an AI agent to understand the project.\n\n"
                f"{answers_summary}"
            )
        except Exception:
            # Fallback: raw answers as context
            context = f"# Project Context\n\n{answers_summary}"

        return context
