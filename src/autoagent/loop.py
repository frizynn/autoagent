"""OptimizationLoop — propose→evaluate→keep/discard cycle.

Orchestrates MetaAgent, Evaluator, Archive, and StateManager into an
autonomous optimization loop.  Each iteration proposes a pipeline mutation,
evaluates it against a benchmark, and keeps or discards based on primary_score.

Phase transitions: initialized → running → completed | paused
State is persisted atomically after every iteration.
MetaAgent failures (compile/validation errors) produce discard entries
without halting the loop.
Budget exhaustion triggers phase="paused" (distinct from "completed").
Resume from "paused" or stale "running" reconstructs best state from archive.

When the archive exceeds summary_threshold, an LLM-generated summary replaces
raw entries in the meta-agent prompt. The summary is cached and regenerated
every summary_interval iterations. Summarizer cost counts against budget_usd.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from autoagent.archive import Archive, ArchiveEntry
from autoagent.benchmark import Benchmark
from autoagent.evaluation import EvaluationResult, Evaluator, ExampleResult
from autoagent.meta_agent import MetaAgent, ProposalResult
from autoagent.pipeline import PipelineRunner
from autoagent.primitives import LLMProtocol, MetricsCollector, PrimitivesContext
from autoagent.state import ProjectState, StateManager
from autoagent.summarizer import ArchiveSummarizer
from autoagent.types import MetricsSnapshot

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_failed_evaluation() -> EvaluationResult:
    """Return a zero-score EvaluationResult for failed proposals."""
    return EvaluationResult(
        primary_score=0.0,
        per_example_results=[],
        metrics=None,
        benchmark_id="",
        duration_ms=0.0,
        num_examples=0,
        num_failures=0,
    )


class OptimizationLoop:
    """Autonomous propose→evaluate→keep/discard loop.

    Parameters
    ----------
    state_manager:
        Manages state.json persistence and locking.
    archive:
        Monotonic archive for recording iteration outcomes.
    evaluator:
        Evaluates pipelines against the benchmark.
    meta_agent:
        Proposes pipeline mutations via LLM.
    benchmark:
        Loaded benchmark with examples and scorer.
    primitives_factory:
        Callable returning a fresh PrimitivesContext per evaluation.
    max_iterations:
        Stop after this many iterations. None = unlimited.
    budget_usd:
        Hard dollar ceiling. Loop pauses before exceeding this amount.
        None = no budget limit.
    summary_threshold:
        Archive size at which summaries replace raw entries in the prompt.
    summary_interval:
        Regenerate summary every N iterations past threshold.
    summarizer_llm:
        LLM for summarization. If None, uses meta_agent's LLM.
    """

    def __init__(
        self,
        state_manager: StateManager,
        archive: Archive,
        evaluator: Evaluator,
        meta_agent: MetaAgent,
        benchmark: Benchmark,
        primitives_factory: Callable[[], PrimitivesContext],
        max_iterations: int | None = None,
        budget_usd: float | None = None,
        summary_threshold: int = 20,
        summary_interval: int = 10,
        summarizer_llm: LLMProtocol | None = None,
    ) -> None:
        self.state_manager = state_manager
        self.archive = archive
        self.evaluator = evaluator
        self.meta_agent = meta_agent
        self.benchmark = benchmark
        self.primitives_factory = primitives_factory
        self.max_iterations = max_iterations
        self.budget_usd = budget_usd
        self.summary_threshold = summary_threshold
        self.summary_interval = summary_interval
        self.summarizer_llm = summarizer_llm
        # Cached summary state
        self._cached_summary: str = ""
        self._summary_archive_len: int = 0

    def run(self) -> ProjectState:
        """Execute the optimization loop.

        Returns the final ProjectState after completion.

        Phase transitions:
        - Sets phase="running" at start (also handles "paused" → "running")
        - Sets phase="completed" at end (or on max_iterations reached)
        - Sets phase="paused" on budget exhaustion
        - Lock is always released in the finally block

        Resume behavior:
        - If current_iteration > 0, reconstructs best_score from archive
        - Restores pipeline.py from the best kept archive entry
        """
        sm = self.state_manager
        pipeline_path = sm.pipeline_path

        sm.acquire_lock()
        try:
            # Read and transition to running
            state = sm.read_state()
            state = replace(
                state,
                phase="running",
                started_at=state.started_at or _now_iso(),
                updated_at=_now_iso(),
            )
            sm.write_state(state)

            # Read current best source from disk
            current_best_source = pipeline_path.read_text(encoding="utf-8")
            best_score: float | None = None
            best_iteration_id = state.best_iteration_id
            total_cost = state.total_cost_usd
            iteration = state.current_iteration

            # --- Resume from state ---
            if iteration > 0:
                # Reconstruct best_score from archive's best kept entry
                best_kept = self.archive.query(
                    decision="keep",
                    sort_by="primary_score",
                    ascending=False,
                    limit=1,
                )
                if best_kept:
                    entry = best_kept[0]
                    best_score = entry.evaluation_result["primary_score"]
                    # Restore pipeline source from archive snapshot
                    archive_pipeline = (
                        self.archive.archive_dir
                        / f"{str(entry.iteration_id).zfill(max(3, len(str(entry.iteration_id))))}-pipeline.py"
                    )
                    if archive_pipeline.exists():
                        current_best_source = archive_pipeline.read_text(
                            encoding="utf-8"
                        )
                        pipeline_path.write_text(
                            current_best_source, encoding="utf-8"
                        )
                # If no kept entries, best_score stays None — first good eval
                # will be kept. current_best_source stays as whatever is on disk.

            iterations_run = 0
            while self.max_iterations is None or iterations_run < self.max_iterations:
                # --- Budget check before iteration ---
                if self.budget_usd is not None:
                    if total_cost >= self.budget_usd:
                        state = replace(
                            state,
                            phase="paused",
                            current_iteration=iteration,
                            total_cost_usd=total_cost,
                            updated_at=_now_iso(),
                        )
                        sm.write_state(state)
                        return state

                    # Estimate next iteration cost from average of prior
                    if iterations_run > 0:
                        avg_cost = total_cost / (
                            iteration if iteration > 0 else iterations_run
                        )
                        if total_cost + avg_cost > self.budget_usd:
                            state = replace(
                                state,
                                phase="paused",
                                current_iteration=iteration,
                                total_cost_usd=total_cost,
                                updated_at=_now_iso(),
                            )
                            sm.write_state(state)
                            return state

                iteration += 1
                iterations_run += 1

                # Gather archive context for the meta-agent
                all_entries = self.archive.query()
                archive_len = len(all_entries)
                archive_summary = ""

                if archive_len >= self.summary_threshold:
                    # Check if summary needs (re)generation
                    needs_summary = (
                        not self._cached_summary
                        or (archive_len - self._summary_archive_len) >= self.summary_interval
                    )
                    if needs_summary:
                        # Resolve LLM: prefer explicit summarizer_llm, fall back to meta_agent's
                        sum_llm = self.summarizer_llm or getattr(self.meta_agent, "llm", None)
                        if sum_llm is not None:
                            try:
                                summarizer = ArchiveSummarizer(
                                    llm=sum_llm,
                                    resummarize_interval=self.summary_interval,
                                )
                                result = summarizer.summarize(all_entries)
                                if result.text:
                                    self._cached_summary = result.text
                                    self._summary_archive_len = archive_len
                                    total_cost += result.cost_usd
                                    logger.info(
                                        "Archive summary regenerated: %d entries, $%.6f",
                                        archive_len,
                                        result.cost_usd,
                                    )
                                else:
                                    logger.warning(
                                        "Summarizer returned empty text, falling back to raw entries"
                                    )
                            except Exception:
                                logger.warning(
                                    "Summarizer failed, falling back to raw entries",
                                    exc_info=True,
                                )

                    archive_summary = self._cached_summary

                if archive_summary:
                    # Use summary — skip raw entry gathering
                    kept_entries: list[ArchiveEntry] = []
                    discarded_entries: list[ArchiveEntry] = []
                else:
                    # Below threshold or summary unavailable — use raw entries
                    kept_entries = self.archive.query(
                        decision="keep", sort_by="primary_score",
                        ascending=False, limit=3,
                    )
                    discarded_entries = self.archive.query(
                        decision="discard", limit=3,
                    )

                # Propose a mutation
                proposal = self.meta_agent.propose(
                    current_source=current_best_source,
                    kept_entries=kept_entries,
                    discarded_entries=discarded_entries,
                    archive_summary=archive_summary,
                )
                total_cost += proposal.cost_usd

                if not proposal.success:
                    # Failed proposal → discard with error rationale
                    eval_result = _make_failed_evaluation()
                    self.archive.add(
                        pipeline_source=proposal.proposed_source or current_best_source,
                        evaluation_result=eval_result,
                        rationale=f"proposal_error: {proposal.error}",
                        decision="discard",
                        parent_iteration_id=(
                            int(best_iteration_id) if best_iteration_id else None
                        ),
                    )
                    state = replace(
                        state,
                        current_iteration=iteration,
                        total_cost_usd=total_cost,
                        updated_at=_now_iso(),
                    )
                    sm.write_state(state)
                    continue

                # Write proposed source to disk for evaluation
                pipeline_path.write_text(proposal.proposed_source, encoding="utf-8")

                # Evaluate
                eval_result = self.evaluator.evaluate(
                    pipeline_path=pipeline_path,
                    benchmark=self.benchmark,
                    primitives_factory=self.primitives_factory,
                )

                # Accumulate evaluation cost
                if eval_result.metrics:
                    total_cost += eval_result.metrics.cost_usd

                score = eval_result.primary_score

                # Decision: keep if score >= best (or first successful eval)
                if best_score is None or score >= best_score:
                    decision = "keep"
                    best_score = score
                    current_best_source = proposal.proposed_source
                    best_iteration_id = str(self.archive._next_iteration_id())
                else:
                    decision = "discard"

                # Archive the iteration
                parent_id = (
                    int(state.best_iteration_id)
                    if state.best_iteration_id
                    else None
                )
                entry = self.archive.add(
                    pipeline_source=proposal.proposed_source,
                    evaluation_result=eval_result,
                    rationale=proposal.rationale,
                    decision=decision,
                    parent_iteration_id=parent_id,
                    baseline_source=(
                        current_best_source if parent_id is None else None
                    ),
                )

                if decision == "keep":
                    best_iteration_id = str(entry.iteration_id)
                else:
                    # Restore previous best on disk
                    pipeline_path.write_text(
                        current_best_source, encoding="utf-8"
                    )

                state = replace(
                    state,
                    current_iteration=iteration,
                    best_iteration_id=best_iteration_id,
                    total_cost_usd=total_cost,
                    updated_at=_now_iso(),
                )
                sm.write_state(state)

            # Loop finished — mark completed
            state = replace(state, phase="completed", updated_at=_now_iso())
            sm.write_state(state)

        finally:
            sm.release_lock()

        return state
