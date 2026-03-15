"""Report generator — composable sections that produce a structured markdown report.

Pure computation — no LLM calls, no network I/O.  Reads archive entries,
project state, and config to produce a ``ReportResult`` with full markdown
and a short terminal-friendly summary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autoagent.archive import ArchiveEntry
from autoagent.state import ProjectConfig, ProjectState
from autoagent.strategy import analyze_strategy


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportResult:
    """Outcome of report generation.

    ``markdown`` is the full report suitable for writing to disk.
    ``summary`` is a short (1–2 line) terminal-friendly summary.
    """

    markdown: str
    summary: str


# ---------------------------------------------------------------------------
# Section functions
# ---------------------------------------------------------------------------


def _score_trajectory(entries: list[ArchiveEntry]) -> str:
    """Best-score progression, improvement rate, and phase detection.

    Returns a markdown section string.
    """
    if not entries:
        return "## Score Trajectory\n\nNo iterations recorded.\n"

    # Extract scores ordered by iteration
    scored: list[tuple[int, float]] = []
    for e in sorted(entries, key=lambda x: x.iteration_id):
        er = e.evaluation_result
        if isinstance(er, dict):
            score = er.get("primary_score")
            if score is not None:
                try:
                    scored.append((e.iteration_id, float(score)))
                except (TypeError, ValueError):
                    pass

    if not scored:
        return "## Score Trajectory\n\nNo scorable iterations found.\n"

    # Best score progression
    lines: list[str] = ["## Score Trajectory\n"]
    best_so_far = float("-inf")
    progression: list[tuple[int, float]] = []
    for iteration_id, score in scored:
        if score > best_so_far:
            best_so_far = score
            progression.append((iteration_id, score))

    lines.append("### Best Score Progression\n")
    lines.append("| Iteration | Score |")
    lines.append("|-----------|-------|")
    for iteration_id, score in progression:
        lines.append(f"| {iteration_id} | {score:.4f} |")
    lines.append("")

    # Improvement rate
    total_iterations = len(scored)
    total_improvements = len(progression)
    if total_iterations > 1:
        first_score = scored[0][1]
        last_best = progression[-1][1]
        delta = last_best - first_score
        lines.append(
            f"**Improvement:** {delta:+.4f} over {total_iterations} iterations "
            f"({total_improvements} improvements)\n"
        )

    # Phase detection
    if total_iterations >= 3:
        recent = [s for _, s in scored[-3:]]
        spread = max(recent) - min(recent)
        if spread < 0.01:
            phase = "stagnated"
        elif scored[-1][1] >= best_so_far - 0.001:
            phase = "converging"
        else:
            phase = "exploring"
        lines.append(f"**Current phase:** {phase}\n")

    return "\n".join(lines)


def _top_architectures(entries: list[ArchiveEntry], limit: int = 5) -> str:
    """Top-K kept entries with scores, mutation types, and rationale.

    Gracefully degrades when no entries were kept.
    """
    kept = [e for e in entries if e.decision == "keep"]

    if not kept:
        if not entries:
            return "## Top Architectures\n\nNo iterations recorded.\n"
        return (
            "## Top Architectures\n\n"
            "No iterations were kept. All entries were discarded.\n"
        )

    # Sort by primary_score descending
    def _score(e: ArchiveEntry) -> float:
        er = e.evaluation_result
        if isinstance(er, dict):
            s = er.get("primary_score")
            if s is not None:
                try:
                    return float(s)
                except (TypeError, ValueError):
                    pass
        return 0.0

    kept.sort(key=_score, reverse=True)
    top = kept[:limit]

    lines: list[str] = ["## Top Architectures\n"]
    for rank, e in enumerate(top, 1):
        score = _score(e)
        mutation = e.mutation_type or "unknown"
        rationale = e.rationale or "—"
        # Truncate rationale for table readability
        if len(rationale) > 120:
            rationale = rationale[:117] + "..."
        lines.append(f"### #{rank}: Iteration {e.iteration_id} (score: {score:.4f})\n")
        lines.append(f"- **Mutation type:** {mutation}")
        lines.append(f"- **Rationale:** {rationale}")
        lines.append("")

    return "\n".join(lines)


def _cost_breakdown(
    state: ProjectState, entries: list[ArchiveEntry]
) -> str:
    """Total cost, per-iteration breakdown, and gate costs.

    Sums TLA+ verification and leakage check costs from entries.
    """
    lines: list[str] = ["## Cost Breakdown\n"]
    lines.append(f"**Total cost:** ${state.total_cost_usd:.4f}\n")

    if not entries:
        lines.append("No iterations to break down.\n")
        return "\n".join(lines)

    # Per-iteration costs
    lines.append("### Per-Iteration Costs\n")
    lines.append("| Iteration | Eval Cost | TLA+ Cost | Leakage Cost | Decision |")
    lines.append("|-----------|-----------|-----------|--------------|----------|")

    total_eval = 0.0
    total_tla = 0.0
    total_leakage = 0.0

    for e in sorted(entries, key=lambda x: x.iteration_id):
        eval_cost = _extract_eval_cost(e)
        tla_cost = _extract_gate_cost(e.tla_verification)
        leakage_cost = _extract_gate_cost(e.leakage_check)

        total_eval += eval_cost
        total_tla += tla_cost
        total_leakage += leakage_cost

        lines.append(
            f"| {e.iteration_id} "
            f"| ${eval_cost:.4f} "
            f"| ${tla_cost:.4f} "
            f"| ${leakage_cost:.4f} "
            f"| {e.decision} |"
        )

    lines.append("")
    lines.append("### Cost Totals\n")
    lines.append(f"- **Evaluation costs:** ${total_eval:.4f}")
    lines.append(f"- **TLA+ verification costs:** ${total_tla:.4f}")
    lines.append(f"- **Leakage check costs:** ${total_leakage:.4f}")
    lines.append(
        f"- **Gate costs subtotal:** ${total_tla + total_leakage:.4f}"
    )
    lines.append(f"- **Total tracked:** ${state.total_cost_usd:.4f}")
    lines.append("")

    return "\n".join(lines)


def _extract_eval_cost(entry: ArchiveEntry) -> float:
    """Extract evaluation cost from an entry's metrics."""
    er = entry.evaluation_result
    if isinstance(er, dict):
        metrics = er.get("metrics")
        if isinstance(metrics, dict):
            cost = metrics.get("cost_usd")
            if cost is not None:
                try:
                    return float(cost)
                except (TypeError, ValueError):
                    pass
    return 0.0


