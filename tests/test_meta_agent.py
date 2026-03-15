"""Tests for MetaAgent — prompt construction, source extraction, validation, propose flow."""

from __future__ import annotations

import pytest

from autoagent.archive import ArchiveEntry
from autoagent.meta_agent import MetaAgent, ProposalResult
from autoagent.primitives import MetricsCollector, MockLLM


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_PIPELINE = (
    'def run(input_data, primitives=None):\n'
    '    return {"answer": "hello"}\n'
)

VALID_PIPELINE_FENCED = f"```python\n{VALID_PIPELINE}```"

VALID_PIPELINE_FENCED_WITH_RATIONALE = (
    f"Here is the improved pipeline:\n\n{VALID_PIPELINE_FENCED}\n\n"
    "I simplified the return value."
)

SYNTAX_ERROR_SOURCE = "def run(input_data, primitives=None)\n    return 42\n"

MISSING_RUN_SOURCE = "def process(data):\n    return data\n"

RUN_NOT_CALLABLE = "run = 42\n"


def _make_entry(
    iteration_id: int,
    decision: str = "keep",
    score: float = 0.8,
    rationale: str = "test rationale",
) -> ArchiveEntry:
    """Create a minimal ArchiveEntry for prompt testing."""
    return ArchiveEntry(
        iteration_id=iteration_id,
        timestamp=1000.0 + iteration_id,
        pipeline_diff="",
        evaluation_result={
            "primary_score": score,
            "per_example_results": [],
            "benchmark_id": "test",
            "duration_ms": 100.0,
            "num_examples": 1,
            "num_failures": 0,
        },
        rationale=rationale,
        decision=decision,
    )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    """Tests for MetaAgent._build_prompt()."""

    def test_prompt_includes_goal(self):
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        agent = MetaAgent(llm, goal="Maximize accuracy")
        prompt = agent._build_prompt("source code", [], [])
        assert "Maximize accuracy" in prompt

    def test_prompt_includes_current_pipeline(self):
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        agent = MetaAgent(llm, goal="test")
        prompt = agent._build_prompt("my_pipeline_code()", [], [])
        assert "my_pipeline_code()" in prompt

    def test_prompt_includes_kept_history(self):
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        agent = MetaAgent(llm, goal="test")
        kept = [_make_entry(1, "keep", 0.9, "improved scoring")]
        prompt = agent._build_prompt("source", kept, [])
        assert "Iteration 1" in prompt
        assert "0.9" in prompt
        assert "improved scoring" in prompt

    def test_prompt_includes_discarded_history(self):
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        agent = MetaAgent(llm, goal="test")
        discarded = [_make_entry(2, "discard", 0.3, "broke parsing")]
        prompt = agent._build_prompt("source", [], discarded)
        assert "Iteration 2" in prompt
        assert "broke parsing" in prompt
        assert "Discarded" in prompt

    def test_prompt_includes_benchmark_description(self):
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        agent = MetaAgent(llm, goal="test")
        prompt = agent._build_prompt("source", [], [], benchmark_description="QA benchmark with 50 examples")
        assert "QA benchmark with 50 examples" in prompt

    def test_prompt_includes_run_signature_instruction(self):
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        agent = MetaAgent(llm, goal="test")
        prompt = agent._build_prompt("source", [], [])
        assert "def run(input_data, primitives=None)" in prompt


# ---------------------------------------------------------------------------
# Source extraction
# ---------------------------------------------------------------------------

class TestExtractSource:
    """Tests for MetaAgent._extract_source()."""

    def test_clean_source_no_fences(self):
        source = MetaAgent._extract_source(VALID_PIPELINE)
        assert "def run" in source
        assert "```" not in source

    def test_single_fenced_block(self):
        source = MetaAgent._extract_source(VALID_PIPELINE_FENCED)
        assert "def run" in source
        assert "```" not in source

    def test_fenced_block_with_surrounding_text(self):
        source = MetaAgent._extract_source(VALID_PIPELINE_FENCED_WITH_RATIONALE)
        assert "def run" in source
        assert "```" not in source
        # Should not include the rationale text
        assert "I simplified" not in source

    def test_multiple_fenced_blocks_picks_longest(self):
        short_block = '```python\nx = 1\n```'
        long_block = f'```python\n{VALID_PIPELINE}```'
        response = f"First:\n{short_block}\n\nSecond:\n{long_block}"
        source = MetaAgent._extract_source(response)
        assert "def run" in source
        assert source.strip() == VALID_PIPELINE.strip()

    def test_empty_response(self):
        source = MetaAgent._extract_source("")
        assert source == ""

    def test_no_fence_treats_entire_response_as_source(self):
        raw = "import os\ndef run(input_data, primitives=None):\n    return {}\n"
        source = MetaAgent._extract_source(raw)
        assert source == raw.strip()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidateSource:
    """Tests for MetaAgent._validate_source()."""

    def test_valid_pipeline(self):
        assert MetaAgent._validate_source(VALID_PIPELINE) is None

    def test_syntax_error(self):
        error = MetaAgent._validate_source(SYNTAX_ERROR_SOURCE)
        assert error is not None
        assert "syntax error" in error

    def test_missing_run(self):
        error = MetaAgent._validate_source(MISSING_RUN_SOURCE)
        assert error is not None
        assert "missing run() function" in error

    def test_run_not_callable(self):
        error = MetaAgent._validate_source(RUN_NOT_CALLABLE)
        assert error is not None
        assert "run is not callable" in error

    def test_empty_source(self):
        error = MetaAgent._validate_source("")
        # Empty source compiles fine but has no run
        assert error is not None
        assert "missing run() function" in error


