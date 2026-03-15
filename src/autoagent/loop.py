"""OptimizationLoop — propose→evaluate→keep/discard cycle.

Orchestrates MetaAgent, Evaluator, Archive, and StateManager into an
autonomous optimization loop.  Each iteration proposes a pipeline mutation,
evaluates it against a benchmark, and keeps or discards based on primary_score.

Phase transitions: initialized → running → completed
State is persisted atomically after every iteration.
MetaAgent failures (compile/validation errors) produce discard entries
without halting the loop.
"""

from __future__ import annotations

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
from autoagent.primitives import PrimitivesContext
from autoagent.state import ProjectState, StateManager
from autoagent.types import MetricsSnapshot


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
    ) -> None:
        self.state_manager = state_manager
        self.archive = archive
        self.evaluator = evaluator
        self.meta_agent = meta_agent
        self.benchmark = benchmark
        self.primitives_factory = primitives_factory
        self.max_iterations = max_iterations

    def run(self) -> ProjectState:
        """Execute the optimization loop.

        Returns the final ProjectState after completion.

        Phase transitions:
        - Sets phase="running" at start
        - Sets phase="completed" at end (or on max_iterations reached)
        - Lock is always released in the finally block
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

            iterations_run = 0
            while self.max_iterations is None or iterations_run < self.max_iterations:
                iteration += 1
                iterations_run += 1

                # Gather archive context for the meta-agent
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
