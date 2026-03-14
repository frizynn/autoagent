"""Primitive protocols, concrete providers, and metrics collection for AutoAgent."""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

from autoagent.types import MetricsSnapshot

# ---------------------------------------------------------------------------
# Cost configuration — USD per 1K tokens (input, output)
# ---------------------------------------------------------------------------

COST_PER_1K_TOKENS: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (0.0025, 0.010),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4-turbo": (0.010, 0.030),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    # Anthropic
    "claude-3.5-sonnet": (0.003, 0.015),
    "claude-3-opus": (0.015, 0.075),
    "claude-3-haiku": (0.00025, 0.00125),
}


def calculate_cost(
    tokens_in: int,
    tokens_out: int,
    model: str,
    cost_config: dict[str, tuple[float, float]] | None = None,
) -> float:
    """Calculate USD cost from token counts and model name.

    Looks up per-1K-token prices from *cost_config* (falls back to
    ``COST_PER_1K_TOKENS``).  Returns 0.0 for unknown models.
    """
    config = cost_config if cost_config is not None else COST_PER_1K_TOKENS
    prices = config.get(model)
    if prices is None:
        return 0.0
    input_price, output_price = prices
    return (tokens_in * input_price + tokens_out * output_price) / 1000


# ---------------------------------------------------------------------------
# Protocols — structural contracts for primitives
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProtocol(Protocol):
    """Structural interface for language-model primitives."""

    def complete(self, prompt: str, **kwargs: Any) -> str: ...


@runtime_checkable
class RetrieverProtocol(Protocol):
    """Structural interface for document-retrieval primitives."""

    def retrieve(self, query: str, **kwargs: Any) -> list[str]: ...


# ---------------------------------------------------------------------------
# MetricsCollector — accumulates per-call snapshots
# ---------------------------------------------------------------------------


class MetricsCollector:
    """Accumulates :class:`MetricsSnapshot` objects across primitive calls.

    Inspection surface:
        - ``.snapshots`` — list of every individual call snapshot
        - ``.aggregate()`` — single snapshot with summed values
    """

    def __init__(self) -> None:
        self.snapshots: list[MetricsSnapshot] = []

    def record(self, snapshot: MetricsSnapshot) -> None:
        """Register a single-call snapshot."""
        self.snapshots.append(snapshot)

    def aggregate(self) -> MetricsSnapshot:
        """Return a single snapshot with summed metrics across all calls.

        If no snapshots have been recorded, returns a zero-valued snapshot.
        """
        if not self.snapshots:
            return MetricsSnapshot(
                latency_ms=0.0,
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,
            )
        return MetricsSnapshot(
            latency_ms=sum(s.latency_ms for s in self.snapshots),
            tokens_in=sum(s.tokens_in for s in self.snapshots),
            tokens_out=sum(s.tokens_out for s in self.snapshots),
            cost_usd=sum(s.cost_usd for s in self.snapshots),
            model=self.snapshots[-1].model,
            provider=self.snapshots[-1].provider,
        )

    def reset(self) -> None:
        """Clear all recorded snapshots."""
        self.snapshots.clear()


# ---------------------------------------------------------------------------
# PrimitivesContext — namespace holding configured instances
# ---------------------------------------------------------------------------


class PrimitivesContext:
    """Namespace that holds configured primitive instances and a shared collector.

    Pipeline code receives this as the ``primitives`` argument to ``run()``.
    """

    def __init__(
        self,
        llm: LLMProtocol | None = None,
        retriever: RetrieverProtocol | None = None,
        collector: MetricsCollector | None = None,
    ) -> None:
        self.llm = llm
        self.retriever = retriever
        self.collector = collector or MetricsCollector()


# ---------------------------------------------------------------------------
# Concrete providers — MockLLM, MockRetriever, OpenAILLM
# ---------------------------------------------------------------------------


class MockLLM:
    """In-process mock LLM that returns configurable responses.

    Every call registers a :class:`MetricsSnapshot` with the collector.
    """

    def __init__(
        self,
        response: str = "mock response",
        tokens_in: int = 10,
        tokens_out: int = 20,
        model: str = "mock-llm",
        latency_ms: float = 1.0,
        collector: MetricsCollector | None = None,
        cost_config: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.response = response
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.model = model
        self.latency_ms = latency_ms
        self.collector = collector
        self.cost_config = cost_config

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Return the pre-configured response and record metrics."""
        cost = calculate_cost(
            self.tokens_in, self.tokens_out, self.model, self.cost_config
        )
        snapshot = MetricsSnapshot(
            latency_ms=self.latency_ms,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            cost_usd=cost,
            model=self.model,
            provider="mock",
        )
        if self.collector is not None:
            self.collector.record(snapshot)
        return self.response


class MockRetriever:
    """In-process mock retriever that returns configurable documents.

    Every call registers a :class:`MetricsSnapshot` with the collector.
    """

    def __init__(
        self,
        documents: list[str] | None = None,
        tokens_in: int = 5,
        tokens_out: int = 0,
        model: str = "mock-retriever",
        latency_ms: float = 0.5,
        collector: MetricsCollector | None = None,
        cost_config: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.documents = documents if documents is not None else ["doc1", "doc2"]
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.model = model
        self.latency_ms = latency_ms
        self.collector = collector
        self.cost_config = cost_config

    def retrieve(self, query: str, **kwargs: Any) -> list[str]:
        """Return the pre-configured documents and record metrics."""
        cost = calculate_cost(
            self.tokens_in, self.tokens_out, self.model, self.cost_config
        )
        snapshot = MetricsSnapshot(
            latency_ms=self.latency_ms,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            cost_usd=cost,
            model=self.model,
            provider="mock",
        )
        if self.collector is not None:
            self.collector.record(snapshot)
        return list(self.documents)


class OpenAILLM:
    """OpenAI LLM provider with lazy SDK import.

    The ``openai`` package is imported inside :meth:`complete` so that the
    rest of the library works without the SDK installed.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        collector: MetricsCollector | None = None,
        cost_config: dict[str, tuple[float, float]] | None = None,
        **client_kwargs: Any,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.collector = collector
        self.cost_config = cost_config
        self._client_kwargs = client_kwargs
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazily create the OpenAI client, raising a clear error if missing."""
        if self._client is not None:
            return self._client
        try:
            import openai  # noqa: F811
        except ImportError:
            raise ImportError(
                "The openai package is required for OpenAILLM. "
                "Install it with: pip install openai"
            ) from None
        kwargs: dict[str, Any] = {**self._client_kwargs}
        if self.api_key is not None:
            kwargs["api_key"] = self.api_key
        self._client = openai.OpenAI(**kwargs)
        return self._client

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Send a completion request to OpenAI and return the response text.

        Captures latency, token counts, and cost in a MetricsSnapshot.
        """
        client = self._get_client()

        model = kwargs.pop("model", self.model)
        messages = kwargs.pop("messages", [{"role": "user", "content": prompt}])

        t0 = time.perf_counter()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs,
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        # Normalize OpenAI's token field names
        usage = response.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0
        cost = calculate_cost(tokens_in, tokens_out, model, self.cost_config)

        snapshot = MetricsSnapshot(
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            model=model,
            provider="openai",
        )
        if self.collector is not None:
            self.collector.record(snapshot)

        return response.choices[0].message.content or ""


# Public aliases matching the slice plan's expected import names
LLM = LLMProtocol
Retriever = RetrieverProtocol
