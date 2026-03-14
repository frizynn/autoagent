"""PipelineRunner — dynamically loads and executes user pipeline.py files."""

from __future__ import annotations

import time
import traceback
import types
from pathlib import Path
from typing import Any

from autoagent.primitives import PrimitivesContext
from autoagent.types import ErrorInfo, PipelineResult


class PipelineRunner:
    """Load and execute a pipeline.py file, returning structured PipelineResult.

    The runner resolves the given path, validates it against *allowed_root*,
    dynamically loads the module (fresh every call — no caching), invokes its
    ``run(input_data, primitives)`` callable, and wraps the outcome in a
    :class:`PipelineResult` with aggregated metrics.

    Every failure mode (missing file, missing ``run()``, runtime exception)
    produces a valid ``PipelineResult(success=False)`` with structured
    :class:`ErrorInfo` — the runner never raises.
    """

    def __init__(self, allowed_root: Path | str | None = None) -> None:
        self.allowed_root: Path = Path(allowed_root).resolve() if allowed_root else Path.cwd().resolve()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        pipeline_path: str | Path,
        input_data: Any = None,
        primitives_context: PrimitivesContext | None = None,
        *,
        timeout: float | None = None,  # reserved for S03 — not enforced in S01
    ) -> PipelineResult:
        """Load *pipeline_path* and execute its ``run()`` function.

        Returns a :class:`PipelineResult` in all cases.  On failure,
        ``success`` is ``False`` and ``error`` contains structured
        :class:`ErrorInfo` with type, message, and traceback.
        """
        t0 = time.perf_counter()

        # --- path validation ---
        try:
            resolved = self._validate_path(pipeline_path)
        except _PathError as exc:
            return self._fail(exc.error_info, t0)

        # --- module loading ---
        try:
            module = self._load_module(resolved)
        except _PathError as exc:
            return self._fail(exc.error_info, t0)

        # --- verify run() callable ---
        run_fn = getattr(module, "run", None)
        if run_fn is None or not callable(run_fn):
            return self._fail(
                ErrorInfo(
                    type="AttributeError",
                    message=f"Pipeline module {resolved.name} has no callable 'run' attribute",
                ),
                t0,
            )

        # --- execute ---
        ctx = primitives_context or PrimitivesContext()
        try:
            output = run_fn(input_data, ctx)
        except Exception as exc:
            return self._fail(
                ErrorInfo(
                    type=type(exc).__name__,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                ),
                t0,
            )

        duration_ms = (time.perf_counter() - t0) * 1000
        metrics = ctx.collector.aggregate()

        return PipelineResult(
            output=output,
            metrics=metrics,
            success=True,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_path(self, pipeline_path: str | Path) -> Path:
        """Resolve and validate the pipeline path. Raises _PathError on failure."""
        resolved = Path(pipeline_path).resolve()

        # Must be a .py file
        if resolved.suffix != ".py":
            raise _PathError(ErrorInfo(
                type="ValueError",
                message=f"Pipeline path must be a .py file, got: {resolved.name}",
            ))

        # Must exist
        if not resolved.is_file():
            raise _PathError(ErrorInfo(
                type="FileNotFoundError",
                message=f"Pipeline file not found: {resolved}",
            ))

        # Must be under allowed_root (resolve symlinks for the check)
        real_path = resolved.resolve()
        real_root = self.allowed_root.resolve()
        try:
            real_path.relative_to(real_root)
        except ValueError:
            raise _PathError(ErrorInfo(
                type="PermissionError",
                message=f"Pipeline path {resolved} is outside allowed root {self.allowed_root}",
            ))

        return resolved

    def _load_module(self, path: Path) -> types.ModuleType:
        """Load a Python module from *path* without caching.

        Reads source directly and compiles it, bypassing importlib's
        bytecode cache so that changes to the file are always picked up.
        """
        source = path.read_text(encoding="utf-8")
        code = compile(source, str(path), "exec")
        module = types.ModuleType(f"_autoagent_pipeline_{path.stem}")
        module.__file__ = str(path)
        exec(code, module.__dict__)  # noqa: S102
        return module

    @staticmethod
    def _fail(error: ErrorInfo, t0: float) -> PipelineResult:
        """Build a failure PipelineResult with duration captured."""
        return PipelineResult(
            output=None,
            metrics=None,
            success=False,
            error=error,
            duration_ms=(time.perf_counter() - t0) * 1000,
        )


class _PathError(Exception):
    """Internal exception carrying an ErrorInfo for path/load failures."""

    def __init__(self, error_info: ErrorInfo) -> None:
        self.error_info = error_info
        super().__init__(error_info.message)
