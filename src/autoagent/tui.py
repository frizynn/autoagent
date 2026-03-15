"""autoagent TUI — live dashboard for the optimization loop.

Uses Textual to render a real-time view of the optimization process.
The loop runs in a thread worker; events flow through a thread-safe queue
to update the UI without blocking.

Can also attach to an already-running headless process by reading state.json
and archive entries (watch mode).
"""

from __future__ import annotations

import queue
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Label,
    ProgressBar,
    RichLog,
    Static,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# ---------------------------------------------------------------------------
# Sparkline widget (minimal — no external deps)
# ---------------------------------------------------------------------------

_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(values: list[float], width: int = 30) -> str:
    """Render a sparkline string from numeric values."""
    if not values:
        return ""
    mn, mx = min(values), max(values)
    rng = mx - mn if mx != mn else 1.0
    # Take the last `width` values
    tail = values[-width:]
    return "".join(
        _SPARK_CHARS[min(int((v - mn) / rng * (len(_SPARK_CHARS) - 1)), len(_SPARK_CHARS) - 1)]
        for v in tail
    )


# ---------------------------------------------------------------------------
# Metric card widget
# ---------------------------------------------------------------------------


class MetricCard(Static):
    """A small card showing a label + value."""

    def __init__(self, label: str, value: str = "—", id: str | None = None) -> None:
        super().__init__(id=id)
        self._label = label
        self._value = value

    def compose(self) -> ComposeResult:
        yield Label(self._label, classes="metric-label")
        yield Label(self._value, id=f"{self.id}-value" if self.id else None, classes="metric-value")

    def update_value(self, value: str) -> None:
        self._value = value
        value_widget = self.query_one(".metric-value", Label)
        value_widget.update(value)


# ---------------------------------------------------------------------------
# Main TUI App
# ---------------------------------------------------------------------------


