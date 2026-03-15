"""autoagent CLI — init, run, and status subcommands.

Entry point for the ``autoagent`` console script.
All commands operate on a ``.autoagent/`` project directory
managed by :class:`~autoagent.state.StateManager`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
    """Run the optimization loop (stub — wired in S05)."""
    project_dir = _resolve_project_dir(args)
    sm = StateManager(project_dir)

    if not sm.is_initialized():
        print(
            f"Error: no autoagent project found at {sm.aa_dir}",
            file=sys.stderr,
        )
        return 1

    print("Optimization loop not yet implemented — will be wired in S05.")
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
    sub.add_parser("run", help="Run the optimization loop")

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
