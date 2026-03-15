/**
 * Interview Runner — drives `autoagent new --json` via bidirectional JSON protocol.
 *
 * Spawns the Python subprocess, reads JSON lines from stdout, and renders each
 * prompt/confirm/status message using pi's native `ctx.ui.input()` / `ctx.ui.select()`.
 * Sequential input collection — no custom overlay, same pattern as the GSD preferences wizard.
 *
 * Protocol messages (Python → TS):
 *   prompt  { type: "prompt", phase: string, question: string }
 *   confirm { type: "confirm", summary: string }
 *   status  { type: "status", message: string }
 *   complete { type: "complete", config: object, context: string }
 *   error   { type: "error", message: string }
 *
 * Responses (TS → Python):
 *   answer  { type: "answer", text: string }
 *   abort   { type: "abort" }
 */

import { spawn, type ChildProcess } from "node:child_process";
import { createInterface, type Interface as ReadlineInterface } from "node:readline";
import type { ExtensionCommandContext } from "@gsd/pi-coding-agent";

export interface InterviewResult {
  success: boolean;
  error?: string;
}

interface PromptMessage {
  type: "prompt";
  phase: string;
  question: string;
}

interface ConfirmMessage {
  type: "confirm";
  summary: string;
}

interface StatusMessage {
  type: "status";
  message: string;
}

interface CompleteMessage {
  type: "complete";
  config: Record<string, unknown>;
  context: string;
}

interface ErrorMessage {
  type: "error";
  message: string;
}

type ProtocolMessage = PromptMessage | ConfirmMessage | StatusMessage | CompleteMessage | ErrorMessage;

const SIGKILL_TIMEOUT_MS = 5000;

/**
 * Spawn `autoagent new --json` and drive the interview via pi UI dialogs.
 *
 * Each prompt renders as `ui.input()`, confirmations as `ui.select()`,
 * status messages as `ui.notify()`. Escape at any prompt aborts the interview.
 */
export async function runInterview(
  projectDir: string,
  ui: ExtensionCommandContext["ui"],
): Promise<InterviewResult> {
  let proc: ChildProcess;

  try {
    proc = spawn("autoagent", ["--project-dir", projectDir, "new", "--json"], {
      cwd: projectDir,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      stdio: ["pipe", "pipe", "pipe"],
    });
  } catch (err: any) {
    return { success: false, error: `Failed to spawn autoagent: ${err.message}` };
  }

  const stderrLines: string[] = [];
  const STDERR_MAX = 20;

  // Capture stderr tail for diagnostics
  if (proc.stderr) {
    const stderrRl = createInterface({ input: proc.stderr });
    stderrRl.on("line", (line: string) => {
      stderrLines.push(line);
      if (stderrLines.length > STDERR_MAX) {
        stderrLines.shift();
      }
    });
  }

  // Set up readline on stdout for line-buffered JSON parsing
  const rl: ReadlineInterface = createInterface({ input: proc.stdout! });

  // Async line reader: waiters get resolved by incoming lines, or null on close.
  // Protocol is strict request-response so at most one waiter is pending at a time.
  const pendingWaiters: Array<(value: string | null) => void> = [];
  const bufferedLines: string[] = [];
  let lineClosed = false;

  rl.on("line", (line: string) => {
    if (pendingWaiters.length > 0) {
      pendingWaiters.shift()!(line);
    } else {
      bufferedLines.push(line);
    }
  });

  rl.on("close", () => {
    lineClosed = true;
    for (const resolve of pendingWaiters) {
      resolve(null);
    }
    pendingWaiters.length = 0;
  });

  function nextLine(): Promise<string | null> {
    if (bufferedLines.length > 0) {
      return Promise.resolve(bufferedLines.shift()!);
    }
    if (lineClosed) return Promise.resolve(null);
    return new Promise<string | null>((resolve) => {
      pendingWaiters.push(resolve);
    });
  }

  function writeLine(obj: Record<string, unknown>): void {
    if (proc.stdin && !proc.stdin.destroyed) {
      proc.stdin.write(JSON.stringify(obj) + "\n");
    }
  }

  function killProc(): void {
    if (proc && !proc.killed) {
      proc.kill("SIGTERM");
      setTimeout(() => {
        if (proc && !proc.killed) {
          proc.kill("SIGKILL");
        }
      }, SIGKILL_TIMEOUT_MS);
    }
  }

  // Protocol loop: read JSON lines, dispatch on type
  try {
    while (true) {
      const raw = await nextLine();
      if (raw === null) {
        // Subprocess exited without sending complete
        const stderrTail = stderrLines.length > 0 ? `\n${stderrLines.join("\n")}` : "";
        return {
          success: false,
          error: `Interview subprocess exited unexpectedly${stderrTail}`,
        };
      }

      let msg: ProtocolMessage;
      try {
        msg = JSON.parse(raw) as ProtocolMessage;
      } catch {
        // Non-JSON line — skip
        continue;
      }

      switch (msg.type) {
        case "prompt": {
          const answer = await ui.input(msg.question, "");
          if (answer === undefined || answer === null) {
            // User pressed Escape — abort
            writeLine({ type: "abort" });
            killProc();
            ui.notify("Interview cancelled.", "info");
            return { success: false, error: "Interview cancelled by user" };
          }
          writeLine({ type: "answer", text: answer });
          break;
        }

        case "confirm": {
          const choice = await ui.select(msg.summary, ["Yes", "No"]);
          if (choice === undefined || choice === null) {
            // Escape on confirmation — treat as abort
            writeLine({ type: "abort" });
            killProc();
            ui.notify("Interview cancelled.", "info");
            return { success: false, error: "Interview cancelled by user" };
          }
          // Python reads the text field: "Yes" or "No"
          // For confirmation, Python's json_input_fn expects data.get("text", "")
          // and the orchestrator checks if the text matches yes/no patterns
          writeLine({ type: "answer", text: choice });
          break;
        }

        case "status": {
          ui.notify(msg.message, "info");
          break;
        }

        case "complete": {
          ui.notify("Interview complete! Config saved.", "success");
          return { success: true };
        }

        case "error": {
          return { success: false, error: msg.message };
        }

        default: {
          // Unknown message type — skip
          break;
        }
      }
    }
  } catch (err: any) {
    killProc();
    return { success: false, error: `Interview error: ${err.message}` };
  }
}
