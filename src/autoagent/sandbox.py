"""Sandbox-isolated pipeline execution via Docker containers.

Wraps ``PipelineRunner.run()`` in a Docker container with ``--network=none``
and ``docker cp`` (no bind-mounts). Falls back to direct ``PipelineRunner``
when Docker is unavailable (D043). All Docker interaction via
``subprocess.run()`` — zero Python package dependencies (D044).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from autoagent.pipeline import PipelineRunner
from autoagent.primitives import PrimitivesContext
from autoagent.types import ErrorInfo, MetricsSnapshot, PipelineResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SandboxResult:
    """Metadata about sandbox execution for a single iteration.

    Fields:
        sandbox_used: True if Docker container was used, False if fallback.
        container_id: Docker container ID when sandbox was used.
        network_policy: Network mode applied to the container (e.g. "none").
        fallback_reason: Why fallback was used, None if sandbox succeeded.
        cost_usd: Cost attributed to sandbox overhead (currently 0).
    """

    sandbox_used: bool
    container_id: str | None = None
    network_policy: str = "none"
    fallback_reason: str | None = None
    cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Container-side runner harness (string constant, copied into container)
# ---------------------------------------------------------------------------

_RUNNER_HARNESS = """\
#!/usr/bin/env python3
\"\"\"Thin harness executed inside Docker container.

Reads JSON from stdin: {"pipeline_path": str, "input_data": any}
Writes PipelineResult JSON to stdout.
\"\"\"
import json
import sys
import time
import traceback as tb_mod
from pathlib import Path

def main():
    payload = json.loads(sys.stdin.read())
    pipeline_path = payload["pipeline_path"]
    input_data = payload.get("input_data")

    t0 = time.perf_counter()

    # Load pipeline module
    import importlib.util
    spec = importlib.util.spec_from_file_location("pipeline", pipeline_path)
    if spec is None or spec.loader is None:
        result = {
            "output": None,
            "metrics": None,
            "success": False,
            "error": {"type": "ImportError", "message": f"Cannot load {pipeline_path}", "traceback": None},
            "duration_ms": (time.perf_counter() - t0) * 1000,
        }
        print(json.dumps(result))
        return

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        result = {
            "output": None,
            "metrics": None,
            "success": False,
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback": tb_mod.format_exc()},
            "duration_ms": (time.perf_counter() - t0) * 1000,
        }
        print(json.dumps(result))
        return

    run_fn = getattr(module, "run", None)
    if run_fn is None or not callable(run_fn):
        result = {
            "output": None,
            "metrics": None,
            "success": False,
            "error": {"type": "AttributeError", "message": "Pipeline has no callable 'run'", "traceback": None},
            "duration_ms": (time.perf_counter() - t0) * 1000,
        }
        print(json.dumps(result))
        return

    try:
        output = run_fn(input_data, None)  # No primitives context in sandbox
        result = {
            "output": output,
            "metrics": None,
            "success": True,
            "error": None,
            "duration_ms": (time.perf_counter() - t0) * 1000,
        }
    except Exception as exc:
        result = {
            "output": None,
            "metrics": None,
            "success": False,
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback": tb_mod.format_exc()},
            "duration_ms": (time.perf_counter() - t0) * 1000,
        }

    print(json.dumps(result))

if __name__ == "__main__":
    main()
