"""Tests for MetaAgent — prompt construction, source extraction, validation, propose flow."""

from __future__ import annotations

import pytest

from autoagent.archive import ArchiveEntry
from autoagent.meta_agent import MetaAgent, ProposalResult, build_component_vocabulary
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


# ---------------------------------------------------------------------------
# archive_summary parameter in _build_prompt
# ---------------------------------------------------------------------------


class TestArchiveSummaryPrompt:
    """Tests for the archive_summary parameter in _build_prompt()."""

    def test_archive_summary_replaces_raw_entries(self):
        """When archive_summary is set, it appears and raw entry sections do not."""
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        agent = MetaAgent(llm, goal="Maximize accuracy")

        kept = [_make_entry(1, "keep", 0.9, "good iteration")]
        discarded = [_make_entry(2, "discard", 0.3, "bad iteration")]

        prompt = agent._build_prompt(
            "source code",
            kept,
            discarded,
            archive_summary="## Top-K Results\n- Iteration 1 (score=0.9)",
        )

        # Archive Summary section should be present
        assert "## Archive Summary" in prompt
        assert "## Top-K Results" in prompt
        assert "Iteration 1 (score=0.9)" in prompt

        # Raw entry sections should NOT be present
        assert "## Top Kept Iterations" not in prompt
        assert "## Recent Discarded Iterations" not in prompt

    def test_no_archive_summary_preserves_raw_entries(self):
        """When archive_summary is empty, raw kept/discarded sections appear as before."""
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        agent = MetaAgent(llm, goal="Maximize accuracy")

        kept = [_make_entry(1, "keep", 0.9, "good iteration")]
        discarded = [_make_entry(2, "discard", 0.3, "bad iteration")]

        prompt = agent._build_prompt("source code", kept, discarded)

        # Raw entry sections should be present
        assert "## Top Kept Iterations" in prompt
        assert "## Recent Discarded Iterations" in prompt
        assert "good iteration" in prompt
        assert "bad iteration" in prompt

        # Archive Summary section should NOT be present
        assert "## Archive Summary" not in prompt


# ---------------------------------------------------------------------------
# Component vocabulary
# ---------------------------------------------------------------------------


class TestComponentVocabulary:
    """Tests for build_component_vocabulary() and its injection into prompts."""

    def test_vocabulary_section_in_prompt(self):
        """_build_prompt() output includes the vocabulary section header."""
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        agent = MetaAgent(llm, goal="test")
        prompt = agent._build_prompt("source", [], [])
        assert "## Component Vocabulary" in prompt

    def test_vocabulary_contains_primitives(self):
        """Vocabulary mentions both primitive signatures."""
        vocab = build_component_vocabulary()
        assert "primitives.llm.complete" in vocab
        assert "primitives.retriever.retrieve" in vocab

    def test_vocabulary_contains_all_patterns(self):
        """Vocabulary contains all 6 architectural pattern names."""
        vocab = build_component_vocabulary()
        for pattern in ["RAG", "CAG", "Debate", "Reflexion", "Ensemble", "Reranking"]:
            assert pattern in vocab, f"Missing pattern: {pattern}"

    def test_vocabulary_contains_anti_patterns(self):
        """Vocabulary warns against hardcoded imports and missing primitives."""
        vocab = build_component_vocabulary()
        assert "import openai" in vocab
        assert "import anthropic" in vocab
        assert "hardcode" in vocab.lower() or "hardcoded" in vocab.lower()
        assert "primitives" in vocab

    def test_vocabulary_token_budget(self):
        """Vocabulary output stays under ~2K tokens (~8K chars)."""
        vocab = build_component_vocabulary()
        assert len(vocab) < 8000, f"Vocabulary is {len(vocab)} chars, exceeds 8000 budget"

    def test_system_instructions_mention_structural_changes(self):
        """System instructions section mentions architecture/structural changes."""
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        agent = MetaAgent(llm, goal="test")
        prompt = agent._build_prompt("source", [], [])
        # The system instructions are the first section, before ## Goal
        system_section = prompt.split("## Goal")[0]
        assert "architecture" in system_section.lower()

    def test_vocabulary_skeletons_use_primitives(self):
        """All pattern skeletons call primitives.llm or primitives.retriever, never raw imports."""
        vocab = build_component_vocabulary()
        # Every skeleton should use primitives
        assert "primitives.llm.complete(" in vocab
        # No raw provider imports in skeletons
        assert "from openai" not in vocab
        assert "from anthropic" not in vocab


# ---------------------------------------------------------------------------
# Strategy signals in prompt
# ---------------------------------------------------------------------------


class TestStrategySignals:
    """Tests for strategy_signals parameter in _build_prompt() and propose()."""

    def test_strategy_signals_in_prompt(self):
        """## Strategy Guidance section appears when strategy_signals is non-empty."""
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        agent = MetaAgent(llm, goal="test")
        prompt = agent._build_prompt(
            "source", [], [],
            strategy_signals="Consider structural changes — plateau detected.",
        )
        assert "## Strategy Guidance" in prompt
        assert "Consider structural changes" in prompt
        assert "plateau detected" in prompt

    def test_strategy_signals_empty_omitted(self):
        """## Strategy Guidance section is absent when strategy_signals is empty."""
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        agent = MetaAgent(llm, goal="test")
        prompt = agent._build_prompt("source", [], [], strategy_signals="")
        assert "## Strategy Guidance" not in prompt
        assert "Strategy Guidance" not in prompt

    def test_propose_forwards_strategy_signals(self):
        """propose() passes strategy_signals through to _build_prompt()."""
        collector = MetricsCollector()
        llm = MockLLM(
            response=VALID_PIPELINE_FENCED_WITH_RATIONALE,
            collector=collector,
        )
        agent = MetaAgent(llm, goal="test")

        # Capture the prompt that was sent to the LLM
        result = agent.propose(
            current_source=VALID_PIPELINE,
            strategy_signals="Try parameter tuning within current topology.",
        )
        assert result.success is True
        # The MockLLM received a prompt — check it contained strategy signals
        # MockLLM stores the last prompt it received
        last_prompt = llm.last_prompt
        assert "## Strategy Guidance" in last_prompt
        assert "Try parameter tuning" in last_prompt

    def test_strategy_signals_after_history_sections(self):
        """Strategy Guidance section appears after archive/history sections."""
        collector = MetricsCollector()
        llm = MockLLM(collector=collector)
        agent = MetaAgent(llm, goal="test")
        kept = [_make_entry(1, "keep", 0.9, "good")]
        prompt = agent._build_prompt(
            "source", kept, [],
            strategy_signals="Focus on structural changes.",
        )
        # Strategy Guidance should come after Top Kept Iterations
        kept_pos = prompt.index("## Top Kept Iterations")
        strategy_pos = prompt.index("## Strategy Guidance")
        assert strategy_pos > kept_pos
