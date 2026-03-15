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
from autoagent.pareto import ParetoResult, compute_complexity, pareto_decision
from autoagent.benchmark import Benchmark
from autoagent.evaluation import EvaluationResult, Evaluator, ExampleResult
from autoagent.meta_agent import MetaAgent, ProposalResult
from autoagent.pipeline import PipelineRunner
from autoagent.primitives import LLMProtocol, MetricsCollector, PrimitivesContext
from autoagent.state import ProjectState, StateManager
from autoagent.strategy import analyze_strategy, classify_mutation
from autoagent.summarizer import ArchiveSummarizer
from autoagent.types import MetricsSnapshot
from autoagent.verification import TLAVerifier, VerificationResult
from autoagent.leakage import LeakageChecker
from autoagent.sandbox import SandboxRunner

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
        tla_verifier: TLAVerifier | None = None,
        leakage_checker: LeakageChecker | None = None,
        sandbox_runner: SandboxRunner | None = None,
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
        self.tla_verifier = tla_verifier
        self.leakage_checker = leakage_checker

        # Sandbox runner — wire into evaluator when Docker is available
        self._sandbox_used = False
        self._sandbox_fallback_reason: str | None = None
        if sandbox_runner is not None:
            if sandbox_runner.available():
                self.evaluator = Evaluator(runner=sandbox_runner)
                self._sandbox_used = True
                logger.info("Sandbox runner active — evaluator will use Docker isolation")
            else:
                reason = sandbox_runner._diagnose_unavailability()
                self._sandbox_fallback_reason = reason
                logger.warning(
                    "Docker unavailable (%s) — evaluator will use direct PipelineRunner",
                    reason,
                )

        # Cached summary state
        self._cached_summary: str = ""
        self._summary_archive_len: int = 0

    def _sandbox_execution_dict(self) -> dict[str, Any] | None:
        """Build sandbox_execution metadata for archive entries."""
        if not self._sandbox_used and self._sandbox_fallback_reason is None:
            return None  # No sandbox_runner was provided
        return {
            "sandbox_used": self._sandbox_used,
            "container_id": None,  # Per-iteration container IDs not tracked at loop level
            "network_policy": "none" if self._sandbox_used else None,
            "fallback_reason": self._sandbox_fallback_reason,
        }

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
            best_metrics: dict | None = None
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
                    # Reconstruct best_metrics for Pareto comparison
                    _eval_metrics = entry.evaluation_result.get("metrics") or {}
                    best_metrics = {
                        "primary_score": best_score,
                        "latency_ms": _eval_metrics.get("latency_ms", 0.0),
                        "cost_usd": _eval_metrics.get("cost_usd", 0.0),
                    }
                    # Use stored complexity if available, else recompute
                    _pareto_eval = entry.pareto_evaluation or {}
                    _stored_cand = (_pareto_eval.get("candidate_metrics") or {})
                    if "complexity" in _stored_cand:
                        best_metrics["complexity"] = _stored_cand["complexity"]
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

                # Gather strategy signals from stagnation detector
                strategy_signals = ""
                try:
                    recent_entries = self.archive.recent(10)
                    strategy_signals = analyze_strategy(recent_entries)
                    if strategy_signals:
                        logger.info("Strategy signal: %s", strategy_signals)
                except Exception:
                    logger.warning(
                        "Strategy detector failed, proceeding without signals",
                        exc_info=True,
                    )

                # Propose a mutation
                proposal = self.meta_agent.propose(
                    current_source=current_best_source,
                    kept_entries=kept_entries,
                    discarded_entries=discarded_entries,
                    archive_summary=archive_summary,
                    strategy_signals=strategy_signals,
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
                        mutation_type="parametric",
                        sandbox_execution=self._sandbox_execution_dict(),
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

                # --- TLA+ verification gate ---
                tla_verification: dict[str, Any] | None = None
                if self.tla_verifier is not None:
                    vr = self.tla_verifier.verify(proposal.proposed_source)
                    total_cost += vr.cost_usd
                    tla_verification = {
                        "passed": vr.passed,
                        "violations": list(vr.violations),
                        "spec_text": vr.spec_text,
                        "attempts": vr.attempts,
                        "cost_usd": vr.cost_usd,
                        "skipped": vr.skipped,
                        "skip_reason": vr.skip_reason,
                    }

                    if not vr.passed and not vr.skipped:
                        # TLA+ failed — discard without evaluation
                        rationale = f"tla_verification_failed: {'; '.join(vr.violations)}"
                        logger.info(
                            "Iteration %d: TLA+ verification failed, discarding: %s",
                            iteration,
                            rationale,
                        )
                        eval_result = _make_failed_evaluation()
                        parent_id = (
                            int(best_iteration_id) if best_iteration_id else None
                        )
                        self.archive.add(
                            pipeline_source=proposal.proposed_source,
                            evaluation_result=eval_result,
                            rationale=rationale,
                            decision="discard",
                            parent_iteration_id=parent_id,
                            mutation_type="parametric",
                            tla_verification=tla_verification,
                            sandbox_execution=self._sandbox_execution_dict(),
                        )
                        # Restore previous best on disk
                        pipeline_path.write_text(
                            current_best_source, encoding="utf-8"
                        )
                        state = replace(
                            state,
                            current_iteration=iteration,
                            total_cost_usd=total_cost,
                            updated_at=_now_iso(),
                        )
                        sm.write_state(state)
                        continue

                    if vr.passed and not vr.skipped:
                        logger.info(
                            "Iteration %d: TLA+ verification passed (%d attempts, $%.6f)",
                            iteration, vr.attempts, vr.cost_usd,
                        )
                    elif vr.skipped:
                        logger.info(
                            "Iteration %d: TLA+ verification skipped: %s",
                            iteration, vr.skip_reason,
                        )

                # --- Leakage detection gate ---
                leakage_check: dict[str, Any] | None = None
                if self.leakage_checker is not None:
                    lr = self.leakage_checker.check(
                        self.benchmark, proposal.proposed_source,
                    )
                    total_cost += lr.cost_usd
                    leakage_check = {
                        "blocked": lr.blocked,
                        "exact_matches": lr.exact_matches,
                        "fuzzy_warnings": list(lr.fuzzy_warnings),
                        "cost_usd": lr.cost_usd,
                    }

                    if lr.blocked:
                        rationale = (
                            f"leakage_blocked: {lr.exact_matches} exact matches"
                        )
                        logger.info(
                            "Iteration %d: leakage detected, discarding: %s",
                            iteration,
                            rationale,
                        )
                        eval_result = _make_failed_evaluation()
                        parent_id = (
                            int(best_iteration_id) if best_iteration_id else None
                        )
                        self.archive.add(
                            pipeline_source=proposal.proposed_source,
                            evaluation_result=eval_result,
                            rationale=rationale,
                            decision="discard",
                            parent_iteration_id=parent_id,
                            mutation_type="parametric",
                            tla_verification=tla_verification,
                            leakage_check=leakage_check,
                            sandbox_execution=self._sandbox_execution_dict(),
                        )
                        # Restore previous best on disk
                        pipeline_path.write_text(
                            current_best_source, encoding="utf-8"
                        )
                        state = replace(
                            state,
                            current_iteration=iteration,
                            total_cost_usd=total_cost,
                            updated_at=_now_iso(),
                        )
                        sm.write_state(state)
                        continue

                    if lr.fuzzy_warnings:
                        for fw in lr.fuzzy_warnings:
                            logger.warning(
                                "Iteration %d: leakage warning: %s",
                                iteration, fw,
                            )

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

                # Build candidate metrics vector for Pareto comparison
                candidate_metrics: dict = {
                    "primary_score": score,
                    "latency_ms": eval_result.metrics.latency_ms if eval_result.metrics else 0.0,
                    "cost_usd": eval_result.metrics.cost_usd if eval_result.metrics else 0.0,
                    "complexity": compute_complexity(proposal.proposed_source),
                }

                # Pareto decision: keep/discard based on multi-objective dominance
                pareto_result = pareto_decision(
                    candidate_metrics=candidate_metrics,
                    current_best_metrics=best_metrics,
                    candidate_source=proposal.proposed_source,
                    best_source=current_best_source,
                )
                decision = pareto_result.decision

                if decision == "keep":
                    best_score = score
                    best_metrics = candidate_metrics.copy()
                    current_best_source = proposal.proposed_source
                    best_iteration_id = str(self.archive._next_iteration_id())

                # Classify mutation type from diff
                parent_id = (
                    int(state.best_iteration_id)
                    if state.best_iteration_id
                    else None
                )
                pipeline_diff_text = ""
                if parent_id is not None:
                    parent_pad = max(3, len(str(parent_id)))
                    parent_pipeline = self.archive.archive_dir / f"{str(parent_id).zfill(parent_pad)}-pipeline.py"
                    if parent_pipeline.exists():
                        import difflib as _difflib
                        _old = parent_pipeline.read_text(encoding="utf-8")
                        pipeline_diff_text = "".join(_difflib.unified_diff(
                            _old.splitlines(keepends=True),
                            proposal.proposed_source.splitlines(keepends=True),
                        ))
                mt = classify_mutation(pipeline_diff_text)
                logger.debug("Mutation type: %s", mt)

                # Archive the iteration
                entry = self.archive.add(
                    pipeline_source=proposal.proposed_source,
                    evaluation_result=eval_result,
                    rationale=proposal.rationale,
                    decision=decision,
                    parent_iteration_id=parent_id,
                    baseline_source=(
                        current_best_source if parent_id is None else None
                    ),
                    mutation_type=mt,
                    tla_verification=tla_verification,
                    leakage_check=leakage_check,
                    pareto_evaluation={
                        "decision": pareto_result.decision,
                        "rationale": pareto_result.rationale,
                        "candidate_metrics": pareto_result.candidate_metrics,
                        "best_metrics": pareto_result.best_metrics,
                    },
                    sandbox_execution=self._sandbox_execution_dict(),
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
