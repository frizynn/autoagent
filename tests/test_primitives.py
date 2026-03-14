"""Tests for autoagent.types and autoagent.primitives."""

from __future__ import annotations

import sys
import types
from unittest import mock

import pytest

from autoagent.primitives import (
    COST_PER_1K_TOKENS,
    LLM,
    MetricsCollector,
    MockLLM,
    MockRetriever,
    OpenAILLM,
    PrimitivesContext,
    Retriever,
    calculate_cost,
)
from autoagent.types import ErrorInfo, MetricsSnapshot, PipelineResult


# ── MetricsSnapshot ──────────────────────────────────────────────────────


class TestMetricsSnapshot:
    def test_creation_defaults(self) -> None:
        snap = MetricsSnapshot(latency_ms=10.0, tokens_in=5, tokens_out=15, cost_usd=0.001)
        assert snap.latency_ms == 10.0
        assert snap.tokens_in == 5
        assert snap.tokens_out == 15
        assert snap.cost_usd == 0.001
        assert snap.model == ""
        assert snap.provider == ""
        assert snap.custom_metrics == {}
        assert snap.timestamp > 0

    def test_creation_all_fields(self) -> None:
        snap = MetricsSnapshot(
            latency_ms=50.0,
            tokens_in=100,
            tokens_out=200,
            cost_usd=0.05,
            model="gpt-4o",
            provider="openai",
            timestamp=1234567890.0,
            custom_metrics={"quality": 0.9},
        )
        assert snap.model == "gpt-4o"
        assert snap.custom_metrics["quality"] == 0.9

    def test_frozen(self) -> None:
        snap = MetricsSnapshot(latency_ms=1.0, tokens_in=0, tokens_out=0, cost_usd=0.0)
        with pytest.raises(AttributeError):
            snap.latency_ms = 999.0  # type: ignore[misc]

    def test_asdict(self) -> None:
        snap = MetricsSnapshot(
            latency_ms=10.0, tokens_in=5, tokens_out=15, cost_usd=0.001, model="m"
        )
        d = snap.asdict()
        assert isinstance(d, dict)
        assert d["latency_ms"] == 10.0
        assert d["tokens_in"] == 5
        assert d["model"] == "m"
        # Should be JSON-serializable
        import json

        json.dumps(d)


# ── PipelineResult ───────────────────────────────────────────────────────


class TestPipelineResult:
    def test_success_result(self) -> None:
        snap = MetricsSnapshot(latency_ms=10.0, tokens_in=5, tokens_out=15, cost_usd=0.001)
        result = PipelineResult(output="hello", metrics=snap, success=True, duration_ms=12.0)
        assert result.success is True
        assert result.output == "hello"
        assert result.error is None
        assert result.duration_ms == 12.0

    def test_error_result(self) -> None:
        err = ErrorInfo(type="ValueError", message="bad input", traceback="Traceback ...")
        result = PipelineResult(output=None, metrics=None, success=False, error=err)
        assert result.success is False
        assert result.error is not None
        assert result.error.type == "ValueError"
        assert result.error.message == "bad input"

    def test_asdict(self) -> None:
        err = ErrorInfo(type="RuntimeError", message="boom")
        result = PipelineResult(output=None, metrics=None, success=False, error=err, duration_ms=5.0)
        d = result.asdict()
        assert d["success"] is False
        assert d["error"]["type"] == "RuntimeError"
        import json

        json.dumps(d)


# ── Cost calculation ─────────────────────────────────────────────────────


