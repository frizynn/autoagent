"""Tests for InterviewOrchestrator — vague-input detection, multi-turn flow,
config generation, context.md output, and SequenceMockLLM."""

from __future__ import annotations

import pytest

from autoagent.interview import (
    InterviewOrchestrator,
    InterviewResult,
    SequenceMockLLM,
    is_vague,
    PHASES,
    MAX_RETRIES_PER_PHASE,
)
from autoagent.state import ProjectConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_input_fn(answers: list[str]):
    """Return an input_fn that yields answers in order."""
    it = iter(answers)
    def input_fn(prompt: str = "") -> str:
        return next(it, "")
    return input_fn


def _make_print_fn() -> tuple[list[str], callable]:
    """Return (captured_lines, print_fn)."""
    lines: list[str] = []
    def print_fn(text: str = "") -> None:
        lines.append(str(text))
    return lines, print_fn


def _run_interview(
    user_answers: list[str],
    llm_responses: list[str] | None = None,
) -> tuple[InterviewResult, InterviewOrchestrator]:
    """Run a full interview with given user answers and LLM responses."""
    if llm_responses is None:
        # Default: LLM generates probes and context
        llm_responses = ["Can you be more specific?"] * 20
    llm = SequenceMockLLM(llm_responses)
    lines, print_fn = _make_print_fn()
    input_fn = _make_input_fn(user_answers)
    orch = InterviewOrchestrator(llm=llm, input_fn=input_fn, print_fn=print_fn)
    result = orch.run()
    return result, orch


# ---------------------------------------------------------------------------
# SequenceMockLLM tests
# ---------------------------------------------------------------------------


class TestSequenceMockLLM:
    def test_returns_responses_in_order(self):
        llm = SequenceMockLLM(["first", "second", "third"])
        assert llm.complete("a") == "first"
        assert llm.complete("b") == "second"
        assert llm.complete("c") == "third"

    def test_cycles_when_exhausted(self):
        llm = SequenceMockLLM(["alpha", "beta"])
        assert llm.complete("1") == "alpha"
        assert llm.complete("2") == "beta"
        assert llm.complete("3") == "alpha"

    def test_tracks_call_count(self):
        llm = SequenceMockLLM(["x"])
        llm.complete("a")
        llm.complete("b")
        assert llm.call_count == 2

    def test_records_prompts(self):
        llm = SequenceMockLLM(["x"])
        llm.complete("hello")
        llm.complete("world")
        assert llm.prompts == ["hello", "world"]

    def test_empty_responses_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            SequenceMockLLM([])


# ---------------------------------------------------------------------------
# Vague-input detection tests
# ---------------------------------------------------------------------------


class TestVagueDetection:
    def test_empty_string_is_vague(self):
        assert is_vague("") is True

    def test_whitespace_only_is_vague(self):
        assert is_vague("   ") is True

    def test_short_answer_is_vague(self):
        assert is_vague("yes") is True
        assert is_vague("ok fine") is True

    def test_vague_phrase_is_vague(self):
        assert is_vague("better") is True
        assert is_vague("IMPROVE") is True
        assert is_vague("not sure") is True

    def test_specific_answer_is_not_vague(self):
        assert is_vague("Minimize latency of API responses below 200ms") is False

    def test_long_enough_non_vague_is_fine(self):
        assert is_vague("use gradient descent with learning rate 0.01") is False


# ---------------------------------------------------------------------------
# Happy-path interview
# ---------------------------------------------------------------------------


class TestHappyPath:
    """All phases answered clearly → valid config with all fields."""

    CLEAR_ANSWERS = [
        "Minimize API response latency below 200ms p99",        # goal
        "p99 latency, throughput, error rate",                  # metrics
        "Budget under $50, must run on CPU only",               # constraints
        "Connection pooling, caching strategies, query tuning", # search_space
        "data/benchmark.csv with RMSE scoring",                 # benchmark
        "$25 for this optimization run",                          # budget
        "yes",                                                  # confirmation
    ]

    def test_produces_valid_result(self):
        # LLM responses: probes (unused in happy path) + context generation
        llm_responses = [
            "# Project Context\n\nThis project focuses on latency optimization."
        ]
        result, orch = _run_interview(self.CLEAR_ANSWERS, llm_responses)

        assert isinstance(result, InterviewResult)
        assert isinstance(result.config, ProjectConfig)
        assert result.context  # non-empty

    def test_config_has_goal(self):
        result, _ = _run_interview(self.CLEAR_ANSWERS)
        assert "latency" in result.config.goal.lower()

    def test_config_has_metric_priorities(self):
        result, _ = _run_interview(self.CLEAR_ANSWERS)
        assert len(result.config.metric_priorities) >= 2
        assert "p99 latency" in result.config.metric_priorities

    def test_config_has_constraints(self):
        result, _ = _run_interview(self.CLEAR_ANSWERS)
        assert len(result.config.constraints) >= 1

    def test_config_has_search_space(self):
        result, _ = _run_interview(self.CLEAR_ANSWERS)
        assert len(result.config.search_space) >= 2

    def test_config_has_budget(self):
        result, _ = _run_interview(self.CLEAR_ANSWERS)
        assert result.config.budget_usd == 25.0

    def test_phase_is_complete(self):
        _, orch = _run_interview(self.CLEAR_ANSWERS)
        assert orch.phase == "complete"

    def test_all_phases_recorded_in_state(self):
        _, orch = _run_interview(self.CLEAR_ANSWERS)
        for phase_key, _ in PHASES:
            assert phase_key in orch.state


