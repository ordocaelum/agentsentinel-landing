/**
 * AgentSentinel — Safety controls for AI agents
 * Copyright (c) 2026 Leland E. Doss. All rights reserved.
 * Licensed under the Business Source License 1.1
 * See LICENSE.md for details
 */
export type Decision =
  | "allowed"
  | "blocked_budget"
  | "blocked_rate_limit"
  | "blocked_security"
  | "blocked_pii"
  | "blocked_network"
  | "blocked_content"
  | "approval_required"
  | "approved"
  | "error";

/** A single recorded event from a protected tool invocation. */
export class AuditEvent {
  constructor(
    public readonly timestamp: number,
    public readonly toolName: string,
    public readonly status: string,
    public readonly cost: number,
    public readonly decision: Decision,
    public readonly metadata: Record<string, unknown> = {}
  ) {}

  /** Create an {@link AuditEvent} timestamped to now (ms since epoch). */
  static now(
    toolName: string,
    status: string,
    cost: number,
    decision: Decision,
    metadata: Record<string, unknown> = {}
  ): AuditEvent {
    return new AuditEvent(Date.now(), toolName, status, cost, decision, metadata);
  }
}

/** Interface for audit event destinations. */
export interface AuditSink {
  record(event: AuditEvent): void;
}

/** Prints every {@link AuditEvent} to *stdout*. */
export class ConsoleAuditSink implements AuditSink {
  record(event: AuditEvent): void {
    const ts = new Date(event.timestamp).toISOString();
    console.log(
      `[AgentSentinel] ${ts} | ${event.toolName.padEnd(30)} | ${event.decision.padEnd(22)} | status=${event.status.padEnd(7)} | cost=$${event.cost.toFixed(4)}`
    );
  }
}

/** Stores events in-memory — useful for testing and demos. */
export class InMemoryAuditSink implements AuditSink {
  readonly events: AuditEvent[] = [];

  record(event: AuditEvent): void {
    this.events.push(event);
  }

  clear(): void {
    this.events.length = 0;
  }
}

/** Manages one or more {@link AuditSink} instances. */
export class AuditLogger {
  private sinks: AuditSink[];

  constructor(sinks: AuditSink[] = [new ConsoleAuditSink()]) {
    this.sinks = [...sinks];
  }

  addSink(sink: AuditSink): void {
    this.sinks.push(sink);
  }

  removeSink(sink: AuditSink): void {
    const idx = this.sinks.indexOf(sink);
    if (idx !== -1) this.sinks.splice(idx, 1);
  }

  record(event: AuditEvent): void {
    for (const sink of this.sinks) sink.record(event);
  }
}
