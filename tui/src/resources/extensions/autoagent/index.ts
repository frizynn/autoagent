/**
 * AutoAgent Pi Extension — Entry Point
 *
 * Architecture: each experiment iteration gets a fresh session.
 * State persists on disk in .autoagent/STATE.md (the "living document").
 * The extension orchestrates: agent_end → read disk → new session → dispatch.
 *
 * Phases:
 *   1. Setup (MODE A) — scan repo, clarify with user, write prepare.py + target, validate baseline
 *   2. Exploration — research the domain, study the target code, formulate initial hypotheses
 *   3. Iterations — read STATE.md → research → hypothesize → implement → eval → update STATE.md
 *
 * Commands:
 *   /autoagent go    — start the experiment loop (exploration + iterations)
 *   /autoagent stop  — stop the running loop
 *
 * Shortcuts:
 *   Ctrl+Alt+A — toggle dashboard overlay
 *
 * Events:
 *   session_start       — show project status
 *   before_agent_start  — inject system.md into agent system prompt
 *   agent_end           — dispatch next iteration (if loop is active)
 */

import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "@gsd/pi-coding-agent";
import { Key } from "@gsd/pi-tui";
import { readFileSync, existsSync, writeFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";
import { DashboardOverlay } from "./dashboard.js";

const __extensionDir = dirname(fileURLToPath(import.meta.url));

// ── Loop state (module-level) ───────────────────────────────────────────

let loopActive = false;
let loopPhase: "idle" | "exploration" | "iterating" = "idle";
let cmdCtx: ExtensionCommandContext | null = null;
let iterationCount = 0;

// ── Helpers ─────────────────────────────────────────────────────────────

function getCurrentBranch(): string | null {
  try {
    return execSync("git branch --show-current", { encoding: "utf-8", cwd: process.cwd() }).trim() || null;
  } catch { return null; }
}

function getProjectConfig(): { target: string } | null {
  const autoagentDir = join(process.cwd(), ".autoagent");
  const configPath = join(autoagentDir, "config.json");
  if (existsSync(configPath)) {
    try {
      return JSON.parse(readFileSync(configPath, "utf-8"));
    } catch { /* malformed */ }
  }
  // Default: pipeline.py in .autoagent/
  if (existsSync(join(autoagentDir, "pipeline.py"))) {
    return { target: ".autoagent/pipeline.py" };
  }
  return null;
}

function readStateDoc(): string | null {
  const statePath = join(process.cwd(), ".autoagent", "STATE.md");
  if (!existsSync(statePath)) return null;
  try {
    return readFileSync(statePath, "utf-8");
  } catch { return null; }
}

function readResultsTsv(): string | null {
  const tsvPath = join(process.cwd(), ".autoagent", "results.tsv");
  if (!existsSync(tsvPath)) return null;
  try {
    return readFileSync(tsvPath, "utf-8");
  } catch { return null; }
}

// ── Prompt Builders ─────────────────────────────────────────────────────

function buildExplorationPrompt(programContent: string, config: { target: string }): string {
  return `You are starting a new AutoAgent experiment run. This is the EXPLORATION phase.

## Your Task

1. **Read the target file** — Read \`${config.target}\` thoroughly. Understand what it does, how it works, its strengths and weaknesses.

2. **Read the evaluator** — Read \`.autoagent/prepare.py\` to understand exactly what the metric measures and what "better" means.

3. **Research** — Search the web for relevant techniques, papers, and approaches that could improve this code. Look for state-of-the-art methods in this domain.

4. **Create the experiment branch** — \`git checkout -b autoagent/run-$(date +%b%d | tr A-Z a-z)\` (append a counter if it exists).

5. **Run the baseline** — Run \`cd .autoagent && python3 prepare.py eval > eval.log 2>&1\` and record the baseline score.

6. **Initialize results.tsv** — Create \`.autoagent/results.tsv\` with header if it doesn't exist:
   \`\`\`
   commit\tscore\tresource\tstatus\tdescription
   \`\`\`
   Log the baseline result.

7. **Write STATE.md** — Create \`.autoagent/STATE.md\` with your findings:
   - What the target code does (brief)
   - Baseline score and what the metric measures
   - Key observations about the code (inefficiencies, patterns, limitations)
   - Research findings (techniques, papers, approaches found on the web)
   - Ranked list of hypotheses to test (most promising first)
   - Each hypothesis should have: what to change, why it might improve the score, expected impact

This document is your memory between iterations. Future iterations will read it to decide what to try next. Make it useful.

## Experiment Protocol

${programContent}`;
}

function buildIterationPrompt(programContent: string, config: { target: string }, stateDoc: string, resultsTsv: string): string {
  return `You are running iteration ${iterationCount + 1} of an AutoAgent experiment. Each iteration is a fresh session — STATE.md is your memory.

## Current State

### STATE.md (your living document — update this at the end)
${stateDoc}

### results.tsv (experiment log)
\`\`\`
${resultsTsv}
\`\`\`

### Target file: \`${config.target}\`

## Your Task This Iteration

1. **Review STATE.md** — Read your hypotheses and previous findings. Pick the most promising untested hypothesis.

2. **Research if needed** — If the hypothesis needs more context, search the web for papers, techniques, or implementations. Add findings to STATE.md.

3. **Implement** — Edit \`${config.target}\` with the change. Keep it focused — one hypothesis per iteration.

4. **Commit** — \`git add ${config.target} && git commit -m "<description>"\`

5. **Evaluate** — \`cd .autoagent && python3 prepare.py eval > eval.log 2>&1\` then \`grep "^score:" .autoagent/eval.log\`

6. **Keep or discard:**
   - Score improved → KEEP. Log with status \`keep\`.
   - Score equal or worse → DISCARD. Log with status \`discard\`, then \`git reset --hard HEAD~1\`.
   - Crashed → try to fix (use judgment). If fundamentally broken, log \`crash\` and revert.

7. **Log to results.tsv** — Append the result (tab-separated). Do NOT commit results.tsv.

8. **Update STATE.md** — This is critical. Update:
   - What you tried and what happened (add to history)
   - Mark tested hypotheses with results
   - Add new hypotheses based on what you learned
   - Update research notes if you found new information
   - Re-rank remaining hypotheses

   STATE.md is how the next iteration knows what happened. If you don't update it, the next iteration starts blind.

**IMPORTANT**: Always redirect eval output: \`> eval.log 2>&1\`. Do NOT let output flood your context.

## Experiment Protocol

${programContent}`;
}

// ── Extension ───────────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  // ── System prompt injection ───────────────────────────────────────────
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
      const hasPrepare = existsSync(join(autoagentDir, "prepare.py"));
      const config = getProjectConfig();
      const hasResults = existsSync(join(autoagentDir, "results.tsv"));

      const targetLabel = config?.target ?? "pipeline.py";

      if (!config || !hasPrepare) {
        const missing = [!config && "target file", !hasPrepare && "prepare.py"]
          .filter(Boolean)
          .join(", ");
        statusLine = `Project incomplete — missing ${missing}`;
      } else {
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

  // ── agent_end — dispatch next iteration ───────────────────────────────
  pi.on("agent_end", async (_event: any, ctx: ExtensionContext) => {
    if (!loopActive || !cmdCtx) return;

    // Small delay to let files settle
    await new Promise(r => setTimeout(r, 500));

    const config = getProjectConfig();
    if (!config) {
      loopActive = false;
      loopPhase = "idle";
      ctx.ui.notify("Loop stopped — no project config found.", "warning");
      return;
    }

    if (loopPhase === "exploration") {
      // Exploration just finished — check if STATE.md was created
      const stateDoc = readStateDoc();
      if (!stateDoc) {
        ctx.ui.notify("Exploration didn't produce STATE.md. Stopping.", "warning");
        loopActive = false;
        loopPhase = "idle";
        return;
      }
      // Transition to iterating
      loopPhase = "iterating";
      iterationCount = 0;
      ctx.ui.notify("Exploration complete. Starting experiment iterations.", "info");
    } else if (loopPhase === "iterating") {
      iterationCount++;
    }

    // Read state and results for next iteration
    const stateDoc = readStateDoc();
    const resultsTsv = readResultsTsv();

    if (!stateDoc) {
      ctx.ui.notify("STATE.md missing — cannot continue iterations. Stopping.", "warning");
      loopActive = false;
      loopPhase = "idle";
      return;
    }

    // Read program.md for protocol rules
    const autoagentDir = join(process.cwd(), ".autoagent");
    let programContent = "";
    const localProgram = join(autoagentDir, "program.md");
    const bundledProgram = join(__extensionDir, "prompts", "program.md");
    if (existsSync(localProgram)) {
      programContent = readFileSync(localProgram, "utf-8");
    } else if (existsSync(bundledProgram)) {
      programContent = readFileSync(bundledProgram, "utf-8");
    }

    // Fresh session for this iteration
    const result = await cmdCtx.newSession();
    if (result.cancelled) {
      loopActive = false;
      loopPhase = "idle";
      ctx.ui.notify("Experiment loop stopped.", "info");
      return;
    }

    const prompt = buildIterationPrompt(programContent, config, stateDoc, resultsTsv ?? "commit\tscore\tresource\tstatus\tdescription\n");

    ctx.ui.notify(`⚡ Iteration ${iterationCount + 1}`, "info");

    pi.sendMessage(
      { customType: "autoagent-iteration", content: prompt, display: false },
      { triggerTurn: true },
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
          // Guard: require prepare.py + (pipeline.py or config.json with target)
          const projectDir = process.cwd();
          const autoagentDir = join(projectDir, ".autoagent");
          const hasPrepare = existsSync(join(autoagentDir, "prepare.py"));
          const config = getProjectConfig();

          if (!hasPrepare || !config) {
            ctx.ui.notify(
              "Project not ready — describe what you want to optimize and I'll help set it up.",
              "warning",
            );
            return;
          }

          // Verify target file exists
          if (!existsSync(join(projectDir, config.target))) {
            ctx.ui.notify(`Target file not found: ${config.target}`, "warning");
            return;
          }

          // Read program.md
          const localProgram = join(autoagentDir, "program.md");
          const bundledProgram = join(__extensionDir, "prompts", "program.md");
          let programContent = "";
          if (existsSync(localProgram)) {
            programContent = readFileSync(localProgram, "utf-8");
          } else if (existsSync(bundledProgram)) {
            programContent = readFileSync(bundledProgram, "utf-8");
          } else {
            ctx.ui.notify("No program.md found.", "warning");
            return;
          }

          // Activate loop
          loopActive = true;
          cmdCtx = ctx;
          iterationCount = 0;

          // Determine phase: if STATE.md exists, resume iterating; otherwise, explore first
          const stateDoc = readStateDoc();
          if (stateDoc) {
            loopPhase = "iterating";
            const resultsTsv = readResultsTsv();
            ctx.ui.notify("⚡ Resuming experiment loop from STATE.md...", "info");
            const prompt = buildIterationPrompt(programContent, config, stateDoc, resultsTsv ?? "commit\tscore\tresource\tstatus\tdescription\n");
            pi.sendMessage(
              { customType: "autoagent-iteration", content: prompt, display: false },
              { triggerTurn: true },
            );
          } else {
            loopPhase = "exploration";
            ctx.ui.notify("⚡ Starting exploration phase...", "info");
            const prompt = buildExplorationPrompt(programContent, config);
            pi.sendMessage(
              { customType: "autoagent-exploration", content: prompt, display: false },
              { triggerTurn: true },
            );
          }
          return;
        }

        case "stop": {
          if (loopActive) {
            loopActive = false;
            loopPhase = "idle";
            cmdCtx = null;
            ctx.abort();
            ctx.ui.notify(`⚡ Experiment loop stopped after ${iterationCount} iterations.`, "info");
          } else if (!ctx.isIdle()) {
            ctx.abort();
            ctx.ui.notify("⚡ Stopped.", "info");
          } else {
            ctx.ui.notify("Nothing running to stop.", "info");
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

  // ── Ctrl+Alt+A shortcut — dashboard overlay ───────────────────────────
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
