/**
 * TypeScript interfaces matching the Python JSONL event schema from T01.
 *
 * Each event has an "event" discriminator field, a timestamp, and
 * event-specific payload fields.
 */

// ── Individual event types ───────────────────────────────────────────────

export interface LoopStartEvent {
  event: "loop_start";
  timestamp: string;
  goal: string;
  budget_usd: number;
  phase: string;
}

export interface IterationStartEvent {
  event: "iteration_start";
  timestamp: string;
  iteration: number;
}

export interface IterationEndEvent {
  event: "iteration_end";
  timestamp: string;
  iteration: number;
  score: number | null;
  decision: string;
  cost_usd: number;
  elapsed_ms: number;
  best_iteration_id: string | null;
  rationale: string;
  mutation_type: string;
}

export interface LoopEndEvent {
  event: "loop_end";
  timestamp: string;
  phase: string;
  total_iterations: number;
  total_cost_usd: number;
  best_iteration_id: string | null;
}

export interface ErrorEvent {
  event: "error";
  timestamp: string;
  message: string;
  iteration: number;
}

// ── Union type ───────────────────────────────────────────────────────────

export type AutoagentEvent =
  | LoopStartEvent
  | IterationStartEvent
  | IterationEndEvent
  | LoopEndEvent
  | ErrorEvent;

// ── Subprocess lifecycle states ──────────────────────────────────────────

export enum SubprocessState {
  Idle = "idle",
  Running = "running",
  Completed = "completed",
  Error = "error",
  Stopped = "stopped",
}
