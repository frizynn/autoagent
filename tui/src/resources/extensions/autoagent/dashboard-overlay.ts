/**
 * AutoAgent Dashboard Overlay
 *
 * Renders a live-updating dashboard showing optimization iteration progress,
 * scores, decisions, cost, and elapsed time. Subscribes to SubprocessManager
 * events for real-time updates.
 *
 * Controls: ↑↓/j/k scroll, g/G top/end, Esc/Ctrl+C/Ctrl+Alt+A close.
 * Closing the overlay does NOT stop the subprocess (D067).
 */

import type { Theme } from "@gsd/pi-coding-agent";
import { truncateToWidth, visibleWidth, matchesKey, Key } from "@gsd/pi-tui";
import { SubprocessManager } from "./subprocess-manager.js";
import { type AutoagentEvent, type IterationEndEvent, SubprocessState } from "./types.js";

function formatDuration(ms: number): string {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rs = s % 60;
  if (m < 60) return `${m}m ${rs}s`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return `${h}h ${rm}m`;
}

function padRight(content: string, width: number): string {
  const vis = visibleWidth(content);
  return content + " ".repeat(Math.max(0, width - vis));
}

function joinColumns(left: string, right: string, width: number): string {
  const leftW = visibleWidth(left);
  const rightW = visibleWidth(right);
  if (leftW + rightW + 2 > width) {
    return truncateToWidth(`${left}  ${right}`, width);
  }
  return left + " ".repeat(width - leftW - rightW) + right;
}

function centerLine(content: string, width: number): string {
  const vis = visibleWidth(content);
  if (vis >= width) return truncateToWidth(content, width);
  const leftPad = Math.floor((width - vis) / 2);
  return " ".repeat(leftPad) + content;
}

function stateBadge(state: SubprocessState, th: Theme): string {
  switch (state) {
    case SubprocessState.Running: return th.fg("success", "● RUNNING");
    case SubprocessState.Completed: return th.fg("accent", "✓ COMPLETED");
    case SubprocessState.Error: return th.fg("error", "✗ ERROR");
    case SubprocessState.Stopped: return th.fg("warning", "■ STOPPED");
    case SubprocessState.Idle: return th.fg("dim", "○ IDLE");
  }
}

export class AutoagentDashboardOverlay {
  private tui: { requestRender: () => void };
  private theme: Theme;
  private onClose: () => void;
  private cachedWidth?: number;
  private cachedLines?: string[];
  private refreshTimer: ReturnType<typeof setInterval>;
  private unsubscribe: () => void;
  private scrollOffset = 0;

  constructor(
    tui: { requestRender: () => void },
    theme: Theme,
    onClose: () => void,
  ) {
    this.tui = tui;
    this.theme = theme;
    this.onClose = onClose;

    // Subscribe to live events for immediate re-render
    this.unsubscribe = SubprocessManager.onEvent(() => {
      this.invalidate();
      this.tui.requestRender();
    });

    // Periodic refresh for elapsed timer updates
    this.refreshTimer = setInterval(() => {
      this.invalidate();
      this.tui.requestRender();
    }, 1000);
  }

  handleInput(data: string): void {
    if (matchesKey(data, Key.escape) || matchesKey(data, Key.ctrl("c")) || matchesKey(data, Key.ctrlAlt("a"))) {
      // Close overlay only — D067: do NOT call SubprocessManager.stop()
      this.dispose();
      this.onClose();
      return;
    }

    if (matchesKey(data, Key.down) || matchesKey(data, "j")) {
      this.scrollOffset++;
      this.invalidate();
      this.tui.requestRender();
      return;
    }

    if (matchesKey(data, Key.up) || matchesKey(data, "k")) {
      this.scrollOffset = Math.max(0, this.scrollOffset - 1);
      this.invalidate();
      this.tui.requestRender();
      return;
    }

    if (data === "g") {
      this.scrollOffset = 0;
      this.invalidate();
      this.tui.requestRender();
      return;
    }

    if (data === "G") {
      this.scrollOffset = 999;
      this.invalidate();
      this.tui.requestRender();
      return;
    }
  }