# ---------------------------------------------------------------------------
# Full propose() flow
# ---------------------------------------------------------------------------

class TestPropose:
    """End-to-end tests for MetaAgent.propose()."""

    def test_valid_proposal(self):
        collector = MetricsCollector()
        llm = MockLLM(
            response=VALID_PIPELINE_FENCED_WITH_RATIONALE,
            collector=collector,
        )
        agent = MetaAgent(llm, goal="Maximize accuracy")
        result = agent.propose(
            current_source=VALID_PIPELINE,
            kept_entries=[_make_entry(1)],
            discarded_entries=[_make_entry(2, "discard")],
        )
        assert result.success is True
        assert result.error is None
        assert "def run" in result.proposed_source
        assert result.rationale  # should have rationale text

    def test_invalid_python_proposal(self):
        collector = MetricsCollector()
        llm = MockLLM(
            response=f"```python\n{SYNTAX_ERROR_SOURCE}```",
            collector=collector,
        )
        agent = MetaAgent(llm, goal="test")
        result = agent.propose(current_source=VALID_PIPELINE)
        assert result.success is False
        assert result.error is not None
        assert "syntax error" in result.error

    def test_missing_run_proposal(self):
        collector = MetricsCollector()
        llm = MockLLM(
            response=f"```python\n{MISSING_RUN_SOURCE}```",
            collector=collector,
        )
        agent = MetaAgent(llm, goal="test")
        result = agent.propose(current_source=VALID_PIPELINE)
        assert result.success is False
        assert "missing run() function" in result.error

    def test_empty_response_proposal(self):
        collector = MetricsCollector()
        llm = MockLLM(response="", collector=collector)
        agent = MetaAgent(llm, goal="test")
        result = agent.propose(current_source=VALID_PIPELINE)
        assert result.success is False
        assert result.error == "empty response"

    def test_whitespace_only_response(self):
        collector = MetricsCollector()
        llm = MockLLM(response="   \n\n  ", collector=collector)
        agent = MetaAgent(llm, goal="test")
        result = agent.propose(current_source=VALID_PIPELINE)
        assert result.success is False
        assert result.error == "empty response"

    def test_cost_tracking(self):
        """Meta-agent LLM cost is tracked via its own MetricsCollector."""
        collector = MetricsCollector()
        llm = MockLLM(
            response=VALID_PIPELINE_FENCED,
            tokens_in=100,
            tokens_out=200,
            model="gpt-4o-mini",
            collector=collector,
        )
        agent = MetaAgent(llm, goal="test")
        result = agent.propose(current_source="pass")
        # MockLLM records metrics in the collector
        assert len(collector.snapshots) == 1
        assert collector.snapshots[0].tokens_in == 100
        assert collector.snapshots[0].tokens_out == 200
        # ProposalResult captures the cost
        assert result.cost_usd == collector.aggregate().cost_usd
        assert result.cost_usd > 0  # gpt-4o-mini has known pricing

    def test_cost_not_mixed_with_separate_collector(self):
        """Two separate MetricsCollectors stay independent."""
        meta_collector = MetricsCollector()
        pipeline_collector = MetricsCollector()

        meta_llm = MockLLM(
            response=VALID_PIPELINE_FENCED,
            tokens_in=50,
            tokens_out=100,
            collector=meta_collector,
        )
        pipeline_llm = MockLLM(
            response="pipeline answer",
            tokens_in=10,
            tokens_out=20,
            collector=pipeline_collector,
        )

        agent = MetaAgent(meta_llm, goal="test")
        agent.propose(current_source="pass")

        # Simulate a pipeline LLM call
        pipeline_llm.complete("some prompt")

        # Collectors are independent
        assert len(meta_collector.snapshots) == 1
        assert len(pipeline_collector.snapshots) == 1
        assert meta_collector.aggregate().tokens_in == 50
        assert pipeline_collector.aggregate().tokens_in == 10


# ---------------------------------------------------------------------------
# Import contract
# ---------------------------------------------------------------------------

class TestImportContract:
    def test_importable(self):
        from autoagent.meta_agent import MetaAgent, ProposalResult
        assert MetaAgent is not None
        assert ProposalResult is not None