"""

# Docker subprocess timeout in seconds
_DOCKER_TIMEOUT = 30
_EXEC_TIMEOUT = 120


# ---------------------------------------------------------------------------
# SandboxRunner
# ---------------------------------------------------------------------------


class SandboxRunner:
    """Execute pipelines inside Docker containers with network isolation.

    Mirrors ``PipelineRunner`` API. When Docker is unavailable, falls back
    to a ``PipelineRunner`` instance with a warning log.

    Args:
        fallback_runner: A ``PipelineRunner`` to use when Docker is unavailable.
            Created automatically if not provided.
        image: Docker image to use for containers (default: python:3.11-slim).
    """

    def __init__(
        self,
        fallback_runner: PipelineRunner | None = None,
        image: str = "python:3.11-slim",
    ) -> None:
        self.image = image
        self._fallback_runner = fallback_runner or PipelineRunner()

    # -- availability check (D043) -----------------------------------------

    @staticmethod
    def available() -> bool:
        """Return True if Docker binary exists on PATH and daemon is running.

        Checks both ``shutil.which("docker")`` and ``docker info`` command
        to distinguish "no binary" from "daemon not running".
        """
        if shutil.which("docker") is None:
            return False
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=_DOCKER_TIMEOUT,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    # -- main entry point --------------------------------------------------

    def run(
        self,
        pipeline_path: str | Path,
        input_data: Any = None,
        primitives_context: PrimitivesContext | None = None,
        *,
        timeout: float | None = None,
    ) -> PipelineResult:
        """Execute pipeline in Docker sandbox, matching ``PipelineRunner.run()`` signature.

        When Docker is available: creates container, copies pipeline source
        via ``docker cp``, executes via ``docker exec``, parses result.
        When unavailable: delegates to fallback ``PipelineRunner``.

        Returns a :class:`PipelineResult` in all cases.
        """
        if not self.available():
            fallback_reason = self._diagnose_unavailability()
            logger.warning(
                "Docker unavailable (%s) — falling back to direct PipelineRunner",
                fallback_reason,
            )
            self._last_sandbox_result = SandboxResult(
                sandbox_used=False,
                fallback_reason=fallback_reason,
            )
            return self._fallback_runner.run(
                pipeline_path, input_data, primitives_context, timeout=timeout
            )

        # Docker is available — run in container
        container_id: str | None = None
        try:
            container_id = self._create_container()
            logger.info("Sandbox container created: %s", container_id[:12])
            self._start_container(container_id)
            logger.info("Sandbox container started: %s", container_id[:12])

            # Copy pipeline source into container
            resolved_path = Path(pipeline_path).resolve()
            self._copy_to_container(container_id, resolved_path)

            # Copy runner harness into container
            harness_path = self._write_harness_temp()
            try:
                self._copy_to_container(container_id, Path(harness_path), dest="/tmp/_runner_harness.py")
            finally:
                try:
                    Path(harness_path).unlink()
                except OSError:
                    pass

            # Execute harness in container
            container_pipeline_path = f"/tmp/{resolved_path.name}"
            result = self._exec_in_container(
                container_id,
                container_pipeline_path,
                input_data,
            )

            self._last_sandbox_result = SandboxResult(
                sandbox_used=True,
                container_id=container_id,
                network_policy="none",
            )
            return result

        except Exception as exc:
            logger.error("Sandbox execution failed: %s", exc)
            self._last_sandbox_result = SandboxResult(
                sandbox_used=True,
                container_id=container_id,
                network_policy="none",
            )
            return PipelineResult(
                output=None,
                metrics=None,
                success=False,
                error=ErrorInfo(
                    type="SandboxError",
                    message=str(exc),
                ),
            )
        finally:
            if container_id:
                self._cleanup_container(container_id)

    @property
    def last_sandbox_result(self) -> SandboxResult | None:
        """Return the SandboxResult from the most recent run() call."""
        return getattr(self, "_last_sandbox_result", None)

    # -- container lifecycle -----------------------------------------------

    def _create_container(self) -> str:
        """Create a Docker container with --network=none. Returns container ID."""
        result = subprocess.run(
            [
                "docker", "create",
                "--network=none",
                self.image,
                "sleep", "3600",  # Keep container alive for exec calls
            ],
            capture_output=True,
            text=True,
            timeout=_DOCKER_TIMEOUT,
        )
        if result.returncode != 0:
            raise RuntimeError(f"docker create failed: {result.stderr.strip()}")
        container_id = result.stdout.strip()
        logger.info("Container created: %s", container_id[:12])
        return container_id

    def _start_container(self, container_id: str) -> None:
        """Start a previously created container."""
        result = subprocess.run(
            ["docker", "start", container_id],
            capture_output=True,
            text=True,
            timeout=_DOCKER_TIMEOUT,
        )
        if result.returncode != 0:
            raise RuntimeError(f"docker start failed: {result.stderr.strip()}")

    def _copy_to_container(
        self, container_id: str, local_path: Path, dest: str | None = None
    ) -> None:
        """Copy a local file into the container via ``docker cp``."""
        container_dest = dest or f"/tmp/{local_path.name}"
        result = subprocess.run(
            ["docker", "cp", str(local_path), f"{container_id}:{container_dest}"],
            capture_output=True,
            text=True,
            timeout=_DOCKER_TIMEOUT,
        )
        if result.returncode != 0:
            raise RuntimeError(f"docker cp failed: {result.stderr.strip()}")
        logger.info("Copied %s → container:%s", local_path.name, container_dest)

    def _exec_in_container(
        self,
        container_id: str,
        pipeline_path: str,
        input_data: Any,
    ) -> PipelineResult:
        """Execute the runner harness inside the container.

        Sends JSON to stdin, reads PipelineResult JSON from stdout.
        """
        stdin_payload = json.dumps({
            "pipeline_path": pipeline_path,
            "input_data": input_data,
        })

        result = subprocess.run(
            [
                "docker", "exec", "-i", container_id,
                "python3", "/tmp/_runner_harness.py",
            ],
            input=stdin_payload,
            capture_output=True,
            text=True,
            timeout=_EXEC_TIMEOUT,
        )

        if result.returncode != 0:
            return PipelineResult(
                output=None,
                metrics=None,
                success=False,
                error=ErrorInfo(
                    type="SandboxExecError",
                    message=f"docker exec failed (rc={result.returncode}): {result.stderr.strip()}",
                ),
            )

        # Parse JSON output from harness
        try:
            raw = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            return PipelineResult(
                output=None,
                metrics=None,
                success=False,
                error=ErrorInfo(
                    type="SandboxSerializationError",
                    message=f"Failed to parse container output: {exc}",
                ),
            )

        return _deserialize_pipeline_result(raw)

    def _cleanup_container(self, container_id: str) -> None:
        """Stop and remove a container. Best-effort — logs but does not raise."""
        for cmd_label, cmd in [
            ("stop", ["docker", "stop", "--time=2", container_id]),
            ("rm", ["docker", "rm", "-f", container_id]),
        ]:
            try:
                subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=_DOCKER_TIMEOUT,
                )
                logger.info("Container %s: %s", cmd_label, container_id[:12])
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.warning("Container %s failed for %s: %s", cmd_label, container_id[:12], exc)

    # -- helpers -----------------------------------------------------------

    def _write_harness_temp(self) -> str:
        """Write the runner harness to a temp file and return the path."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, prefix="sandbox_harness_"
        ) as f:
            f.write(_RUNNER_HARNESS)
            return f.name

    @staticmethod
    def _diagnose_unavailability() -> str:
        """Return a human-readable reason for Docker unavailability."""
        if shutil.which("docker") is None:
            return "docker binary not found on PATH"
        return "docker daemon not running or not accessible"


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _deserialize_pipeline_result(raw: dict[str, Any]) -> PipelineResult:
    """Reconstruct a PipelineResult from a JSON dict."""
    error = None
    if raw.get("error"):
        e = raw["error"]
        error = ErrorInfo(
            type=e.get("type", "Unknown"),
            message=e.get("message", ""),
            traceback=e.get("traceback"),
        )

    metrics = None
    if raw.get("metrics"):
        m = raw["metrics"]
        metrics = MetricsSnapshot(
            latency_ms=m.get("latency_ms", 0.0),
            tokens_in=m.get("tokens_in", 0),
            tokens_out=m.get("tokens_out", 0),
            cost_usd=m.get("cost_usd", 0.0),
            model=m.get("model", ""),
            provider=m.get("provider", ""),
            timestamp=m.get("timestamp", 0.0),
            custom_metrics=m.get("custom_metrics", {}),
        )

    return PipelineResult(
        output=raw.get("output"),
        metrics=metrics,
        success=raw.get("success", False),
        error=error,
        duration_ms=raw.get("duration_ms", 0.0),
    )


def serialize_pipeline_result(result: PipelineResult) -> dict[str, Any]:
    """Serialize a PipelineResult to a JSON-compatible dict."""
    return result.asdict()