# ---------------------------------------------------------------------------
# Vague-input triggers follow-up probe
# ---------------------------------------------------------------------------


class TestVagueInputTriggersProbe:
    def test_vague_goal_triggers_followup(self):
        """'make it better' as goal triggers a follow-up probe."""
        answers = [
            "better",                                                   # vague goal
            "Reduce inference latency to under 100ms",                  # clarified goal
            "accuracy, latency",                                        # metrics (clear enough)
            "Must fit in 8GB VRAM",                                     # constraints
            "Quantization, pruning, distillation",                      # search_space
            "test/bench.csv with F1 score",                             # benchmark
            "$10 budget for this run",                                                    # budget
            "yes",                                                      # confirmation
        ]
        llm_responses = [
            "What specifically do you want to make better? "
            "Can you describe the current performance and your target?",
            "# Context\n\nLatency optimization project.",
        ]
        result, orch = _run_interview(answers, llm_responses)

        # The clarified answer should be recorded, not the vague one
        assert "latency" in orch.state["goal"].lower()
        assert orch._vague_flags.get("goal", 0) >= 1

    def test_empty_answer_triggers_probe(self):
        """Empty string triggers a follow-up probe."""
        answers = [
            "",                                                         # empty goal
            "Optimize model throughput for batch processing",           # clarified
            "throughput, cost per inference",                           # metrics
            "Max budget $100",                                         # constraints
            "Batching, async processing",                              # search_space
            "benchmark/data.json with throughput metric",              # benchmark
            "$50 budget for this run",                                                      # budget
            "yes",                                                     # confirmation
        ]
        llm_responses = [
            "Could you describe what you're trying to optimize?",
            "# Context\n\nBatch processing optimization.",
        ]
        result, orch = _run_interview(answers, llm_responses)
        assert "throughput" in orch.state["goal"].lower()


# ---------------------------------------------------------------------------
# Max retries — after 2 vague attempts, accept and move on
# ---------------------------------------------------------------------------


class TestMaxRetries:
    def test_accepts_after_max_retries(self):
        """After MAX_RETRIES_PER_PHASE vague attempts, orchestrator moves on."""
        answers = [
            "ok",                                                       # vague goal attempt 1
            "fine",                                                     # vague goal attempt 2 (after probe)
            "meh",                                                      # vague goal attempt 3 — accepted (max retries hit)
            "accuracy, recall",                                         # metrics
            "none really",                                              # constraints (short but >10? no, 11 chars)
            "try everything",                                           # search_space
            "no benchmark yet",                                         # benchmark
            "$20 budget for this run",                                                       # budget (short but numeric)
            "yes",                                                      # confirmation
        ]
        llm_responses = [
            "What exactly is your goal? Please be specific.",
            "I need more detail. What metric are you optimizing?",
            "# Context\n\nProject with vague goals.",
        ]
        result, orch = _run_interview(answers, llm_responses)

        # Goal should be the last vague answer accepted after max retries
        assert orch.state["goal"] == "meh"
        assert orch._vague_flags.get("goal", 0) == MAX_RETRIES_PER_PHASE


# ---------------------------------------------------------------------------
# Config output validation
# ---------------------------------------------------------------------------


