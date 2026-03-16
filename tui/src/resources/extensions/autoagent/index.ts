/**
 * AutoAgent Pi Extension — Entry Point
 *
 * Commands:
 *   /autoagent go    — read program.md and dispatch the agent to run the experiment loop
 *   /autoagent stop  — stop the running loop via ctx.abort()
 *
 * Shortcuts:
 *   Ctrl+Alt+A — toggle dashboard overlay (experiment status, scores, branch info)
 *
 * Events:
 *   session_start    — reads .autoagent/ disk state and shows project status with branch info
 *   before_agent_start — injects system.md into the agent's system prompt
 */

import type { ExtensionAPI, ExtensionCommandContext } from "@gsd/pi-coding-agent";
import { Key } from "@gsd/pi-tui";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";
import { DashboardOverlay } from "./dashboard.js";

const __extensionDir = dirname(fileURLToPath(import.meta.url));

function getCurrentBranch(): string | null {
  try {
    return execSync("git branch --show-current", { encoding: "utf-8", cwd: process.cwd() }).trim() || null;
  } catch { return null; }
}

export default function (pi: ExtensionAPI) {
  // ── System prompt injection — tells the LLM it's AutoAgent ────────────
  pi.on("before_agent_start", async (event: any) => {
    let systemContent = "";
    try {
      const promptPath = join(__extensionDir, "prompts", "system.md");
      systemContent = readFileSync(promptPath, "utf-8");
    } catch {
      systemContent =
        "You are AutoAgent — an autonomous experiment system. When no .autoagent/ project exists, guide the user through setup. When one exists, use /autoagent go to run the loop.";
    }

    return {
      systemPrompt: `${event.systemPrompt}\n\n[SYSTEM CONTEXT — AutoAgent]\n\n${systemContent}`,
    };
  });

  // ── Session start — show project status ───────────────────────────────
  pi.on("session_start", async (_event: any, ctx: any) => {
    const projectDir = process.cwd();
    const autoagentDir = join(projectDir, ".autoagent");

    let statusLine: string;
    if (!existsSync(autoagentDir)) {
      statusLine = "No project — describe what you want to optimize to get started";
    } else {
      // Check for key project files
      const hasPipeline = existsSync(join(autoagentDir, "pipeline.py"));
      const hasPrepare = existsSync(join(autoagentDir, "prepare.py"));
      const hasConfig = existsSync(join(autoagentDir, "config.json"));
      const hasResults = existsSync(join(autoagentDir, "results.tsv"));

      // Determine target file
      let targetLabel = "pipeline.py";
      if (hasConfig) {
        try {
          const config = JSON.parse(readFileSync(join(autoagentDir, "config.json"), "utf-8"));
          if (config.target) targetLabel = config.target;
        } catch { /* ignore */ }
      }

      const hasTarget = hasPipeline || hasConfig;

      if (!hasTarget || !hasPrepare) {
        const missing = [!hasTarget && "target file", !hasPrepare && "prepare.py"]
          .filter(Boolean)
          .join(", ");
        statusLine = `Project incomplete — missing ${missing}`;
      } else {
        // Count experiment results if results.tsv exists
        let iterCount = 0;
        if (hasResults) {
          try {
            const lines = readFileSync(join(autoagentDir, "results.tsv"), "utf-8")
              .split("\n")
              .filter((l) => l.trim() && !l.startsWith("commit"));
            iterCount = lines.length;
          } catch { /* ignore */ }
        }
        statusLine = iterCount > 0
          ? `Optimizing ${targetLabel} · ${iterCount} experiment${iterCount !== 1 ? "s" : ""} logged`
          : `Optimizing ${targetLabel} · no experiments yet — use /autoagent go`;
      }
    }

    const branch = getCurrentBranch();
    const branchInfo = branch?.startsWith("autoagent/") ? ` · branch: ${branch}` : "";

    ctx.ui.notify(
      `⚡ AutoAgent${branchInfo}\n${statusLine}\n\nCommands: /autoagent go | stop · Ctrl+Alt+A dashboard`,
      "info",
    );
  });

  // ── /autoagent command ─────────────────────────────────────────────────
  pi.registerCommand("autoagent", {
    description: "AutoAgent — go or stop",

    getArgumentCompletions: (prefix: string) => {
      const subcommands = ["go", "stop"];
      const parts = prefix.trim().split(/\s+/);

      if (parts.length <= 1) {
        return subcommands
          .filter((cmd) => cmd.startsWith(parts[0] ?? ""))
          .map((cmd) => ({ value: cmd, label: cmd }));
      }

      return [];
    },

    handler: async (args: string, ctx: ExtensionCommandContext) => {
      const parts = args.trim().split(/\s+/);
      const subcommand = parts[0] || "go";

      switch (subcommand) {
        case "go": {
          // Guard: require prepare.py + (pipeline.py or config.json with target) before dispatching
          const projectDir = process.cwd();
          const autoagentDir = join(projectDir, ".autoagent");
          const hasPrepare = existsSync(join(autoagentDir, "prepare.py"));
          const hasPipeline = existsSync(join(autoagentDir, "pipeline.py"));
          const hasConfig = existsSync(join(autoagentDir, "config.json"));

          // Need prepare.py always, and either pipeline.py or a config.json pointing at a target
          if (!hasPrepare || (!hasPipeline && !hasConfig)) {
            ctx.ui.notify(
              "Project not ready — describe what you want to optimize and I'll help set it up.",
              "warning",
            );
            return;
          }

          // If config.json exists, verify the target file actually exists
          if (hasConfig && !hasPipeline) {
            try {
              const config = JSON.parse(readFileSync(join(autoagentDir, "config.json"), "utf-8"));
              if (config.target && !existsSync(join(projectDir, config.target))) {
                ctx.ui.notify(
                  `Target file not found: ${config.target}`,
                  "warning",
                );
                return;
              }
            } catch {
              // config.json is malformed — let the agent figure it out
            }
          }

          // Read program.md and dispatch the agent to follow it
          const localProgramPath = join(autoagentDir, "program.md");
          const bundledProgramPath = join(__extensionDir, "prompts", "program.md");
          let programContent: string;

          if (existsSync(localProgramPath)) {
            programContent = readFileSync(localProgramPath, "utf-8");
          } else {
            try {
              programContent = readFileSync(bundledProgramPath, "utf-8");
            } catch {
              ctx.ui.notify(
                "No program.md found — describe what you want to optimize to set up a project first.",
                "warning",
              );
              return;
            }
          }

          ctx.ui.notify("⚡ Starting autonomous experiment loop...", "info");

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

        case "stop": {
          if (ctx.isIdle()) {
            ctx.ui.notify("Nothing running to stop.", "info");
          } else {
            ctx.abort();
            ctx.ui.notify("⚡ Experiment loop stopped.", "info");
          }
          return;
        }

        default:
          ctx.ui.notify(
            `Unknown subcommand: ${subcommand}. Available: go, stop`,
            "warning",
          );
      }
    },
  });

  // ── Ctrl+Alt+A shortcut — open dashboard overlay ────────────────────
  pi.registerShortcut(Key.ctrlAlt("a"), {
    description: "AutoAgent dashboard",
    handler: async (ctx) => {
      await ctx.ui.custom<void>(
        (tui, theme, _kb, done) => {
          return new DashboardOverlay(tui, theme, () => done());
        },
        {
          overlay: true,
          overlayOptions: {
            width: "80%",
            minWidth: 60,
            maxHeight: "80%",
            anchor: "center",
          },
        },
      );
    },
  });
}