def _extract_gate_cost(gate: dict[str, Any] | None) -> float:
    """Extract cost_usd from a gate result dict (TLA+ or leakage)."""
    if gate is None:
        return 0.0
    cost = gate.get("cost_usd")
    if cost is not None:
        try:
            return float(cost)
        except (TypeError, ValueError):
            pass
    return 0.0


def _recommendations(
    entries: list[ArchiveEntry], state: ProjectState, config: ProjectConfig | None = None
) -> str:
    """Strategy recommendations based on stagnation/convergence signals.

    Uses ``analyze_strategy()`` for the core signal, plus budget remaining.
    """
    lines: list[str] = ["## Recommendations\n"]

    # Strategy signal from analyze_strategy (expects newest-first)
    recent = sorted(entries, key=lambda e: e.iteration_id, reverse=True)
    signal = analyze_strategy(recent)
    if signal:
        lines.append(f"**Strategy signal:** {signal}\n")
    else:
        lines.append("No stagnation or convergence signals detected.\n")

    # Budget remaining
    if config is not None and config.budget_usd is not None:
        remaining = config.budget_usd - state.total_cost_usd
        pct = (remaining / config.budget_usd * 100) if config.budget_usd > 0 else 0
        lines.append(
            f"**Budget remaining:** ${remaining:.4f} ({pct:.1f}% of ${config.budget_usd:.2f})\n"
        )
    else:
        lines.append(f"**Budget:** No budget limit configured.\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def generate_report(
    entries: list[ArchiveEntry],
    state: ProjectState,
    config: ProjectConfig,
) -> ReportResult:
    """Compose all sections into a full markdown report.

    Returns a ``ReportResult`` with the complete markdown and a short summary.
    Handles empty archives gracefully.
    """
    # Header
    header_lines: list[str] = ["# Autoagent Optimization Report\n"]
    header_lines.append(f"**Goal:** {config.goal or '(not set)'}")
    header_lines.append(f"**Iterations:** {state.current_iteration}")

    # Best score from entries
    best_score: float | None = None
    if entries:
        for e in entries:
            er = e.evaluation_result
            if isinstance(er, dict):
                s = er.get("primary_score")
                if s is not None:
                    try:
                        val = float(s)
                        if best_score is None or val > best_score:
                            best_score = val
                    except (TypeError, ValueError):
                        pass

    if best_score is not None:
        header_lines.append(f"**Best score:** {best_score:.4f}")
    else:
        header_lines.append("**Best score:** —")

    header_lines.append(f"**Total cost:** ${state.total_cost_usd:.4f}")
    header_lines.append(f"**Phase:** {state.phase}")
    header_lines.append("")

    header = "\n".join(header_lines)

    # Empty archive shortcut
    if not entries:
        markdown = header + "\n---\n\nNo optimization data available. Run `autoagent run` to start.\n"
        summary = "No data — 0 iterations, $0.0000 spent."
        return ReportResult(markdown=markdown, summary=summary)

    # Compose sections
    sections = [
        header,
        "---\n",
        _score_trajectory(entries),
        _top_architectures(entries),
        _cost_breakdown(state, entries),
        _recommendations(entries, state, config),
    ]
    markdown = "\n".join(sections)

    # Build summary
    n = len(entries)
    kept = sum(1 for e in entries if e.decision == "keep")
    score_str = f"{best_score:.4f}" if best_score is not None else "—"
    summary = (
        f"{n} iterations ({kept} kept), best score: {score_str}, "
        f"cost: ${state.total_cost_usd:.4f}"
    )

    return ReportResult(markdown=markdown, summary=summary)
