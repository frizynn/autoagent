"""autoagent TUI — interactive terminal dashboard.

Standalone Textual app that provides the full autoagent experience:
- Project status at a glance
- Start/stop optimization runs (via subprocess for crash isolation)
- Live JSONL event streaming from the optimization loop
- Score visualization and iteration history

The loop runs as a child process (`autoagent run --jsonl`), not in-process.
This means a loop crash doesn't crash the TUI (D074).
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import signal
import subprocess
import sys
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Static,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# ---------------------------------------------------------------------------
# Sparkline
# ---------------------------------------------------------------------------

_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(values: list[float], width: int = 30) -> str:
    """Render a sparkline string from numeric values."""
    if not values:
        return ""
    mn, mx = min(values), max(values)
    rng = mx - mn if mx != mn else 1.0
    tail = values[-width:]
    return "".join(
        _SPARK_CHARS[min(int((v - mn) / rng * (len(_SPARK_CHARS) - 1)), len(_SPARK_CHARS) - 1)]
        for v in tail
    )


# ---------------------------------------------------------------------------
# Subprocess runner — manages the `autoagent run --jsonl` child process
# ---------------------------------------------------------------------------

_SIGKILL_TIMEOUT = 5.0  # seconds after SIGTERM before SIGKILL


class LoopSubprocess:
    """Manages the optimization loop as a child process.

    Spawns ``autoagent run --jsonl``, reads JSONL from stdout line-by-line
    in a reader thread, and puts parsed events into a queue for the TUI.

    Lifecycle: start() → running → stop()/crash → done
    """

    def __init__(self, project_dir: str, event_queue: queue.Queue[dict[str, Any]]) -> None:
        self._project_dir = project_dir
        self._queue = event_queue
        self._proc: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._pid: int | None = None
        self._stderr_lines: list[str] = []

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def pid(self) -> int | None:
        return self._pid

    def start(self, extra_args: list[str] | None = None) -> None:
        """Spawn the subprocess."""
        if self.running:
            return

        args = [sys.executable, "-m", "autoagent.cli", "--project-dir", self._project_dir, "run", "--jsonl"]
        if extra_args:
            args.extend(extra_args)

        env = {**os.environ, "PYTHONUNBUFFERED": "1"}

        self._stderr_lines = []
        self._proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=self._project_dir,
        )
        self._pid = self._proc.pid

        # Reader thread: parse JSONL from stdout
        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader_thread.start()

        # Stderr reader thread
        stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        stderr_thread.start()

    def stop(self) -> None:
        """Send SIGTERM, then SIGKILL after timeout."""
        if not self._proc or not self.running:
            return

        self._proc.send_signal(signal.SIGTERM)

        def _force_kill() -> None:
            if self._proc and self._proc.poll() is None:
                self._proc.kill()

        timer = threading.Timer(_SIGKILL_TIMEOUT, _force_kill)
        timer.daemon = True
        timer.start()

    def _read_stdout(self) -> None:
        """Read JSONL lines from subprocess stdout (runs in thread)."""
        assert self._proc and self._proc.stdout
        try:
            for line in self._proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    self._queue.put(event)
                except json.JSONDecodeError:
                    pass  # non-JSON line, skip
        except (OSError, ValueError):
            pass  # pipe closed

        # Process exited — emit a synthetic event
        exit_code = self._proc.wait() if self._proc else None
        if exit_code == 0:
            self._queue.put({"event": "_subprocess_exit", "code": 0})
        else:
            stderr_tail = "\n".join(self._stderr_lines[-5:]) if self._stderr_lines else ""
            self._queue.put({
                "event": "_subprocess_exit",
                "code": exit_code,
                "stderr": stderr_tail,
            })

    def _read_stderr(self) -> None:
        """Capture stderr lines (runs in thread)."""
        assert self._proc and self._proc.stderr
        try:
            for line in self._proc.stderr:
                self._stderr_lines.append(line.rstrip())
                if len(self._stderr_lines) > 50:
                    self._stderr_lines.pop(0)
        except (OSError, ValueError):
            pass


# ---------------------------------------------------------------------------
# Interview subprocess — drives `autoagent new --json`
# ---------------------------------------------------------------------------


class InterviewSubprocess:
    """Manages the interview as a child process using the JSON protocol.

    Spawns ``autoagent new --json``, reads JSON messages from stdout,
    and writes JSON answers to stdin. Messages are put into a queue
    for the TUI to render.

    Protocol (Python → TUI):
      prompt   { type: "prompt", phase: str, question: str }
      confirm  { type: "confirm", summary: str }
      status   { type: "status", message: str }
      complete { type: "complete", config: dict, context: str }
      error    { type: "error", message: str }

    Responses (TUI → Python):
      answer   { type: "answer", text: str }
      abort    { type: "abort" }
    """

    def __init__(self, project_dir: str, msg_queue: queue.Queue[dict[str, Any]]) -> None:
        self._project_dir = project_dir
        self._queue = msg_queue
        self._proc: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        """Spawn the interview subprocess."""
        if self.running:
            return

        args = [
            sys.executable, "-m", "autoagent.cli",
            "--project-dir", self._project_dir,
            "new", "--json",
        ]
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}

        self._proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=self._project_dir,
        )

        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader_thread.start()

    def send_answer(self, text: str) -> None:
        """Send an answer back to the interview subprocess."""
        if self._proc and self._proc.stdin and not self._proc.stdin.closed:
            msg = json.dumps({"type": "answer", "text": text})
            self._proc.stdin.write(msg + "\n")
            self._proc.stdin.flush()

    def abort(self) -> None:
        """Send abort and kill the subprocess."""
        if self._proc and self._proc.stdin and not self._proc.stdin.closed:
            msg = json.dumps({"type": "abort"})
            try:
                self._proc.stdin.write(msg + "\n")
                self._proc.stdin.flush()
            except (OSError, BrokenPipeError):
                pass
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def _read_stdout(self) -> None:
        """Read JSON messages from stdout (runs in thread)."""
        assert self._proc and self._proc.stdout
        try:
            for line in self._proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    self._queue.put(msg)
                except json.JSONDecodeError:
                    pass
        except (OSError, ValueError):
            pass

        # Subprocess exited
        code = self._proc.wait() if self._proc else None
        if code != 0:
            self._queue.put({"type": "error", "message": f"Interview process exited with code {code}"})


# ---------------------------------------------------------------------------
# Metric card widget
# ---------------------------------------------------------------------------


class MetricCard(Static):
    """A small card showing a label + value."""

    def __init__(self, label: str, value: str = "—", *, id: str | None = None) -> None:
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
    """Interactive autoagent TUI.

    Opens on ``autoagent`` with no args. Shows project status, lets user
    start/stop optimization runs, and streams live iteration events.
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

    #progress-section {
        height: auto;
        padding: 0 1;
    }

    DataTable {
        height: auto;
        max-height: 16;
    }

    #interview-bar {
        height: auto;
        max-height: 5;
        padding: 0 1;
        display: none;
    }

    #interview-bar.visible {
        display: block;
    }

    #interview-question {
        color: $text;
        text-style: bold;
        padding: 0 1;
    }

    #interview-input {
        margin: 0 1;
    }
    """

    BINDINGS = [  # noqa: RUF012
        Binding("q", "quit_app", "Quit", show=True, priority=True),
        Binding("r", "start_run", "Run", show=True),
        Binding("s", "stop_run", "Stop", show=True),
        Binding("n", "start_interview", "New", show=True),
        Binding("v", "view_report", "Report", show=True),
        Binding("i", "init_project", "Init", show=True),
        Binding("escape", "cancel_interview", "Cancel", show=False),
    ]

    TITLE = "autoagent"
    SUB_TITLE = "autonomous optimization"

    # Reactive state
    iteration: reactive[int] = reactive(0)
    best_score: reactive[float | None] = reactive(None)
    total_cost: reactive[float] = reactive(0.0)
    phase: reactive[str] = reactive("idle")
    best_iteration_id: reactive[str] = reactive("—")

    def __init__(
        self,
        project_dir: str | None = None,
        max_iterations: int | None = None,
        budget_usd: float | None = None,
        *,
        # Legacy/test support: direct loop factory (runs in-process)
        loop_factory: Callable[..., Any] | None = None,
        watch_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self._project_dir = project_dir or os.getcwd()
        self._max_iterations = max_iterations
        self._budget_usd = budget_usd
        self._loop_factory = loop_factory
        self._watch_dir = watch_dir
        self._event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._scores: list[float] = []
        self._decisions: list[str] = []
        self._loop_done = False
        self._subprocess: LoopSubprocess | None = None
        self._project_initialized = False
        # Interview state
        self._interview_proc: InterviewSubprocess | None = None
        self._interview_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._interviewing = False

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="top-bar"):
            yield MetricCard("ITERATION", "0", id="mc-iteration")
            yield MetricCard("BEST SCORE", "—", id="mc-best-score")
            yield MetricCard("COST", "$0.0000", id="mc-cost")
            yield MetricCard("PHASE", "idle", id="mc-phase")
            yield MetricCard("BEST #", "—", id="mc-best-id")

        if self._max_iterations:
            with Vertical(id="progress-section"):
                yield ProgressBar(total=self._max_iterations, id="progress")

        with Horizontal(id="main-area"):
            with Vertical(id="score-panel"):
                yield Label("📈 Score History", id="score-title")
                yield Label("", id="sparkline")
                yield Label("", id="score-stats")
                yield DataTable(id="recent-table")

            with Vertical(id="log-panel"):
                yield Label("📋 Event Log")
                yield RichLog(id="event-log", highlight=True, markup=True)

        # Interview input bar (hidden by default)
        with Vertical(id="interview-bar"):
            yield Label("", id="interview-question")
            yield Input(placeholder="Type your answer and press Enter…", id="interview-input")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize: load project state, set up polling."""
        table = self.query_one("#recent-table", DataTable)
        table.add_columns("Iter", "Score", "Decision", "Mutation", "Cost")

        # Poll event queue (for subprocess events)
        self.set_interval(0.15, self._poll_events)
        self.set_interval(0.15, self._poll_interview)

        log = self.query_one("#event-log", RichLog)

        # Load initial project state from disk
        self._load_project_state()

        if self._project_initialized:
            log.write(
                "[dim]Project loaded. Keybinds: "
                "[bold]r[/]=Run  [bold]s[/]=Stop  [bold]n[/]=New  "
                "[bold]v[/]=Report  [bold]q[/]=Quit[/]"
            )
            # If watch mode, also poll state.json periodically
            if self._watch_dir is not None:
                self.set_interval(2.0, self._poll_state_file)
        else:
            log.write(
                "[yellow]No autoagent project found.[/]\n"
                "[dim]Press [bold]i[/bold] to initialize, or [bold]q[/bold] to quit.[/]"
            )
            self.phase = "no project"
            self._update_cards()

        # Legacy: if loop_factory provided, run it in-process (for tests)
        if self._loop_factory is not None:
            self._run_loop_factory()

    def _load_project_state(self) -> None:
        """Read current project state from .autoagent/ on disk."""
        from autoagent.state import StateManager

        sm = StateManager(self._project_dir)
        if not sm.is_initialized():
            self._project_initialized = False
            return

        self._project_initialized = True

        try:
            state = sm.read_state()
            config = sm.read_config()
        except Exception:
            return

        self.iteration = state.current_iteration
        self.total_cost = state.total_cost_usd
        self.phase = state.phase
        self.best_iteration_id = state.best_iteration_id or "—"

        if config.goal:
            self.sub_title = config.goal[:60]

        # Load best score from archive
        try:
            from autoagent.archive import Archive
            archive = Archive(sm.archive_dir)
            best = archive.best("primary_score")
            if best:
                self.best_score = float(best.evaluation_result.get("primary_score", 0.0))
        except Exception:
            pass

        self._update_cards()

    # -- Subprocess management ---------------------------------------------

    def _start_subprocess(self) -> None:
        """Spawn the optimization loop as a subprocess."""
        if self._subprocess and self._subprocess.running:
            self.query_one("#event-log", RichLog).write(
                "[yellow]Loop already running. Press [bold]s[/bold] to stop first.[/]"
            )
            return

        if not self._project_initialized:
            self.query_one("#event-log", RichLog).write(
                "[yellow]No project initialized. Run [bold]autoagent init[/bold] first.[/]"
            )
            return

        extra_args: list[str] = []
        if self._max_iterations:
            extra_args.extend(["--max-iterations", str(self._max_iterations)])
        if self._budget_usd:
            extra_args.extend(["--budget", str(self._budget_usd)])

        self._subprocess = LoopSubprocess(self._project_dir, self._event_queue)
        self._subprocess.start(extra_args or None)
        self._loop_done = False
        self.phase = "starting"
        self._update_cards()

        log = self.query_one("#event-log", RichLog)
        pid = self._subprocess.pid
        log.write(f"[bold green]▶ Subprocess started[/] (PID {pid})")

    def _stop_subprocess(self) -> None:
        """Send SIGTERM to the running subprocess."""
        if not self._subprocess or not self._subprocess.running:
            self.query_one("#event-log", RichLog).write("[dim]No loop running.[/]")
            return

        self._subprocess.stop()
        self.query_one("#event-log", RichLog).write("[yellow]⏹ Stop signal sent.[/]")

    # -- Legacy in-process loop (for tests) --------------------------------

    def _run_loop_factory(self) -> None:
        """Run a loop_factory in a thread (test/legacy support)."""
        from textual import work

        @work(thread=True)
        def _worker(self_ref: AutoagentApp) -> None:
            def event_callback(event: dict[str, Any]) -> None:
                self_ref._event_queue.put(event)
            try:
                final_state = self_ref._loop_factory(event_callback=event_callback)
                self_ref._event_queue.put({
                    "event": "loop_done",
                    "phase": final_state.phase if final_state else "unknown",
                })
            except Exception as exc:
                self_ref._event_queue.put({
                    "event": "error",
                    "message": str(exc),
                    "timestamp": datetime.now(UTC).isoformat(),
                })

        _worker(self)

    # -- Event polling -----------------------------------------------------

    def _poll_events(self) -> None:
        """Drain the event queue and update the UI."""
        drained = 0
        while drained < 50:
            try:
                event = self._event_queue.get_nowait()
            except queue.Empty:
                break
            drained += 1
            self._handle_event(event)

    def _handle_event(self, event: dict[str, Any]) -> None:
        """Process a single event and update the UI."""
        ev_type = event.get("event", "")
        log = self.query_one("#event-log", RichLog)
        ts = event.get("timestamp", "")
        ts_short = ts[11:19] if len(ts) >= 19 else ts

        if ev_type == "loop_start":
            self.phase = "running"
            goal = event.get("goal", "")
            budget = event.get("budget_usd")
            if goal:
                self.sub_title = goal[:60]
            budget_str = f"${budget:.2f}" if budget else "unlimited"
            log.write(f"[bold green]▶ Loop started[/] — budget: {budget_str}")
            self._update_cards()

        elif ev_type == "iteration_start":
            it = event.get("iteration", 0)
            self.iteration = it
            log.write(f"[dim]{ts_short}[/] ⏳ Iteration {it}…")
            self._update_cards()
            if self._max_iterations:
                with contextlib.suppress(Exception):
                    self.query_one("#progress", ProgressBar).update(progress=it - 1)

        elif ev_type == "iteration_end":
            self._handle_iteration_end(event, log, ts_short)

        elif ev_type == "loop_end":
            p = event.get("phase", "completed")
            self.phase = p
            total_it = event.get("total_iterations", 0)
            total_cost = event.get("total_cost_usd", 0.0)
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

        elif ev_type == "_subprocess_exit":
            code = event.get("code")
            if code == 0:
                if not self._loop_done:
                    self.phase = "completed"
                    self._loop_done = True
                    self._update_cards()
            else:
                stderr = event.get("stderr", "")
                log.write(f"[bold red]💀 Subprocess exited with code {code}[/]")
                if stderr:
                    for line in stderr.split("\n")[-3:]:
                        if line.strip():
                            log.write(f"  [dim red]{line.strip()}[/]")
                self.phase = "crashed"
                self._loop_done = True
                self._update_cards()
                log.write("[dim]Press [bold]r[/bold] to try again.[/]")

        else:
            log.write(f"[dim]{ts_short}[/] {ev_type}: {event}")

    def _handle_iteration_end(self, event: dict[str, Any], log: RichLog, ts_short: str) -> None:
        """Process an iteration_end event."""
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
            short = rationale[:100] + ("…" if len(rationale) > 100 else "")
            log.write(f"  [dim italic]{short}[/]")

        table = self.query_one("#recent-table", DataTable)
        dec_plain = "✓ keep" if decision == "keep" else "✗ discard"
        table.add_row(str(it), f"{score:.4f}", dec_plain, mutation or "?", f"${cost:.4f}")

        self._update_sparkline()
        self._update_cards()

        if self._max_iterations:
            with contextlib.suppress(Exception):
                self.query_one("#progress", ProgressBar).update(progress=it)

    def _update_cards(self) -> None:
        """Refresh metric card values."""
        self.query_one("#mc-iteration", MetricCard).update_value(str(self.iteration))
        score_str = f"{self.best_score:.4f}" if self.best_score is not None else "—"
        self.query_one("#mc-best-score", MetricCard).update_value(score_str)
        self.query_one("#mc-cost", MetricCard).update_value(f"${self.total_cost:.4f}")
        self.query_one("#mc-phase", MetricCard).update_value(self.phase)
        self.query_one("#mc-best-id", MetricCard).update_value(str(self.best_iteration_id))

    def _update_sparkline(self) -> None:
        """Redraw sparkline and score stats."""
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

    # -- Watch mode --------------------------------------------------------

    def _poll_state_file(self) -> None:
        """Poll state.json for watch mode."""
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

        try:
            archive = Archive(sm.archive_dir)
            best = archive.best("primary_score")
            if best:
                self.best_score = float(best.evaluation_result.get("primary_score", 0.0))
        except Exception:
            pass

        self._update_cards()

    # -- Actions (keybinds) ------------------------------------------------

    def action_quit_app(self) -> None:
        """Quit. Stops subprocess if running."""
        if self._subprocess and self._subprocess.running:
            self._subprocess.stop()
        if self._interview_proc and self._interview_proc.running:
            self._interview_proc.abort()
        self.exit(0)

    def action_start_run(self) -> None:
        """Start an optimization run."""
        self._start_subprocess()

    def action_stop_run(self) -> None:
        """Stop the running optimization."""
        self._stop_subprocess()

    def action_start_interview(self) -> None:
        """Start the project interview."""
        self._start_interview()

    def action_cancel_interview(self) -> None:
        """Cancel the interview if running."""
        if not self._interviewing:
            return
        if self._interview_proc:
            self._interview_proc.abort()
        self._interviewing = False
        self._hide_interview_input()
        self.query_one("#event-log", RichLog).write("[yellow]Interview cancelled.[/]")

    def action_view_report(self) -> None:
        """Generate and display the optimization report in the log."""
        log = self.query_one("#event-log", RichLog)

        if not self._project_initialized:
            log.write("[yellow]No project to report on.[/]")
            return

        from autoagent.archive import Archive
        from autoagent.report import generate_report
        from autoagent.state import StateManager

        sm = StateManager(self._project_dir)
        try:
            state = sm.read_state()
            config = sm.read_config()
            archive = Archive(sm.archive_dir)
            entries = archive.query()
        except Exception as exc:
            log.write(f"[bold red]❌ Could not read project data:[/] {exc}")
            return

        result = generate_report(entries, state, config)

        log.write("\n[bold cyan]═══ Optimization Report ═══[/]\n")
        for line in result.markdown.split("\n"):
            log.write(line)
        log.write(f"\n[dim]{result.summary}[/]\n")

    def action_init_project(self) -> None:
        """Initialize a new autoagent project in the current directory."""
        log = self.query_one("#event-log", RichLog)

        if self._project_initialized:
            log.write("[dim]Project already initialized.[/]")
            return

        from autoagent.state import StateManager

        sm = StateManager(self._project_dir)
        try:
            sm.init_project()
            log.write(f"[bold green]✅ Initialized project at {sm.aa_dir}[/]")
            self._load_project_state()
        except FileExistsError:
            log.write("[yellow]Project already exists.[/]")
        except OSError as exc:
            log.write(f"[bold red]❌ Init failed:[/] {exc}")

    # -- Interview ---------------------------------------------------------

    def _start_interview(self) -> None:
        """Launch the interview subprocess and show the input bar."""
        if self._interviewing:
            self.query_one("#event-log", RichLog).write("[dim]Interview already in progress.[/]")
            return

        if self._subprocess and self._subprocess.running:
            self.query_one("#event-log", RichLog).write(
                "[yellow]Cannot start interview while optimization is running.[/]"
            )
            return

        log = self.query_one("#event-log", RichLog)
        log.write("[bold cyan]📝 Starting project interview…[/]")

        self._interview_proc = InterviewSubprocess(self._project_dir, self._interview_queue)
        self._interview_proc.start()
        self._interviewing = True

    def _show_interview_input(self, question: str) -> None:
        """Show the interview bar with a question."""
        bar = self.query_one("#interview-bar")
        bar.add_class("visible")
        self.query_one("#interview-question", Label).update(question)
        inp = self.query_one("#interview-input", Input)
        inp.value = ""
        inp.focus()

    def _hide_interview_input(self) -> None:
        """Hide the interview bar."""
        bar = self.query_one("#interview-bar")
        bar.remove_class("visible")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter press in the interview input."""
        if not self._interviewing or not self._interview_proc:
            return

        if event.input.id != "interview-input":
            return

        answer = event.value.strip()
        event.input.value = ""

        log = self.query_one("#event-log", RichLog)
        log.write(f"  [dim]> {answer}[/]")

        self._interview_proc.send_answer(answer)
        self._hide_interview_input()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Suppress keybind actions while typing in the input."""
        # Textual handles this via focus — Input captures keys when focused

    def _poll_interview(self) -> None:
        """Drain the interview message queue."""
        if not self._interviewing:
            return

        drained = 0
        while drained < 10:
            try:
                msg = self._interview_queue.get_nowait()
            except queue.Empty:
                break
            drained += 1
            self._handle_interview_msg(msg)

    def _handle_interview_msg(self, msg: dict[str, Any]) -> None:
        """Process a single interview protocol message."""
        msg_type = msg.get("type", "")
        log = self.query_one("#event-log", RichLog)

        if msg_type == "prompt":
            phase = msg.get("phase", "")
            question = msg.get("question", "")
            log.write(f"[cyan]  [{phase}][/] {question}")
            self._show_interview_input(question)

        elif msg_type == "confirm":
            summary = msg.get("summary", "")
            log.write("\n[bold cyan]--- Summary ---[/]")
            for line in summary.split("\n"):
                if line.strip():
                    log.write(f"  {line}")
            self._show_interview_input("Does this look correct? (yes/no)")

        elif msg_type == "status":
            message = msg.get("message", "")
            if message:
                log.write(f"[dim]{message}[/]")

        elif msg_type == "complete":
            log.write("[bold green]✅ Interview complete! Project configured.[/]")
            self._interviewing = False
            self._hide_interview_input()
            # Reload project state
            self._load_project_state()

        elif msg_type == "error":
            error = msg.get("message", "unknown error")
            log.write(f"[bold red]❌ Interview error:[/] {error}")
            self._interviewing = False
            self._hide_interview_input()

        else:
            log.write(f"[dim]interview: {msg}[/]")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_tui(
    project_dir: str | None = None,
    max_iterations: int | None = None,
    budget_usd: float | None = None,
    *,
    loop_factory: Callable[..., Any] | None = None,
    watch_dir: Path | None = None,
) -> int:
    """Launch the autoagent TUI.

    Parameters
    ----------
    project_dir:
        Project root directory. Defaults to cwd.
    max_iterations:
        Max iterations (shows progress bar).
    budget_usd:
        Budget ceiling (display only).
    loop_factory:
        Legacy/test: callable that runs the loop in-process.
    watch_dir:
        Watch mode: poll state.json from this directory.

    Returns
    -------
    int
        Exit code (0 = success).
    """
    app = AutoagentApp(
        project_dir=project_dir,
        max_iterations=max_iterations,
        budget_usd=budget_usd,
        loop_factory=loop_factory,
        watch_dir=watch_dir,
    )
    result = app.run()
    return result if isinstance(result, int) else 0