class AutoagentApp(App[int]):
    """Textual TUI for autoagent optimization loop.

    Two modes:
    - **run mode**: Executes the optimization loop in a thread worker.
    - **watch mode**: Attaches to an existing run by polling state.json.
    """

    CSS = """
    Screen {
        layout: vertical;
    }

    #top-bar {
        height: 3;
        layout: horizontal;
        padding: 0 1;
    }

    #top-bar MetricCard {
        width: 1fr;
        height: 3;
        content-align: center middle;
        border: round $surface-lighten-2;
    }

    .metric-label {
        color: $text-muted;
        text-style: dim;
    }

    .metric-value {
        color: $text;
        text-style: bold;
    }

    #main-area {
        height: 1fr;
        layout: horizontal;
    }

    #score-panel {
        width: 40;
        height: 100%;
        border: round $surface-lighten-2;
        padding: 1;
    }

    #score-panel Label {
        width: 100%;
    }

    #log-panel {
        width: 1fr;
        height: 100%;
        border: round $surface-lighten-2;
    }

    #log-panel RichLog {
        height: 1fr;
    }

    #status-bar {
        height: 1;
        dock: bottom;
        padding: 0 1;
        background: $boost;
        color: $text;
    }

    #progress-section {
        height: auto;
        padding: 0 1;
    }

    DataTable {
        height: auto;
        max-height: 16;
    }
    """

    BINDINGS = [  # noqa: RUF012
        Binding("q", "quit_app", "Quit", show=True),
        Binding("p", "pause", "Pause", show=True),
        Binding("r", "resume", "Resume", show=True),
    ]

    TITLE = "autoagent"
    SUB_TITLE = "optimization loop"

    # Reactive state
    iteration: reactive[int] = reactive(0)
    best_score: reactive[float | None] = reactive(None)
    total_cost: reactive[float] = reactive(0.0)
    phase: reactive[str] = reactive("initialized")
    best_iteration_id: reactive[str] = reactive("—")

    def __init__(
        self,
        loop_factory: Callable[..., Any] | None = None,
        watch_dir: Path | None = None,
        budget_usd: float | None = None,
        max_iterations: int | None = None,
    ) -> None:
        super().__init__()
        self._loop_factory = loop_factory
        self._watch_dir = watch_dir
        self._budget_usd = budget_usd
        self._max_iterations = max_iterations
        self._event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._scores: list[float] = []
        self._decisions: list[str] = []
        self._paused = False
        self._loop_done = False

    def compose(self) -> ComposeResult:
        yield Header()

        # Top metric cards
        with Horizontal(id="top-bar"):
            yield MetricCard("ITERATION", "0", id="mc-iteration")
            yield MetricCard("BEST SCORE", "—", id="mc-best-score")
            yield MetricCard("COST", "$0.0000", id="mc-cost")
            yield MetricCard("PHASE", "initialized", id="mc-phase")
            yield MetricCard("BEST #", "—", id="mc-best-id")

        # Progress bar (only if max_iterations known)
        if self._max_iterations:
            with Vertical(id="progress-section"):
                yield ProgressBar(total=self._max_iterations, id="progress")

        # Main content area
        with Horizontal(id="main-area"):
            # Left: score chart + recent table
            with Vertical(id="score-panel"):
                yield Label("📈 Score History", id="score-title")
                yield Label("", id="sparkline")
                yield Label("", id="score-stats")
                yield DataTable(id="recent-table")

            # Right: event log
            with Vertical(id="log-panel"):
                yield Label("📋 Event Log")
                yield RichLog(id="event-log", highlight=True, markup=True)

        yield Footer()

    def on_mount(self) -> None:
        """Set up the table and start the loop or watcher."""
        table = self.query_one("#recent-table", DataTable)
        table.add_columns("Iter", "Score", "Decision", "Mutation", "Cost")

        # Start polling the event queue
        self.set_interval(0.15, self._poll_events)

        if self._loop_factory is not None:
            self._run_loop()
        elif self._watch_dir is not None:
            self.set_interval(2.0, self._poll_state_file)

    # -- Loop execution in thread worker -----------------------------------

    @work(thread=True)
    def _run_loop(self) -> None:
        """Run the optimization loop in a background thread."""

        def event_callback(event: dict[str, Any]) -> None:
            self._event_queue.put(event)

        try:
            # The factory builds and runs the loop, returning final state
            final_state = self._loop_factory(event_callback=event_callback)
            self._event_queue.put({
                "event": "loop_done",
                "phase": final_state.phase if final_state else "unknown",
            })
        except Exception as exc:
            self._event_queue.put({
                "event": "error",
                "message": str(exc),
                "timestamp": datetime.now(UTC).isoformat(),
            })

    # -- Event polling (runs on UI thread) ---------------------------------

    def _poll_events(self) -> None:
        """Drain the event queue and update the UI."""
        drained = 0
        while drained < 50:  # batch up to 50 events per tick
            try:
                event = self._event_queue.get_nowait()
            except queue.Empty:
                break
            drained += 1
            self._handle_event(event)

    def _handle_event(self, event: dict[str, Any]) -> None:
        """Process a single event dict and update UI."""
        ev_type = event.get("event", "")
        log = self.query_one("#event-log", RichLog)
        ts = event.get("timestamp", "")
        ts_short = ts[11:19] if len(ts) >= 19 else ts

        if ev_type == "loop_start":
            self.phase = "running"
            goal = event.get("goal", "")
            budget = event.get("budget_usd")
            self.SUB_TITLE = goal[:60] if goal else "optimization loop"
            self.sub_title = self.SUB_TITLE
            budget_str = f"${budget:.2f}" if budget else "unlimited"
            log.write(f"[bold green]▶ Loop started[/] — budget: {budget_str}")
            self._update_cards()

        elif ev_type == "iteration_start":
            it = event.get("iteration", 0)
            self.iteration = it
            log.write(f"[dim]{ts_short}[/] ⏳ Iteration {it} started…")
            self._update_cards()
            if self._max_iterations:
                self.query_one("#progress", ProgressBar).update(progress=it - 1)

        elif ev_type == "iteration_end":
            it = event.get("iteration", 0)
            score = event.get("score", 0.0)
            decision = event.get("decision", "?")
            cost = event.get("cost_usd", 0.0)
            mutation = event.get("mutation_type", "?")
            rationale = event.get("rationale", "")
            best_id = event.get("best_iteration_id", "—")
            elapsed = event.get("elapsed_ms", 0)

            self.iteration = it
            self.total_cost = cost
            self.best_iteration_id = best_id or "—"
            self._scores.append(score)
            self._decisions.append(decision)

            if self.best_score is None or (decision == "keep" and score > (self.best_score or 0)):
                self.best_score = score

            # Color-code decision
            dec_styled = (
                "[bold green]✓ keep[/]" if decision == "keep"
                else "[dim red]✗ discard[/]"
            )

            log.write(
                f"[dim]{ts_short}[/] Iter {it}: "
                f"score={score:.4f} {dec_styled} "
                f"[dim]({mutation}, {elapsed:.0f}ms)[/]"
            )
            if rationale:
                short_rationale = rationale[:100] + ("…" if len(rationale) > 100 else "")
                log.write(f"  [dim italic]{short_rationale}[/]")

            # Update table
            table = self.query_one("#recent-table", DataTable)
            dec_plain = "✓ keep" if decision == "keep" else "✗ discard"
            table.add_row(
                str(it),
                f"{score:.4f}",
                dec_plain,
                mutation or "?",
                f"${cost:.4f}",
            )

            # Update sparkline and stats
            self._update_sparkline()
            self._update_cards()

            if self._max_iterations:
                self.query_one("#progress", ProgressBar).update(progress=it)

        elif ev_type == "loop_end":
            p = event.get("phase", "completed")
            self.phase = p
            total_it = event.get("total_iterations", 0)
            total_cost = event.get("total_cost_usd", 0.0)
            best_id = event.get("best_iteration_id", "—")
            log.write(
                f"\n[bold green]✅ Loop finished[/] — {p}, "
                f"{total_it} iterations, ${total_cost:.4f}"
            )
            self._loop_done = True
            self._update_cards()

        elif ev_type == "loop_done":
            p = event.get("phase", "done")
            self.phase = p
            self._loop_done = True
            self._update_cards()
            log.write(f"[bold]Loop complete. Phase: {p}[/]")

        elif ev_type == "error":
            msg = event.get("message", "unknown error")
            log.write(f"[bold red]❌ Error:[/] {msg}")
            self.phase = "error"
            self._loop_done = True
            self._update_cards()

        else:
            # Unknown event — just log it
            log.write(f"[dim]{ts_short}[/] {ev_type}: {event}")

    def _update_cards(self) -> None:
        """Refresh metric card values."""
        self.query_one("#mc-iteration", MetricCard).update_value(str(self.iteration))
        score_str = f"{self.best_score:.4f}" if self.best_score is not None else "—"
        self.query_one("#mc-best-score", MetricCard).update_value(score_str)
        self.query_one("#mc-cost", MetricCard).update_value(f"${self.total_cost:.4f}")
        self.query_one("#mc-phase", MetricCard).update_value(self.phase)
        self.query_one("#mc-best-id", MetricCard).update_value(str(self.best_iteration_id))

    def _update_sparkline(self) -> None:
        """Redraw the sparkline and score stats."""
        spark = _sparkline(self._scores, width=35)
        self.query_one("#sparkline", Label).update(spark)

        if self._scores:
            latest = self._scores[-1]
            best = max(self._scores)
            worst = min(self._scores)
            avg = sum(self._scores) / len(self._scores)
            n_keep = self._decisions.count("keep")
            n_disc = self._decisions.count("discard")
            stats = (
                f"Latest: {latest:.4f}  Best: {best:.4f}  "
                f"Avg: {avg:.4f}  Worst: {worst:.4f}\n"
                f"Keep: {n_keep}  Discard: {n_disc}  "
                f"Keep rate: {n_keep / len(self._decisions) * 100:.0f}%"
            )
            self.query_one("#score-stats", Label).update(stats)

    # -- Watch mode: poll state.json ---------------------------------------

    def _poll_state_file(self) -> None:
        """In watch mode, read state.json and update the UI."""
        if self._watch_dir is None:
            return

        from autoagent.archive import Archive
        from autoagent.state import StateManager

        sm = StateManager(self._watch_dir)
        if not sm.is_initialized():
            return

        try:
            state = sm.read_state()
        except Exception:
            return

        self.iteration = state.current_iteration
        self.total_cost = state.total_cost_usd
        self.phase = state.phase
        self.best_iteration_id = state.best_iteration_id or "—"

        # Read best score from archive
        try:
            archive = Archive(sm.archive_dir)
            best = archive.best("primary_score")
            if best:
                score = best.evaluation_result.get("primary_score", 0.0)
                self.best_score = float(score)
        except Exception:
            pass

        self._update_cards()

    # -- Actions -----------------------------------------------------------

    def action_quit_app(self) -> None:
        """Quit the TUI. If the loop is running, it will stop."""
        self.exit(0)

    def action_pause(self) -> None:
        """Signal the loop to pause (future: wire into loop's budget mechanism)."""
        log = self.query_one("#event-log", RichLog)
        log.write("[yellow]⏸ Pause requested — loop will stop after current iteration.[/]")
        self._paused = True
        # TODO: Wire a pause signal into the optimization loop

    def action_resume(self) -> None:
        """Resume a paused loop (future)."""
        log = self.query_one("#event-log", RichLog)
        log.write("[green]▶ Resume requested.[/]")
        self._paused = False


# ---------------------------------------------------------------------------
# Public entry point for the TUI
# ---------------------------------------------------------------------------


def run_tui(
    loop_factory: Callable[..., Any] | None = None,
    watch_dir: Path | None = None,
    budget_usd: float | None = None,
    max_iterations: int | None = None,
) -> int:
    """Launch the autoagent TUI.

    Parameters
    ----------
    loop_factory:
        Callable that accepts ``event_callback=...`` and runs the loop,
        returning the final ``ProjectState``. Used in run mode.
    watch_dir:
        Project directory to watch in watch mode. Polls state.json.
    budget_usd:
        Budget ceiling (for display purposes).
    max_iterations:
        Max iterations (for progress bar).

    Returns
    -------
    int
        Exit code (0 = success).
    """
    app = AutoagentApp(
        loop_factory=loop_factory,
        watch_dir=watch_dir,
        budget_usd=budget_usd,
        max_iterations=max_iterations,
    )
    result = app.run()
    return result if isinstance(result, int) else 0
