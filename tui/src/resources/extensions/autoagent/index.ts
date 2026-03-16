/**
 * AutoAgent Pi Extension — Entry Point
 *
 * Commands:
 *   /autoagent go    — read program.md and dispatch the agent to run the experiment loop
 *   /autoagent stop  — stop the running loop (placeholder until S03)
 *
 * Shortcuts:
 *   Ctrl+Alt+A — placeholder (will toggle dashboard in S03)
 *
 * Events:
 *   session_start    — reads .autoagent/ disk state and shows project status
 *   before_agent_start — injects system.md into the agent's system prompt
 */

import type { ExtensionAPI, ExtensionCommandContext } from "@gsd/pi-coding-agent";
import { Key } from "@gsd/pi-tui";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __extensionDir = dirname(fileURLToPath(import.meta.url));

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
      const hasResults = existsSync(join(autoagentDir, "results.tsv"));

      if (!hasPipeline || !hasPrepare) {
        statusLine = "Project incomplete — missing " +
          [!hasPipeline && "pipeline.py", !hasPrepare && "prepare.py"]
            .filter(Boolean)
            .join(", ");
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
          ? `Project ready · ${iterCount} experiment${iterCount !== 1 ? "s" : ""} logged`
          : "Project ready · no experiments yet — use /autoagent go";
      }
    }

    ctx.ui.notify(
      `⚡ AutoAgent\n${statusLine}\n\nCommands: /autoagent go | stop`,
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
          // Read program.md and dispatch the agent to follow it
          const projectDir = process.cwd();
          const localProgramPath = join(projectDir, ".autoagent", "program.md");
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
          // Placeholder — will gain real interrupt behavior in S03
          ctx.ui.notify("Nothing running to stop.", "info");
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

  // ── Ctrl+Alt+A shortcut — placeholder for future dashboard ─────────────
  pi.registerShortcut(Key.ctrlAlt("a"), {
    description: "AutoAgent dashboard (coming soon)",
    handler: async (ctx) => {
      ctx.ui.notify("Dashboard not yet available — coming in S03.", "info");
    },
  });
}
