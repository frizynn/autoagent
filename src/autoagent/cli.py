"""autoagent CLI — init, run, and status subcommands.

Entry point for the ``autoagent`` console script.
All commands operate on a ``.autoagent/`` project directory
managed by :class:`~autoagent.state.StateManager`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from autoagent.archive import Archive
from autoagent.benchmark import Benchmark
from autoagent.benchmark_gen import BenchmarkGenerator, GenerationResult
from autoagent.evaluation import Evaluator
from autoagent.interview import InterviewOrchestrator, SequenceMockLLM
from autoagent.loop import OptimizationLoop
from autoagent.meta_agent import MetaAgent
from autoagent.primitives import MetricsCollector, MockLLM, PrimitivesContext, MockRetriever
from autoagent.report import generate_report
from autoagent.state import STARTER_PIPELINE, LockError, StateManager


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


def cmd_new(args: argparse.Namespace) -> int:
    """Run the interactive interview and write config + context to disk."""
    project_dir = _resolve_project_dir(args)
    sm = StateManager(project_dir)

    # Auto-initialize if needed
    if not sm.is_initialized():
        try:
            sm.init_project()
            print(f"Initialized autoagent project at {sm.aa_dir}")
        except OSError as exc:
            print(f"Error: could not initialize project: {exc}", file=sys.stderr)
            return 1
    else:
        # Warn if config already has a goal
        try:
            existing_config = sm.read_config()
        except (OSError, ValueError, KeyError):
            existing_config = None

        if existing_config and existing_config.goal:
            print(
                f"Warning: project already has a goal configured: "
                f"{existing_config.goal!r}",
                file=sys.stderr,
            )
            try:
                confirm = input("Overwrite existing configuration? (yes/no) > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.", file=sys.stderr)
                return 1
            if confirm not in ("yes", "y"):
                print("Aborted.")
                return 0

    # Create orchestrator — MockLLM placeholder until real provider wiring
    collector = MetricsCollector()
    llm = MockLLM(collector=collector)
    orchestrator = InterviewOrchestrator(llm=llm)

    try:
        result = orchestrator.run()
    except KeyboardInterrupt:
        # Clean exit with partial state info
        answered = list(orchestrator.state.keys())
        print(
            f"\nInterview interrupted. "
            f"Partial answers collected for: {', '.join(answered) if answered else 'none'}.",
            file=sys.stderr,
        )
        return 1

    # Auto-generate benchmark if no dataset_path provided and goal is set
    config = result.config
    benchmark_cfg = config.benchmark
    if not benchmark_cfg.get("dataset_path", "") and config.goal:
        gen = BenchmarkGenerator(llm=llm, goal=config.goal)
        gen_result = gen.generate()

        if gen_result.success:
            benchmark_path = sm.aa_dir / "benchmark.json"
            with open(benchmark_path, "w", encoding="utf-8") as f:
                json.dump(gen_result.examples, f, indent=2, ensure_ascii=False)

            from dataclasses import replace
            updated_benchmark = {**benchmark_cfg}
            updated_benchmark["dataset_path"] = "benchmark.json"
            updated_benchmark["scoring_function"] = gen_result.scoring_function
            config = replace(config, benchmark=updated_benchmark)
            print(
                f"Generated benchmark with {len(gen_result.examples)} examples "
                f"(scoring: {gen_result.scoring_function})"
            )
        else:
            print(
                f"Warning: benchmark generation failed: {gen_result.error}",
                file=sys.stderr,
            )

    # Write config and context to disk
    sm.write_config(config)
    context_path = sm.aa_dir / "context.md"
    context_path.write_text(result.context, encoding="utf-8")

    # Print summary
    goal = config.goal or "(not set)"
    metric_count = len(config.metric_priorities)
    constraint_count = len(config.constraints)
    print(f"\nProject configured:")
    print(f"  Goal:        {goal}")
    print(f"  Metrics:     {metric_count}")
    print(f"  Constraints: {constraint_count}")
    print(f"  Config:      {sm.config_path}")
    print(f"  Context:     {context_path}")
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

    # -- Cold-start detection -------------------------------------------------
    current_source = sm.pipeline_path.read_text(encoding="utf-8")
    if current_source == STARTER_PIPELINE:
        print("Cold-start: generating initial pipeline from benchmark…")
        benchmark_desc = benchmark.describe()
        result = meta_agent.generate_initial(benchmark_desc)
        if result.success:
            sm.pipeline_path.write_text(result.proposed_source, encoding="utf-8")
            print("Cold-start: initial pipeline generated successfully.")
        else:
            print(f"Cold-start: first attempt failed ({result.error}), retrying…")
            result = meta_agent.generate_initial(benchmark_desc)
            if result.success:
                sm.pipeline_path.write_text(result.proposed_source, encoding="utf-8")
                print("Cold-start: initial pipeline generated on retry.")
            else:
                print(
                    f"Warning: cold-start generation failed after retry "
                    f"({result.error}). Continuing with starter pipeline.",
                    file=sys.stderr,
                )

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


def cmd_report(args: argparse.Namespace) -> int:
    """Generate a markdown report from archive data."""
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

    archive = Archive(sm.archive_dir)
    entries = archive.query()

    result = generate_report(entries, state, config)

    # Write report to disk
    report_path = sm.aa_dir / "report.md"
    report_path.write_text(result.markdown, encoding="utf-8")

    print(result.summary)
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
    sub.add_parser("new", help="Run interactive interview to configure a new project")

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

    sub.add_parser("report", help="Generate optimization report from archive data")

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
        "new": cmd_new,
        "run": cmd_run,
        "status": cmd_status,
        "report": cmd_report,
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
