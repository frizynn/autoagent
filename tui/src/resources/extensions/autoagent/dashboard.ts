/**
 * AutoAgent Dashboard Overlay
 *
 * Overlay showing experiment progress: current branch, score summary,
 * results table from .autoagent/results.tsv, and experiment branch list.
 * Toggled with Ctrl+Alt+A. Refreshes from disk every 2 seconds.
 */

import type { Theme } from "@gsd/pi-coding-agent";
import { truncateToWidth, visibleWidth, matchesKey, Key } from "@gsd/pi-tui";
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { execSync } from "node:child_process";

// ── Helpers ─────────────────────────────────────────────────────────────

function getCurrentBranch(): string | null {
  try {
    return execSync("git branch --show-current", {
      encoding: "utf-8",
      cwd: process.cwd(),
    }).trim() || null;
  } catch {
    return null;
  }
}

function getExperimentBranches(): string[] {
  try {
    const output = execSync("git branch --list 'autoagent/*'", {
      encoding: "utf-8",
      cwd: process.cwd(),
    });
    return output
      .split("\n")
      .map((line) => line.replace(/^\*?\s*/, "").trim())
      .filter(Boolean);
  } catch {
    return [];
  }
}

interface ResultRow {
  commit: string;
  score: string;
  resource: string;
  status: string;
  description: string;
}

interface ParsedResults {
  rows: ResultRow[];
  error: string | null;
}

function parseResultsTsv(projectDir: string): ParsedResults {
  const tsvPath = join(projectDir, ".autoagent", "results.tsv");
  if (!existsSync(tsvPath)) {
    return { rows: [], error: "No results file" };
  }

  try {
    const content = readFileSync(tsvPath, "utf-8");
    const lines = content.split("\n").filter((l) => l.trim() !== "");
    const rows: ResultRow[] = [];

    for (const line of lines) {
      // Skip header line
      if (line.startsWith("commit")) continue;

      const parts = line.split("\t", 5);
      if (parts.length >= 4) {
        rows.push({
          commit: parts[0],
          score: parts[1],
          resource: parts.length >= 5 ? parts[2] : "",
          status: parts.length >= 5 ? parts[3] : parts[2],
          description: parts.length >= 5 ? parts[4] : parts[3],
        });
      }
    }

    return { rows, error: null };
  } catch {
    return { rows: [], error: "Failed to read results.tsv" };
  }
}

// ── Layout helpers ──────────────────────────────────────────────────────