  render(width: number): string[] {
    if (this.cachedLines && this.cachedWidth === width) {
      return this.cachedLines;
    }

    const content = this.buildContentLines(width);
    const viewportHeight = Math.max(5, process.stdout.rows ? process.stdout.rows - 8 : 24);
    const chromeHeight = 2; // top + bottom border
    const visibleContentRows = Math.max(1, viewportHeight - chromeHeight);
    const maxScroll = Math.max(0, content.length - visibleContentRows);
    this.scrollOffset = Math.min(this.scrollOffset, maxScroll);
    const visibleContent = content.slice(this.scrollOffset, this.scrollOffset + visibleContentRows);

    const lines = this.wrapInBox(visibleContent, width);

    this.cachedWidth = width;
    this.cachedLines = lines;
    return lines;
  }

  private wrapInBox(inner: string[], width: number): string[] {
    const th = this.theme;
    const border = (s: string) => th.fg("borderAccent", s);
    const innerWidth = width - 4;
    const lines: string[] = [];

    lines.push(border("╭" + "─".repeat(width - 2) + "╮"));
    for (const line of inner) {
      const truncated = truncateToWidth(line, innerWidth);
      const padWidth = Math.max(0, innerWidth - visibleWidth(truncated));
      lines.push(border("│") + " " + truncated + " ".repeat(padWidth) + " " + border("│"));
    }
    lines.push(border("╰" + "─".repeat(width - 2) + "╯"));
    return lines;
  }

