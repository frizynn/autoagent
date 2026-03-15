"""autoagent CLI — init, run, and status subcommands.

Entry point for the ``autoagent`` console script.
All commands operate on a ``.autoagent/`` project directory
managed by :class:`~autoagent.state.StateManager`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from autoagent.archive import Archive
from autoagent.benchmark import Benchmark
from autoagent.evaluation import Evaluator
from autoagent.loop import OptimizationLoop
from autoagent.meta_agent import MetaAgent
from autoagent.primitives import MetricsCollector, MockLLM, PrimitivesContext, MockRetriever
from autoagent.state import LockError, StateManager


def _resolve_project_dir(args: argparse.Namespace) -> Path:
    """Return the resolved project directory from parsed args."""
    return Path(args.project_dir).resolve()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    """Create a new .autoagent/ project directory."""
    project_dir = _resolve_project_dir(args)
    sm = StateManager(project_dir)
    try:
        sm.init_project()
    except FileExistsError:
        print(f"Error: project already initialized at {sm.aa_dir}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: could not initialize project: {exc}", file=sys.stderr)
        return 1

    print(f"Initialized autoagent project at {sm.aa_dir}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Display current project state."""
    project_dir = _resolve_project_dir(args)
    sm = StateManager(project_dir)

    if not sm.is_initialized():
        print(
            f"Error: no autoagent project found at {sm.aa_dir}",
            file=sys.stderr,
        )
        return 1

    try:
        state = sm.read_state()
        config = sm.read_config()
    except (OSError, ValueError, KeyError) as exc:
        print(f"Error: could not read project state: {exc}", file=sys.stderr)
        return 1

    lines = [
        f"Project:           {project_dir}",
        f"Phase:             {state.phase}",
        f"Current iteration: {state.current_iteration}",
        f"Best iteration:    {state.best_iteration_id or '—'}",
        f"Total cost (USD):  ${state.total_cost_usd:.4f}",
        f"Last updated:      {state.updated_at or '—'}",
        f"Goal:              {config.goal or '(not set)'}",
    ]
    print("\n".join(lines))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run the optimization loop."""
    project_dir = _resolve_project_dir(args)
    sm = StateManager(project_dir)

    if not sm.is_initialized():
        print(
            f"Error: no autoagent project found at {sm.aa_dir}",
            file=sys.stderr,
        )
        return 1

    # Read config
    config = sm.read_config()
    goal = config.goal or "Optimize the pipeline."

    # Load benchmark
    benchmark_cfg = config.benchmark
    dataset_path = benchmark_cfg.get("dataset_path", "")
    scoring_function = benchmark_cfg.get("scoring_function", "exact_match")

    if not dataset_path:
        print("Error: no benchmark dataset_path configured.", file=sys.stderr)
        return 1

    # Resolve dataset_path relative to project dir
    resolved_dataset = Path(dataset_path)
    if not resolved_dataset.is_absolute():
        resolved_dataset = project_dir / resolved_dataset

    try:
        benchmark = Benchmark.from_file(resolved_dataset, scoring_function)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: could not load benchmark: {exc}", file=sys.stderr)
        return 1

    # Set up components
    archive = Archive(sm.archive_dir)
    evaluator = Evaluator()

    # LLM for the meta-agent — MockLLM for now; real provider plugged in later
    collector = MetricsCollector()
    llm = MockLLM(collector=collector)
    meta_agent = MetaAgent(llm=llm, goal=goal)

    def primitives_factory() -> PrimitivesContext:
        c = MetricsCollector()
        return PrimitivesContext(
            llm=MockLLM(collector=c),
            retriever=MockRetriever(collector=c),
            collector=c,
        )

    max_iterations = getattr(args, "max_iterations", None)
    budget = getattr(args, "budget", None)

    # Persist budget to config if provided
    if budget is not None:
        from dataclasses import replace
        config = replace(config, budget_usd=budget)
        sm.write_config(config)

    loop = OptimizationLoop(
        state_manager=sm,
        archive=archive,
        evaluator=evaluator,
        meta_agent=meta_agent,
        benchmark=benchmark,
        primitives_factory=primitives_factory,
        max_iterations=max_iterations,
        budget_usd=budget if budget is not None else config.budget_usd,
    )

    try:
        final_state = loop.run()
    except LockError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: optimization loop failed: {exc}", file=sys.stderr)
        return 1

    # Print summary
    if final_state.phase == "paused":
        print("Paused (budget).")
    else:
        print(f"Optimization complete.")
    print(f"  Iterations: {final_state.current_iteration}")
    print(f"  Best iteration: {final_state.best_iteration_id or '—'}")
    print(f"  Total cost (USD): ${final_state.total_cost_usd:.4f}")
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="autoagent",
        description="Autonomous optimization system for agentic architectures.",
    )
    parser.add_argument(
        "--project-dir",
        default=".",
        help="Project root directory (default: current working directory)",
    )

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize a new autoagent project")
    sub.add_parser("status", help="Show current project status")

    run_parser = sub.add_parser("run", help="Run the optimization loop")
    run_parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum number of optimization iterations (default: unlimited)",
    )
    run_parser.add_argument(
        "--budget",
        type=float,
        default=None,
        help="Budget ceiling in USD — loop pauses before exceeding (default: unlimited)",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """Console script entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "init": cmd_init,
        "run": cmd_run,
        "status": cmd_status,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    try:
        code = handler(args)
    except LockError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: unexpected failure: {exc}", file=sys.stderr)
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