class TestCostCalculation:
    def test_known_model(self) -> None:
        # gpt-4o: input=0.0025, output=0.010 per 1K tokens
        cost = calculate_cost(1000, 1000, "gpt-4o")
        assert cost == pytest.approx(0.0025 + 0.010)

    def test_unknown_model_returns_zero(self) -> None:
        assert calculate_cost(100, 100, "unknown-model-xyz") == 0.0

    def test_custom_config_override(self) -> None:
        custom = {"my-model": (0.01, 0.02)}
        cost = calculate_cost(1000, 500, "my-model", cost_config=custom)
        assert cost == pytest.approx((1000 * 0.01 + 500 * 0.02) / 1000)

    def test_default_config_has_expected_models(self) -> None:
        for model in ("gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "claude-3.5-sonnet"):
            assert model in COST_PER_1K_TOKENS


# ── MockLLM ──────────────────────────────────────────────────────────────


class TestMockLLM:
    def test_returns_configured_response(self) -> None:
        llm = MockLLM(response="custom answer")
        assert llm.complete("anything") == "custom answer"

    def test_default_response(self) -> None:
        llm = MockLLM()
        assert llm.complete("hello") == "mock response"

    def test_registers_metrics_with_collector(self) -> None:
        collector = MetricsCollector()
        llm = MockLLM(
            response="ok",
            tokens_in=10,
            tokens_out=20,
            model="mock-llm",
            latency_ms=5.0,
            collector=collector,
        )
        llm.complete("test prompt")
        assert len(collector.snapshots) == 1
        snap = collector.snapshots[0]
        assert snap.tokens_in == 10
        assert snap.tokens_out == 20
        assert snap.latency_ms == 5.0
        assert snap.model == "mock-llm"
        assert snap.provider == "mock"

    def test_multiple_calls_accumulate(self) -> None:
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        for _ in range(3):
            llm.complete("x")
        assert len(collector.snapshots) == 3

    def test_satisfies_llm_protocol(self) -> None:
        assert isinstance(MockLLM(), LLM)


# ── MockRetriever ────────────────────────────────────────────────────────


class TestMockRetriever:
    def test_returns_configured_documents(self) -> None:
        ret = MockRetriever(documents=["a", "b", "c"])
        assert ret.retrieve("query") == ["a", "b", "c"]

    def test_default_documents(self) -> None:
        ret = MockRetriever()
        assert ret.retrieve("q") == ["doc1", "doc2"]

    def test_registers_metrics_with_collector(self) -> None:
        collector = MetricsCollector()
        ret = MockRetriever(
            tokens_in=8,
            tokens_out=0,
            latency_ms=2.0,
            collector=collector,
        )
        ret.retrieve("find stuff")
        assert len(collector.snapshots) == 1
        snap = collector.snapshots[0]
        assert snap.tokens_in == 8
        assert snap.latency_ms == 2.0

    def test_returns_copy_not_reference(self) -> None:
        ret = MockRetriever(documents=["x"])
        docs = ret.retrieve("q")
        docs.append("y")
        assert ret.retrieve("q") == ["x"]  # original unchanged

    def test_satisfies_retriever_protocol(self) -> None:
        assert isinstance(MockRetriever(), Retriever)


# ── MetricsCollector ─────────────────────────────────────────────────────


class TestMetricsCollector:
    def test_empty_aggregate(self) -> None:
        collector = MetricsCollector()
        agg = collector.aggregate()
        assert agg.latency_ms == 0.0
        assert agg.tokens_in == 0
        assert agg.tokens_out == 0
        assert agg.cost_usd == 0.0

    def test_aggregate_sums_correctly(self) -> None:
        collector = MetricsCollector()
        for i in range(5):
            collector.record(
                MetricsSnapshot(
                    latency_ms=10.0,
                    tokens_in=100,
                    tokens_out=200,
                    cost_usd=0.01,
                    model="m",
                    provider="p",
                )
            )
        agg = collector.aggregate()
        assert agg.latency_ms == pytest.approx(50.0)
        assert agg.tokens_in == 500
        assert agg.tokens_out == 1000
        assert agg.cost_usd == pytest.approx(0.05)

    def test_aggregate_uses_last_model(self) -> None:
        collector = MetricsCollector()
        collector.record(MetricsSnapshot(latency_ms=1, tokens_in=1, tokens_out=1, cost_usd=0, model="a", provider="x"))
        collector.record(MetricsSnapshot(latency_ms=1, tokens_in=1, tokens_out=1, cost_usd=0, model="b", provider="y"))
        agg = collector.aggregate()
        assert agg.model == "b"
        assert agg.provider == "y"

    def test_reset_clears_snapshots(self) -> None:
        collector = MetricsCollector()
        collector.record(MetricsSnapshot(latency_ms=1, tokens_in=1, tokens_out=1, cost_usd=0))
        collector.reset()
        assert len(collector.snapshots) == 0
        assert collector.aggregate().tokens_in == 0

    def test_mixed_provider_calls(self) -> None:
        """Aggregate works across different providers/models."""
        collector = MetricsCollector()
        llm = MockLLM(tokens_in=10, tokens_out=20, latency_ms=5, collector=collector)
        ret = MockRetriever(tokens_in=3, tokens_out=0, latency_ms=2, collector=collector)
        llm.complete("p1")
        ret.retrieve("q1")
        llm.complete("p2")
        agg = collector.aggregate()
        assert agg.tokens_in == 23  # 10+3+10
        assert agg.tokens_out == 40  # 20+0+20
        assert agg.latency_ms == pytest.approx(12.0)  # 5+2+5


# ── OpenAILLM ────────────────────────────────────────────────────────────


class TestOpenAILLM:
    def test_raises_import_error_when_openai_missing(self) -> None:
        """OpenAILLM.complete() raises a clear ImportError when openai is not installed."""
        llm = OpenAILLM()
        # Temporarily hide the openai module if it happens to be installed
        with mock.patch.dict(sys.modules, {"openai": None}):
            # Also need to ensure fresh import attempt
            llm._client = None
            with pytest.raises(ImportError, match="pip install openai"):
                llm.complete("hello")

    def test_import_error_message_is_actionable(self) -> None:
        llm = OpenAILLM()
        with mock.patch.dict(sys.modules, {"openai": None}):
            llm._client = None
            try:
                llm.complete("test")
            except ImportError as e:
                assert "pip install openai" in str(e)
            else:
                pytest.fail("Expected ImportError")

    def test_complete_with_mocked_openai(self) -> None:
        """Verify OpenAILLM correctly normalizes token fields from OpenAI response."""
        # Build a fake openai module
        fake_openai = types.ModuleType("openai")

        # Mock response structure
        mock_usage = mock.MagicMock()
        mock_usage.prompt_tokens = 50
        mock_usage.completion_tokens = 100

        mock_message = mock.MagicMock()
        mock_message.content = "openai says hello"

        mock_choice = mock.MagicMock()
        mock_choice.message = mock_message

        mock_response = mock.MagicMock()
        mock_response.usage = mock_usage
        mock_response.choices = [mock_choice]

        mock_client = mock.MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        mock_openai_class = mock.MagicMock(return_value=mock_client)
        fake_openai.OpenAI = mock_openai_class  # type: ignore[attr-defined]

        collector = MetricsCollector()
        llm = OpenAILLM(model="gpt-4o", api_key="test-key", collector=collector)

        with mock.patch.dict(sys.modules, {"openai": fake_openai}):
            llm._client = None  # force re-import
            result = llm.complete("test prompt")

        assert result == "openai says hello"
        assert len(collector.snapshots) == 1
        snap = collector.snapshots[0]
        assert snap.tokens_in == 50
        assert snap.tokens_out == 100
        assert snap.model == "gpt-4o"
        assert snap.provider == "openai"
        assert snap.latency_ms > 0
        assert snap.cost_usd > 0


# ── PrimitivesContext ────────────────────────────────────────────────────


class TestPrimitivesContext:
    def test_default_has_collector(self) -> None:
        ctx = PrimitivesContext()
        assert ctx.collector is not None
        assert isinstance(ctx.collector, MetricsCollector)
        assert ctx.llm is None
        assert ctx.retriever is None

    def test_configured_primitives(self) -> None:
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        ret = MockRetriever(collector=collector)
        ctx = PrimitivesContext(llm=llm, retriever=ret, collector=collector)
        assert ctx.llm is llm
        assert ctx.retriever is ret
        assert ctx.collector is collector

    def test_shared_collector_aggregates_across_primitives(self) -> None:
        collector = MetricsCollector()
        llm = MockLLM(tokens_in=10, tokens_out=20, collector=collector)
        ret = MockRetriever(tokens_in=5, tokens_out=0, collector=collector)
        ctx = PrimitivesContext(llm=llm, retriever=ret, collector=collector)

        ctx.llm.complete("p")  # type: ignore[union-attr]
        ctx.retriever.retrieve("q")  # type: ignore[union-attr]

        agg = ctx.collector.aggregate()
        assert agg.tokens_in == 15
        assert agg.tokens_out == 20