  private buildContentLines(width: number): string[] {
    const th = this.theme;
    const shellWidth = width - 4;
    const contentWidth = Math.min(shellWidth, 128);
    const sidePad = Math.max(0, Math.floor((shellWidth - contentWidth) / 2));
    const leftMargin = " ".repeat(sidePad);
    const lines: string[] = [];

    const row = (content = ""): string => {
      const truncated = truncateToWidth(content, contentWidth);
      return leftMargin + padRight(truncated, contentWidth);
    };
    const blank = () => row("");
    const hr = () => row(th.fg("dim", "─".repeat(contentWidth)));
    const centered = (content: string) => row(centerLine(content, contentWidth));

    const status = SubprocessManager.status();
    const state = status.state;
    const events = SubprocessManager.getEvents();

    // ── Header ───────────────────────────────────────────────────────
    const title = th.fg("accent", th.bold("AutoAgent Dashboard"));
    const badge = stateBadge(state, th);
    const elapsed = status.startedAt
      ? th.fg("dim", formatDuration(Date.now() - status.startedAt))
      : "";
    lines.push(row(joinColumns(`${title}  ${badge}`, elapsed, contentWidth)));
    lines.push(blank());

    // ── Goal line (from loop_start event) ────────────────────────────
    const loopStart = events.find(e => e.event === "loop_start");
    if (loopStart && loopStart.event === "loop_start") {
      const budgetStr = th.fg("dim", `budget: $${loopStart.budget_usd.toFixed(2)}`);
      lines.push(row(joinColumns(
        `${th.fg("text", "Goal:")} ${th.fg("text", truncateToWidth(loopStart.goal, contentWidth - 30))}`,
        budgetStr,
        contentWidth,
      )));
      lines.push(blank());
    }

    // ── Iteration table ──────────────────────────────────────────────
    const iterationEvents = events.filter(
      (e): e is IterationEndEvent => e.event === "iteration_end",
    );

    if (iterationEvents.length === 0 && state === SubprocessState.Running) {
      lines.push(centered(th.fg("dim", "Waiting for first iteration…")));
      lines.push(blank());
    } else if (iterationEvents.length > 0) {
      // Table header
      const colWidths = { num: 4, score: 8, decision: 10, cost: 9, elapsed: 8, rationale: Math.max(20, contentWidth - 47) };
      const headerLine = [
        th.fg("dim", "#".padEnd(colWidths.num)),
        th.fg("dim", "Score".padEnd(colWidths.score)),
        th.fg("dim", "Decision".padEnd(colWidths.decision)),
        th.fg("dim", "Cost".padEnd(colWidths.cost)),
        th.fg("dim", "Time".padEnd(colWidths.elapsed)),
        th.fg("dim", "Rationale"),
      ].join(" ");
      lines.push(row(headerLine));
      lines.push(row(th.fg("dim", "─".repeat(contentWidth))));

      for (const iter of iterationEvents) {
        const num = String(iter.iteration).padEnd(colWidths.num);
        const scoreStr = iter.score !== null
          ? iter.score.toFixed(2).padEnd(colWidths.score)
          : "—".padEnd(colWidths.score);
        const decisionStr = iter.decision.padEnd(colWidths.decision);
        const costStr = `$${iter.cost_usd.toFixed(3)}`.padEnd(colWidths.cost);
        const elapsedStr = `${(iter.elapsed_ms / 1000).toFixed(1)}s`.padEnd(colWidths.elapsed);
        const rationale = truncateToWidth(iter.rationale, colWidths.rationale);

        const decColor = iter.decision === "keep" ? "success" : iter.decision === "discard" ? "warning" : "text";

        const iterLine = [
          th.fg("text", num),
          iter.score !== null ? th.fg("accent", scoreStr) : th.fg("dim", scoreStr),
          th.fg(decColor, decisionStr),
          th.fg("dim", costStr),
          th.fg("dim", elapsedStr),
          th.fg("dim", rationale),
        ].join(" ");
        lines.push(row(iterLine));
      }
      lines.push(blank());
    }

    // ── Summary / End state ──────────────────────────────────────────
    const loopEnd = events.find(e => e.event === "loop_end");
    if (loopEnd && loopEnd.event === "loop_end") {
      lines.push(hr());
      lines.push(row(th.fg("text", th.bold("Summary"))));
      lines.push(row(`  ${th.fg("dim", "Total iterations:")} ${th.fg("text", String(loopEnd.total_iterations))}`));
      lines.push(row(`  ${th.fg("dim", "Total cost:")} ${th.fg("warning", `$${loopEnd.total_cost_usd.toFixed(4)}`)}`));
      lines.push(row(`  ${th.fg("dim", "Best iteration:")} ${th.fg("accent", loopEnd.best_iteration_id ?? "—")}`));
      lines.push(row(`  ${th.fg("dim", "Final phase:")} ${th.fg("text", loopEnd.phase)}`));
      lines.push(blank());
    }

    // ── Error display ────────────────────────────────────────────────
    const errorEvents = events.filter(e => e.event === "error");
    if (errorEvents.length > 0) {
      lines.push(hr());
      lines.push(row(th.fg("error", th.bold("Errors"))));
      for (const err of errorEvents) {
        if (err.event === "error") {
          lines.push(row(`  ${th.fg("error", `[iter ${err.iteration}]`)} ${th.fg("text", err.message)}`));
        }
      }
      lines.push(blank());
    }

    if (status.lastError && state === SubprocessState.Error) {
      lines.push(row(th.fg("error", `Process error: ${status.lastError}`)));
      lines.push(blank());
    }

    // ── Footer hint ──────────────────────────────────────────────────
    lines.push(hr());
    const hints = state === SubprocessState.Running
      ? "↑↓ scroll · g/G top/end · esc close · /autoagent stop to terminate"
      : "↑↓ scroll · g/G top/end · esc close";
    lines.push(centered(th.fg("dim", hints)));

    return lines;
  }

  invalidate(): void {
    this.cachedWidth = undefined;
    this.cachedLines = undefined;
  }

  dispose(): void {
    clearInterval(this.refreshTimer);
    this.unsubscribe();
  }
}
