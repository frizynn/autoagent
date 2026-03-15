/**
 * SubprocessManager — singleton managing the autoagent Python child process.
 *
 * Spawns `autoagent run --jsonl` with PYTHONUNBUFFERED=1 (D068), parses
 * JSONL events from stdout, and exposes lifecycle controls + event stream.
 */

import { spawn, type ChildProcess } from "node:child_process";
import { createInterface, type Interface as ReadlineInterface } from "node:readline";
import { type AutoagentEvent, SubprocessState } from "./types.js";

const MAX_EVENTS = 200;
const SIGKILL_TIMEOUT_MS = 5000;

type EventCallback = (event: AutoagentEvent) => void;

class SubprocessManagerImpl {
  private proc: ChildProcess | null = null;
  private rl: ReadlineInterface | null = null;
  private events: AutoagentEvent[] = [];
  private subscribers: Set<EventCallback> = new Set();
  private _state: SubprocessState = SubprocessState.Idle;
  private _pid: number | null = null;
  private _exitCode: number | null = null;
  private _lastError: string | null = null;
  private _stderrTail: string[] = [];
  private _startedAt: number | null = null;
  private killTimer: ReturnType<typeof setTimeout> | null = null;

  get state(): SubprocessState {
    return this._state;
  }

  get pid(): number | null {
    return this._pid;
  }

  get exitCode(): number | null {
    return this._exitCode;
  }

  get lastError(): string | null {
    return this._lastError;
  }

  get stderrTail(): string[] {
    return this._stderrTail.slice();
  }

  get startedAt(): number | null {
    return this._startedAt;
  }

  status(): { state: SubprocessState; pid: number | null; exitCode: number | null; lastError: string | null; eventCount: number; startedAt: number | null } {
    return {
      state: this._state,
      pid: this._pid,
      exitCode: this._exitCode,
      lastError: this._lastError,
      eventCount: this.events.length,
      startedAt: this._startedAt,
    };
  }

  getEvents(): AutoagentEvent[] {
    return this.events.slice();
  }

  onEvent(cb: EventCallback): () => void {
    this.subscribers.add(cb);
    return () => { this.subscribers.delete(cb); };
  }

  start(projectDir: string, extraArgs: string[] = []): void {
    if (this._state === SubprocessState.Running) {
      throw new Error("Subprocess already running");
    }

    // Reset state
    this.events = [];
    this._exitCode = null;
    this._lastError = null;
    this._stderrTail = [];
    this._startedAt = Date.now();
    this._state = SubprocessState.Running;

    const args = ["run", "--jsonl", ...extraArgs];

    try {
      this.proc = spawn("autoagent", args, {
        cwd: projectDir,
        env: { ...process.env, PYTHONUNBUFFERED: "1" },
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (err: any) {
      this._state = SubprocessState.Error;
      this._lastError = `Spawn failed: ${err.message}`;
      this.notify({ event: "error", timestamp: new Date().toISOString(), message: this._lastError, iteration: 0 });
      return;
    }

    this._pid = this.proc.pid ?? null;

    // Parse JSONL from stdout
    this.rl = createInterface({ input: this.proc.stdout! });
    this.rl.on("line", (line: string) => {
      try {
        const parsed = JSON.parse(line) as AutoagentEvent;
        this.events.push(parsed);
        if (this.events.length > MAX_EVENTS) {
          this.events.shift();
        }
        this.notify(parsed);
      } catch {
        // Non-JSON line on stdout — ignore
      }
    });

    // Capture stderr tail (last 20 lines)
    const stderrRl = createInterface({ input: this.proc.stderr! });
    stderrRl.on("line", (line: string) => {
      this._stderrTail.push(line);
      if (this._stderrTail.length > 20) {
        this._stderrTail.shift();
      }
    });

    // Handle process exit
    this.proc.on("error", (err: Error) => {
      this._state = SubprocessState.Error;
      this._lastError = `Process error: ${err.message}`;
      this.notify({ event: "error", timestamp: new Date().toISOString(), message: this._lastError, iteration: 0 });
      this.cleanup();
    });

    this.proc.on("close", (code: number | null) => {
      this._exitCode = code;
      if (this._state === SubprocessState.Stopped) {
        // Already marked as stopped by stop()
      } else if (code === 0) {
        this._state = SubprocessState.Completed;
      } else {
        this._state = SubprocessState.Error;
        this._lastError = `Process exited with code ${code}`;
      }
      this.cleanup();
    });
  }

  stop(): void {
    if (!this.proc || this._state !== SubprocessState.Running) {
      return;
    }

    this._state = SubprocessState.Stopped;
    this.proc.kill("SIGTERM");

    // SIGKILL after timeout if still alive
    this.killTimer = setTimeout(() => {
      if (this.proc && !this.proc.killed) {
        this.proc.kill("SIGKILL");
      }
      this.killTimer = null;
    }, SIGKILL_TIMEOUT_MS);
  }

  private notify(event: AutoagentEvent): void {
    for (const cb of this.subscribers) {
      try {
        cb(event);
      } catch {
        // Don't let subscriber errors crash the manager
      }
    }
  }

  private cleanup(): void {
    if (this.killTimer) {
      clearTimeout(this.killTimer);
      this.killTimer = null;
    }
    this.rl = null;
    this.proc = null;
    this._pid = null;
  }
}

// Singleton export
export const SubprocessManager = new SubprocessManagerImpl();
