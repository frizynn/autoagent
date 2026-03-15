/**
 * AutoAgent Pi Extension — Entry Point
 *
 * Commands:
 *   /autoagent run [--budget N]  — start optimization, open dashboard
 *   /autoagent stop              — terminate running subprocess
 *   /autoagent status            — one-line state summary (reads disk when idle)
 *   /autoagent new               — run project interview
 *   /autoagent report            — generate and view markdown report
 *
 * Shortcuts:
 *   Ctrl+Alt+A — toggle dashboard overlay
 *
 * Footer:
 *   Shows subprocess state: ⚡ iteration N, ✓ done, ✗ error
 */

import type { ExtensionAPI, ExtensionCommandContext } from "@gsd/pi-coding-agent";
import { Key } from "@gsd/pi-tui";
import { execFile } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { SubprocessManager } from "./subprocess-manager.js";
import { AutoagentDashboardOverlay } from "./dashboard-overlay.js";
import { AutoagentReportOverlay } from "./report-overlay.js";
import { SubprocessState } from "./types.js";
import { runInterview } from "./interview-runner.js";

const __extensionDir = dirname(fileURLToPath(import.meta.url));
let overlayOpen = false;

function updateFooter(ctx: { ui: ExtensionCommandContext["ui"] }): void {
  const status = SubprocessManager.status();
  switch (status.state) {
    case SubprocessState.Idle:
      ctx.ui.setStatus("autoagent", "");
      break;
    case SubprocessState.Running: {
      const events = SubprocessManager.getEvents();
      const lastIterEnd = [...events].reverse().find(e => e.event === "iteration_end");
      const iterNum = lastIterEnd && lastIterEnd.event === "iteration_end" ? lastIterEnd.iteration : 0;
      ctx.ui.setStatus("autoagent", `⚡ iteration ${iterNum}`);
      break;
    }
    case SubprocessState.Completed: {
      const events = SubprocessManager.getEvents();
      const loopEnd = events.find(e => e.event === "loop_end");
      const total = loopEnd && loopEnd.event === "loop_end" ? loopEnd.total_iterations : "?";
      ctx.ui.setStatus("autoagent", `✓ done (${total} iterations)`);
      break;
    }
    case SubprocessState.Error:
      ctx.ui.setStatus("autoagent", "✗ error");
      break;
    case SubprocessState.Stopped:
      ctx.ui.setStatus("autoagent", "■ stopped");
      break;
  }
}

async function openDashboard(ctx: ExtensionCommandContext): Promise<void> {
  if (overlayOpen) return;
  overlayOpen = true;

  await ctx.ui.custom<void>(
    (tui, theme, _kb, done) => {
      return new AutoagentDashboardOverlay(tui, theme, () => {
        overlayOpen = false;
        done();
      });
    },
    {
      overlay: true,
      overlayOptions: {
        width: "90%",
        minWidth: 80,
        maxHeight: "92%",
        anchor: "center",
      },
    },
  );
}

async function openReport(ctx: ExtensionCommandContext, markdown: string): Promise<void> {
  if (overlayOpen) return;
  overlayOpen = true;

  await ctx.ui.custom<void>(
    (tui, theme, _kb, done) => {
      return new AutoagentReportOverlay(tui, theme, () => {
        overlayOpen = false;
        done();
      }, markdown);
    },
    {
      overlay: true,
      overlayOptions: {
        width: "90%",
        minWidth: 80,
        maxHeight: "92%",
        anchor: "center",
      },
    },
  );
}

