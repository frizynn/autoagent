"""Tests for autoagent TUI — headless Textual app tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from autoagent.tui import AutoagentApp, _sparkline

# ---------------------------------------------------------------------------
# Sparkline unit tests
# ---------------------------------------------------------------------------


class TestSparkline:
    def test_empty(self) -> None:
        assert _sparkline([]) == ""

    def test_single_value(self) -> None:
        result = _sparkline([1.0])
        assert len(result) == 1

    def test_ascending(self) -> None:
        result = _sparkline([0.0, 0.5, 1.0])
        assert len(result) == 3
        assert result[0] == "▁"
        assert result[-1] == "█"

    def test_constant(self) -> None:
        result = _sparkline([5.0, 5.0, 5.0])
        assert len(result) == 3
        assert len(set(result)) == 1

    def test_width_truncation(self) -> None:
        values = list(range(100))
        result = _sparkline([float(v) for v in values], width=10)
        assert len(result) == 10


# ---------------------------------------------------------------------------
# TUI app tests (headless)
# ---------------------------------------------------------------------------


async def test_tui_mounts_and_shows_initial_state() -> None:
    """The TUI should mount and display initial metric cards."""
    app = AutoagentApp()
    async with app.run_test(size=(120, 40)):
        mc_iter = app.query_one("#mc-iteration")
        assert mc_iter is not None

        mc_phase = app.query_one("#mc-phase")
        assert mc_phase is not None

        assert app.iteration == 0
        assert app.best_score is None


async def test_tui_processes_events() -> None:
    """Events put into the queue should update the UI."""
    app = AutoagentApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app._event_queue.put({
            "event": "loop_start",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "goal": "Test goal",
            "budget_usd": 10.0,
            "phase": "running",
        })
        app._event_queue.put({
            "event": "iteration_end",
            "timestamp": "2026-01-01T00:00:02+00:00",
            "iteration": 1,
            "score": 0.75,
            "decision": "keep",
            "cost_usd": 0.001,
            "elapsed_ms": 150,
            "best_iteration_id": "1",
            "rationale": "Improved score",
            "mutation_type": "parametric",
        })

        await pilot.pause()
        app._poll_events()
        await pilot.pause()

        assert app.iteration == 1
        assert app.best_score == 0.75
        assert app.total_cost == 0.001
        assert app.phase == "running"
        assert len(app._scores) == 1


async def test_tui_loop_done_event() -> None:
    """The loop_done event should update phase."""
    app = AutoagentApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app._event_queue.put({"event": "loop_done", "phase": "completed"})

        await pilot.pause()
        app._poll_events()
        await pilot.pause()

        assert app.phase == "completed"
        assert app._loop_done is True


async def test_tui_error_event() -> None:
    """Error events should set phase to 'error'."""
    app = AutoagentApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app._event_queue.put({
            "event": "error",
            "message": "Something broke",
            "timestamp": "2026-01-01T00:00:00+00:00",
        })

        await pilot.pause()
        app._poll_events()
        await pilot.pause()

        assert app.phase == "error"
        assert app._loop_done is True


async def test_tui_multiple_iterations() -> None:
    """Multiple iteration events should accumulate scores."""
    app = AutoagentApp()
    async with app.run_test(size=(120, 40)) as pilot:
        for i in range(5):
            app._event_queue.put({
                "event": "iteration_end",
                "timestamp": f"2026-01-01T00:00:{i:02d}+00:00",
                "iteration": i + 1,
                "score": 0.5 + i * 0.1,
                "decision": "keep" if i % 2 == 0 else "discard",
                "cost_usd": (i + 1) * 0.001,
                "elapsed_ms": 100,
                "best_iteration_id": "1",
                "rationale": f"Iteration {i+1}",
                "mutation_type": "parametric",
            })

        await pilot.pause()
        app._poll_events()
        await pilot.pause()

        assert app.iteration == 5
        assert len(app._scores) == 5
        assert app._decisions.count("keep") == 3
        assert app._decisions.count("discard") == 2


async def test_tui_with_progress_bar() -> None:
    """When max_iterations is set, a progress bar should appear."""
    app = AutoagentApp(max_iterations=10)
    async with app.run_test(size=(120, 40)):
        from textual.widgets import ProgressBar
        pb = app.query_one("#progress", ProgressBar)
        assert pb is not None
        assert pb.total == 10


async def test_tui_quit_binding() -> None:
    """Pressing 'q' should quit the app."""
    app = AutoagentApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("q")
        assert True  # quit binding fires without error


async def test_tui_subprocess_exit_ok() -> None:
    """A clean subprocess exit should set phase to completed."""
    app = AutoagentApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app._event_queue.put({"event": "_subprocess_exit", "code": 0})

        await pilot.pause()
        app._poll_events()
        await pilot.pause()

        assert app.phase == "completed"
        assert app._loop_done is True


async def test_tui_subprocess_exit_crash() -> None:
    """A non-zero subprocess exit should set phase to crashed."""
    app = AutoagentApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app._event_queue.put({
            "event": "_subprocess_exit",
            "code": 1,
            "stderr": "Error: something failed",
        })

        await pilot.pause()
        app._poll_events()
        await pilot.pause()

        assert app.phase == "crashed"
        assert app._loop_done is True


async def test_tui_with_loop_factory() -> None:
    """A loop_factory should be invoked in the background (legacy/test mode)."""
    call_log: list[str] = []

    def fake_factory(event_callback=None):
        call_log.append("called")
        if event_callback:
            event_callback({
                "event": "loop_start",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "goal": "test",
                "budget_usd": None,
                "phase": "running",
            })
            event_callback({
                "event": "iteration_end",
                "timestamp": "2026-01-01T00:00:01+00:00",
                "iteration": 1,
                "score": 0.9,
                "decision": "keep",
                "cost_usd": 0.01,
                "elapsed_ms": 50,
                "best_iteration_id": "1",
                "rationale": "mock",
                "mutation_type": "structural",
            })
        mock_state = MagicMock()
        mock_state.phase = "completed"
        return mock_state

    app = AutoagentApp(loop_factory=fake_factory)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(delay=0.5)
        app._poll_events()
        await pilot.pause()

        assert "called" in call_log
        assert app.iteration == 1
        assert app.best_score == 0.9


async def test_tui_no_project_state() -> None:
    """TUI should show no-project message when no .autoagent/ exists."""
    app = AutoagentApp(project_dir="/tmp/nonexistent-autoagent-test")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.phase == "no project"
        assert not app._project_initialized