class TestConfigOutput:
    def test_generated_config_has_correct_field_values(self):
        answers = [
            "Maximize classification accuracy on imbalanced data",
            "F1 score; precision; recall",
            "Must use PyTorch; max 4 GPU hours",
            "SMOTE, class weights, focal loss",
            "data/imbalanced.csv with weighted F1",
            "$75 for the full run",
            "yes",
        ]
        llm_responses = ["# Context\n\nClassification project."]
        result, _ = _run_interview(answers, llm_responses)

        cfg = result.config
        assert "accuracy" in cfg.goal.lower()
        assert cfg.budget_usd == 75.0
        assert "F1 score" in cfg.metric_priorities
        assert "precision" in cfg.metric_priorities
        assert len(cfg.constraints) >= 1
        assert len(cfg.search_space) >= 2

    def test_config_serialization_roundtrip(self):
        """ProjectConfig with new fields serializes/deserializes correctly."""
        cfg = ProjectConfig(
            goal="test goal",
            search_space=["option1", "option2"],
            constraints=["budget < 100"],
            metric_priorities=["accuracy", "speed"],
            budget_usd=42.0,
        )
        data = cfg.asdict()
        restored = ProjectConfig.from_dict(data)
        assert restored == cfg
        assert restored.search_space == ["option1", "option2"]
        assert restored.constraints == ["budget < 100"]
        assert restored.metric_priorities == ["accuracy", "speed"]


# ---------------------------------------------------------------------------
# Context output
# ---------------------------------------------------------------------------


class TestContextOutput:
    def test_context_is_nonempty(self):
        answers = [
            "Optimize recommendation engine click-through rate",
            "CTR, conversion rate",
            "Latency under 50ms",
            "Collaborative filtering, content-based, hybrid",
            "clickstream.parquet with nDCG",
            "30",
            "yes",
        ]
        llm_responses = [
            "# Recommendation Engine Optimization\n\n"
            "Goal: Improve CTR using collaborative and content-based approaches."
        ]
        result, _ = _run_interview(answers, llm_responses)
        assert len(result.context) > 0

    def test_context_contains_key_terms(self):
        answers = [
            "Reduce inference latency for real-time serving",
            "p99 latency, throughput",
            "Must deploy on edge devices",
            "Model pruning, quantization",
            "serving_bench.csv with latency percentiles",
            "15",
            "yes",
        ]
        llm_responses = [
            "# Real-time Serving Optimization\n\n"
            "Focus on reducing inference latency through pruning and quantization "
            "for edge deployment. Key metrics: p99 latency and throughput."
        ]
        result, _ = _run_interview(answers, llm_responses)
        assert "latency" in result.context.lower()


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_config_without_new_fields_deserializes(self):
        """Old config.json without new fields loads fine."""
        old_data = {
            "version": 1,
            "goal": "old goal",
            "benchmark": {"dataset_path": "", "scoring_function": ""},
            "budget_usd": 10.0,
            "pipeline_path": "pipeline.py",
        }
        cfg = ProjectConfig.from_dict(old_data)
        assert cfg.goal == "old goal"
        assert cfg.search_space == []
        assert cfg.constraints == []
        assert cfg.metric_priorities == []

    def test_config_with_extra_unknown_keys(self):
        """from_dict ignores unknown keys."""
        data = {
            "version": 1,
            "goal": "test",
            "future_field": "ignored",
            "search_space": ["a"],
        }
        cfg = ProjectConfig.from_dict(data)
        assert cfg.search_space == ["a"]
        assert not hasattr(cfg, "future_field")


# ---------------------------------------------------------------------------
# Observability — state inspection
# ---------------------------------------------------------------------------


class TestObservability:
    def test_state_dict_inspectable_during_interview(self):
        """The state dict is populated phase by phase."""
        answers = [
            "Optimize database query performance",
            "query time, throughput",
            "PostgreSQL only",
            "Index tuning, query rewriting",
            "queries.sql with execution time",
            "5",
            "yes",
        ]
        llm_responses = ["# DB Optimization Context"]
        llm = SequenceMockLLM(llm_responses)
        lines, print_fn = _make_print_fn()
        input_fn = _make_input_fn(answers)
        orch = InterviewOrchestrator(llm=llm, input_fn=input_fn, print_fn=print_fn)

        result = orch.run()

        # All phases should be in state
        assert "goal" in orch.state
        assert "metrics" in orch.state
        assert "confirmed" in orch.state
        assert orch.phase == "complete"

    def test_vague_flags_expose_detection_info(self):
        """_vague_flags tracks which phases had vague answers."""
        answers = [
            "good",                                                    # vague
            "Optimize NLP pipeline accuracy and speed",                # clarified
            "BLEU score, inference time",
            "No GPU access",
            "Try distillation and pruning techniques",
            "eval/test.json with BLEU",
            "100",
            "yes",
        ]
        llm_responses = [
            "What do you mean by 'good'? What specific outcome?",
            "# NLP Pipeline Context",
        ]
        _, orch = _run_interview(answers, llm_responses)
        assert "goal" in orch._vague_flags
        assert orch._vague_flags["goal"] >= 1