export default function (pi: ExtensionAPI) {
  // ── System prompt injection — tells the LLM it's AutoAgent ────────────
  pi.on("before_agent_start", async (event: any) => {
    let systemContent = "";
    try {
      const promptPath = join(__extensionDir, "prompts", "system.md");
      systemContent = readFileSync(promptPath, "utf-8");
    } catch {
      systemContent = "You are AutoAgent — an autonomous optimization system for agentic architectures.";
    }

    return {
      systemPrompt: `${event.systemPrompt}\n\n[SYSTEM CONTEXT — AutoAgent]\n\n${systemContent}`,
    };
  });

  // ── Startup header ────────────────────────────────────────────────────
  pi.on("session_start", async (_event: any, ctx: any) => {
    const version = process.env.AUTOAGENT_VERSION || "0.1.0";

    // Check project status
    const projectDir = process.cwd();
    const statePath = join(projectDir, ".autoagent", "state.json");

    let statusLine = "No project — use /autoagent new to configure";
    if (existsSync(statePath)) {
      try {
        const state = JSON.parse(readFileSync(statePath, "utf-8"));
        const configPath = join(projectDir, ".autoagent", "config.json");
        const config = existsSync(configPath) ? JSON.parse(readFileSync(configPath, "utf-8")) : {};
        const goal = config.goal ? `"${config.goal}"` : "no goal set";
        statusLine = `${state.phase} · iter ${state.current_iteration} · best #${state.best_iteration_id || "—"} · $${(state.total_cost_usd || 0).toFixed(4)} · ${goal}`;
      } catch { /* ignore */ }
    }

    ctx.ui.notify(
      `⚡ AutoAgent v${version}\n${statusLine}\n\nCommands: /autoagent run | stop | new | status | report\nDashboard: Ctrl+Alt+A`,
      "info",
    );
  });

  // ── /autoagent command ─────────────────────────────────────────────────
  pi.registerCommand("autoagent", {
    description: "AutoAgent — go, run, stop, status, new, or report",

    getArgumentCompletions: (prefix: string) => {
      const subcommands = ["go", "run", "stop", "status", "new", "report"];
      const parts = prefix.trim().split(/\s+/);

      if (parts.length <= 1) {
        return subcommands
          .filter((cmd) => cmd.startsWith(parts[0] ?? ""))
          .map((cmd) => ({ value: cmd, label: cmd }));
      }

      // --budget flag completion for "run" subcommand
      if (parts[0] === "run" && parts.length <= 2) {
        const flagPrefix = parts[1] ?? "";
        return ["--budget"]
          .filter((f) => f.startsWith(flagPrefix))
          .map((f) => ({ value: `run ${f}`, label: f }));
      }

      return [];
    },

    handler: async (args: string, ctx: ExtensionCommandContext) => {
      const parts = args.trim().split(/\s+/);
      const subcommand = parts[0] || "run";

      switch (subcommand) {
        case "go": {
          // Agent-driven experiment loop — read program.md and let the LLM iterate
          const projectDir = process.cwd();
          const programPath = join(projectDir, ".autoagent", "program.md");
          let programContent: string;

          if (existsSync(programPath)) {
            programContent = readFileSync(programPath, "utf-8");
          } else {
            // Use bundled program.md
            try {
              programContent = readFileSync(join(__extensionDir, "prompts", "program.md"), "utf-8");
            } catch {
              ctx.ui.notify("No program.md found. Use /autoagent new to set up a project.", "warning");
              return;
            }
          }

          ctx.ui.notify("⚡ Starting autonomous experiment loop...", "info");

          // Dispatch the agent with program.md as context
          pi.sendMessage(
            {
              customType: "autoagent-go",
              content: `Read and follow this experiment protocol exactly. Begin the experiment loop now.\n\n${programContent}`,
              display: false,
            },
            { triggerTurn: true },
          );
          return;
        }

        case "run": {
          if (SubprocessManager.status().state === SubprocessState.Running) {
            ctx.ui.notify("Optimization already running. Use /autoagent stop first.", "warning");
            await openDashboard(ctx);
            return;
          }

          // Parse --budget flag
          const budgetIdx = parts.indexOf("--budget");
          const extraArgs: string[] = [];
          if (budgetIdx !== -1 && parts[budgetIdx + 1]) {
            extraArgs.push("--budget", parts[budgetIdx + 1]);
          }

          const projectDir = process.cwd();

          // Subscribe to events for footer updates
          const unsubFooter = SubprocessManager.onEvent(() => updateFooter(ctx));

          // Also update footer when process exits (state change without event)
          // Poll briefly after start to catch exit
          const exitPoll = setInterval(() => {
            const st = SubprocessManager.status().state;
            if (st !== SubprocessState.Running) {
              updateFooter(ctx);
              clearInterval(exitPoll);
              unsubFooter();
            }
          }, 1000);

          SubprocessManager.start(projectDir, extraArgs);
          updateFooter(ctx);

          // Open dashboard overlay
          await openDashboard(ctx);
          break;
        }

        case "stop": {
          if (SubprocessManager.status().state !== SubprocessState.Running) {
            ctx.ui.notify("No optimization running.", "info");
            return;
          }
          SubprocessManager.stop();
          updateFooter(ctx);
          ctx.ui.notify("Optimization stopped.", "info");
          break;
        }

        case "status": {
          const status = SubprocessManager.status();

          // When idle, try reading disk state for richer info
          if (status.state === SubprocessState.Idle) {
            const projectDir = process.cwd();
            const statePath = join(projectDir, ".autoagent", "state.json");
            const configPath = join(projectDir, ".autoagent", "config.json");

            if (existsSync(statePath) && existsSync(configPath)) {
              try {
                const state = JSON.parse(readFileSync(statePath, "utf-8"));
                const config = JSON.parse(readFileSync(configPath, "utf-8"));
                const parts: string[] = [`AutoAgent: idle`];
                if (config.goal) parts.push(`goal: ${config.goal}`);
                if (state.phase) parts.push(`phase: ${state.phase}`);
                if (state.current_iteration != null) parts.push(`iterations: ${state.current_iteration}`);
                if (state.best_iteration_id) parts.push(`best: ${state.best_iteration_id}`);
                if (state.total_cost_usd != null) parts.push(`cost: $${Number(state.total_cost_usd).toFixed(4)}`);
                ctx.ui.notify(parts.join(" · "), "info");
              } catch {
                ctx.ui.notify("AutoAgent: idle (state files unreadable)", "info");
              }
            } else if (existsSync(join(projectDir, ".autoagent"))) {
              ctx.ui.notify("AutoAgent: idle (project exists, no completed runs)", "info");
            } else {
              ctx.ui.notify(`AutoAgent: idle — no project found in ${projectDir}`, "info");
            }
            break;
          }

          const stateStr = status.state;
          const pidStr = status.pid ? ` (PID ${status.pid})` : "";
          const evtStr = ` · ${status.eventCount} events`;
          const errStr = status.lastError ? ` · last error: ${status.lastError}` : "";
          ctx.ui.notify(`AutoAgent: ${stateStr}${pidStr}${evtStr}${errStr}`, "info");
          break;
        }

        case "new": {
          const projectDir = process.cwd();
          ctx.ui.notify("Starting project interview...", "info");
          const result = await runInterview(projectDir, ctx.ui);
          if (!result.success) {
            ctx.ui.notify(result.error ?? "Interview failed.", "warning");
          }
          break;
        }

        case "report": {
          const projectDir = process.cwd();
          const reportPath = join(projectDir, ".autoagent", "report.md");

          // Run autoagent report to generate/refresh the report file
          try {
            await new Promise<void>((resolve, reject) => {
              execFile("autoagent", ["--project-dir", projectDir, "report"], (error, _stdout, stderr) => {
                if (error) {
                  reject(new Error(stderr.trim() || `autoagent report failed (exit ${error.code})`));
                } else {
                  resolve();
                }
              });
            });
          } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            ctx.ui.notify(`Report generation failed: ${msg}`, "warning");
            return;
          }

          // Read the generated report
          if (!existsSync(reportPath)) {
            ctx.ui.notify("Report file not found after generation. Is this an AutoAgent project?", "warning");
            return;
          }

          let markdown: string;
          try {
            markdown = readFileSync(reportPath, "utf-8");
          } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            ctx.ui.notify(`Failed to read report: ${msg}`, "warning");
            return;
          }

          if (!markdown.trim()) {
            ctx.ui.notify("Report is empty — no iterations recorded yet.", "info");
            return;
          }

          await openReport(ctx, markdown);
          break;
        }

        default:
          ctx.ui.notify(`Unknown subcommand: ${subcommand}. Use run, stop, status, new, or report.`, "warning");
      }
    },
  });

  // ── Ctrl+Alt+A shortcut — toggle dashboard overlay ─────────────────────
  pi.registerShortcut(Key.ctrlAlt("a"), {
    description: "Toggle AutoAgent dashboard",
    handler: async (ctx) => {
      if (overlayOpen) {
        // Overlay is open — pressing the shortcut will be handled by
        // the overlay's handleInput (which closes on Ctrl+Alt+A)
        return;
      }

      const state = SubprocessManager.status().state;
      if (state === SubprocessState.Idle) {
        ctx.ui.notify("No optimization running. Use /autoagent run to start.", "info");
        return;
      }

      // Open overlay for running/completed/error/stopped state
      await openDashboard(ctx as any);
    },
  });
}