function centerLine(content: string, width: number): string {
  const vis = visibleWidth(content);
  if (vis >= width) return truncateToWidth(content, width);
  const leftPad = Math.floor((width - vis) / 2);
  return " ".repeat(leftPad) + content;
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

// ── Dashboard Overlay ───────────────────────────────────────────────────

export class DashboardOverlay {
  private tui: { requestRender: () => void };
  private theme: Theme;
  private onClose: () => void;
  private cachedWidth?: number;
  private cachedLines?: string[];
  private refreshTimer: ReturnType<typeof setInterval>;
  private scrollOffset = 0;

  // Cached disk state — refreshed every 2s
  private currentBranch: string | null = null;
  private experimentBranches: string[] = [];
  private results: ParsedResults = { rows: [], error: null };

  constructor(
    tui: { requestRender: () => void },
    theme: Theme,
    onClose: () => void,
  ) {
    this.tui = tui;
    this.theme = theme;
    this.onClose = onClose;

    // Initial load
    this.refreshFromDisk();

    // Refresh timer — re-read disk state every 2 seconds
    this.refreshTimer = setInterval(() => {
      this.refreshFromDisk();
      this.invalidate();
      this.tui.requestRender();
    }, 2000);
  }

  private refreshFromDisk(): void {
    this.currentBranch = getCurrentBranch();
    this.experimentBranches = getExperimentBranches();
    this.results = parseResultsTsv(process.cwd());
  }

  // ── Input handling ──────────────────────────────────────────────────

  handleInput(data: string): void {
    if (
      matchesKey(data, Key.escape) ||
      matchesKey(data, Key.ctrl("c")) ||
      matchesKey(data, Key.ctrlAlt("a"))
    ) {
      clearInterval(this.refreshTimer);
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

  // ── Render ──────────────────────────────────────────────────────────

  render(width: number): string[] {
    if (this.cachedLines && this.cachedWidth === width) {
      return this.cachedLines;
    }

    const content = this.buildContentLines(width);

    // Apply scroll — compute viewport from terminal rows
    const viewportHeight = Math.max(5, process.stdout.rows ? process.stdout.rows - 8 : 24);
    const chromeHeight = 2; // top + bottom border
    const visibleContentRows = Math.max(1, viewportHeight - chromeHeight);
    const maxScroll = Math.max(0, content.length - visibleContentRows);
    this.scrollOffset = Math.min(this.scrollOffset, maxScroll);
    const visibleContent = content.slice(
      this.scrollOffset,
      this.scrollOffset + visibleContentRows,
    );

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
      lines.push(
        border("│") +
          " " +
          truncated +
          " ".repeat(padWidth) +
          " " +
          border("│"),
      );
    }
    lines.push(border("╰" + "─".repeat(width - 2) + "╯"));
    return lines;
  }

  private buildContentLines(width: number): string[] {
    const th = this.theme;
    const shellWidth = width - 4;
    const contentWidth = Math.min(shellWidth, 100);
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

    // ── Header ──────────────────────────────────────────────────────
    const title = th.fg("accent", th.bold("AutoAgent Dashboard"));
    const branchName = this.currentBranch || "no branch";
    const branchDisplay = this.currentBranch?.startsWith("autoagent/")
      ? th.fg("warning", `⎇ ${branchName}`)
      : th.fg("dim", `⎇ ${branchName}`);
    const statusHint =
      this.results.rows.length > 0
        ? th.fg("dim", `· ${this.results.rows.length} iterations`)
        : th.fg("dim", "· idle");

    lines.push(row(joinColumns(`${title}  ${branchDisplay}`, statusHint, contentWidth)));
    lines.push(blank());

    // ── Score summary ───────────────────────────────────────────────
    if (this.results.rows.length > 0) {
      const rows = this.results.rows;
      const scores = rows
        .map((r) => parseFloat(r.score))
        .filter((s) => !isNaN(s));
      const bestScore = scores.length > 0 ? Math.max(...scores) : 0;
      const latestScore = scores.length > 0 ? scores[scores.length - 1] : 0;
      const totalIterations = rows.length;

      const keeps = rows.filter((r) => r.status === "keep").length;
      const discards = rows.filter((r) => r.status === "discard").length;
      const crashes = rows.filter(
        (r) => r.status !== "keep" && r.status !== "discard",
      ).length;

      lines.push(row(th.fg("text", th.bold("Score Summary"))));
      lines.push(blank());
      lines.push(
        row(
          `  ${th.fg("dim", "Best:")} ${th.fg("success", String(bestScore))}` +
            `  ${th.fg("dim", "Latest:")} ${th.fg("text", String(latestScore))}` +
            `  ${th.fg("dim", "Iterations:")} ${th.fg("text", String(totalIterations))}`,
        ),
      );
      lines.push(
        row(
          `  ${th.fg("dim", "Keeps:")} ${th.fg("success", String(keeps))}` +
            `  ${th.fg("dim", "Discards:")} ${th.fg("warning", String(discards))}` +
            `  ${th.fg("dim", "Crashes:")} ${th.fg("error", String(crashes))}`,
        ),
      );
    } else {
      lines.push(
        centered(
          th.fg(
            "dim",
            this.results.error === "No results file"
              ? "No experiments yet — use /autoagent go to start"
              : this.results.error || "No experiments yet",
          ),
        ),
      );
    }

    lines.push(blank());

    // ── Experiment branches ─────────────────────────────────────────
    if (this.experimentBranches.length > 1) {
      lines.push(hr());
      lines.push(row(th.fg("text", th.bold("Experiment Branches"))));
      lines.push(blank());

      for (const branch of this.experimentBranches) {
        const isCurrent = branch === this.currentBranch;
        const icon = isCurrent ? th.fg("accent", "▸") : th.fg("dim", "○");
        const branchText = isCurrent
          ? th.fg("accent", branch)
          : th.fg("dim", branch);
        lines.push(row(`  ${icon} ${branchText}`));
      }

      lines.push(blank());
    }

    // ── Results table ───────────────────────────────────────────────
    if (this.results.rows.length > 0) {
      lines.push(hr());
      lines.push(row(th.fg("text", th.bold("Recent Results"))));
      lines.push(blank());

      // Header row
      lines.push(
        row(
          th.fg(
            "dim",
            `  ${"Commit".padEnd(10)}${"Score".padEnd(8)}${"Status".padEnd(10)}Description`,
          ),
        ),
      );

      // Show last 20 rows in reverse chronological order (newest first)
      const recentRows = [...this.results.rows].reverse().slice(0, 20);
      for (const r of recentRows) {
        const commitShort = r.commit.substring(0, 7);
        const statusColor =
          r.status === "keep"
            ? "success"
            : r.status === "discard"
              ? "warning"
              : "error";
        const desc = truncateToWidth(r.description, contentWidth - 42);

        lines.push(
          row(
            `  ${th.fg("text", commitShort.padEnd(10))}` +
              `${th.fg("text", r.score.padEnd(8))}` +
              `${th.fg("dim", (r.resource || "").padEnd(12))}` +
              `${th.fg(statusColor, r.status.padEnd(10))}` +
              `${th.fg("dim", desc)}`,
          ),
        );
      }

      if (this.results.rows.length > 20) {
        lines.push(
          row(
            th.fg(
              "dim",
              `  ...and ${this.results.rows.length - 20} earlier iterations`,
            ),
          ),
        );
      }
    }

    // ── Footer ──────────────────────────────────────────────────────
    lines.push(blank());
    lines.push(hr());
    lines.push(centered(th.fg("dim", "↑↓ scroll · g/G top/end · esc close")));

    return lines;
  }

  // ── Cache / lifecycle ───────────────────────────────────────────────

  invalidate(): void {
    this.cachedWidth = undefined;
    this.cachedLines = undefined;
  }

  dispose(): void {
    clearInterval(this.refreshTimer);
  }
}
