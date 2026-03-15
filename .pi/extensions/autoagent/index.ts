/**
 * AutoAgent Pi Extension — Entry Point
 *
 * Commands:
 *   /autoagent run [--budget N]  — start optimization, open dashboard
 *   /autoagent stop              — terminate running subprocess
 *   /autoagent status            — one-line state summary
 *
 * Shortcuts:
 *   Ctrl+Alt+A — toggle dashboard overlay
 *
 * Footer:
 *   Shows subprocess state: ⚡ iteration N, ✓ done, ✗ error
 */

import type { ExtensionAPI, ExtensionCommandContext } from "@gsd/pi-coding-agent";
import { Key } from "@gsd/pi-tui";
import { SubprocessManager } from "./subprocess-manager.js";
import { AutoagentDashboardOverlay } from "./dashboard-overlay.js";
import { SubprocessState } from "./types.js";
import { runInterview } from "./interview-runner.js";

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

export default function (pi: ExtensionAPI) {
  // ── /autoagent command ─────────────────────────────────────────────────
  pi.registerCommand("autoagent", {
    description: "AutoAgent — run, stop, status, or new (project interview)",
    handler: async (args: string, ctx: ExtensionCommandContext) => {
      const parts = args.trim().split(/\s+/);
      const subcommand = parts[0] || "run";

      switch (subcommand) {
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

        default:
          ctx.ui.notify(`Unknown subcommand: ${subcommand}. Use run, stop, status, or new.`, "warning");
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
