"""Core types for AutoAgent pipeline execution and metrics."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ErrorInfo:
    """Structured error information from a pipeline execution failure."""

    type: str
    message: str
    traceback: str | None = None


@dataclass(frozen=True)
class MetricsSnapshot:
    """Point-in-time metrics from a single primitive call.

    Frozen to ensure snapshots are immutable once captured.
    """

    latency_ms: float
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model: str = ""
    provider: str = ""
    timestamp: float = field(default_factory=time.time)
    custom_metrics: dict[str, Any] = field(default_factory=dict)

    def asdict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for JSON encoding."""
        return asdict(self)


@dataclass
class PipelineResult:
    """Structured result from a pipeline execution.

    Mutable so the runner can populate fields incrementally.
    """

    output: Any
    metrics: MetricsSnapshot | None
    success: bool
    error: ErrorInfo | None = None
    duration_ms: float = 0.0

    def asdict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for JSON encoding."""
        return asdict(self)
