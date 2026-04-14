/**
 * AgentSentinel — Safety controls for AI agents
 * Copyright (c) 2026 Leland E. Doss. All rights reserved.
 * Licensed under the Business Source License 1.1
 * See LICENSE.md for details
 */
import { RateLimitExceededError } from "./errors";

/** Parsed representation of a rate-limit string. */
interface ParsedLimit {
  maxCalls: number;
  windowMs: number;
  label: string;
}

function parseLimit(limitStr: string): ParsedLimit {
  const parts = limitStr.trim().split("/");
  if (parts.length !== 2) {
    throw new Error(`Invalid rate limit format: "${limitStr}". Expected "<N>/min" or "<N>/hour".`);
  }

  const maxCalls = parseInt(parts[0].trim(), 10);
  if (isNaN(maxCalls)) {
    throw new Error(`Invalid rate limit count: "${parts[0]}"`);
  }

  const unit = parts[1].trim().toLowerCase();
  let windowMs: number;
  let label: string;

  if (["min", "minute", "minutes"].includes(unit)) {
    windowMs = 60_000;
    label = "min";
  } else if (["hour", "hours"].includes(unit)) {
    windowMs = 3_600_000;
    label = "hour";
  } else if (["sec", "second", "seconds"].includes(unit)) {
    windowMs = 1_000;
    label = "sec";
  } else {
    throw new Error(`Unknown rate limit unit: "${unit}". Use "sec", "min", or "hour".`);
  }

  return { maxCalls, windowMs, label };
}

/**
 * Per-tool sliding-window rate limiter.
 *
 * @example
 * ```ts
 * const limiter = new RateLimiter({ search_web: "10/min", "*": "100/hour" });
 * limiter.check("search_web"); // throws RateLimitExceededError if exceeded
 * ```
 */
export class RateLimiter {
  private readonly parsed: Map<string, ParsedLimit>;
  private readonly windows: Map<string, number[]> = new Map();

  constructor(limits: Record<string, string> = {}) {
    this.parsed = new Map(
      Object.entries(limits).map(([pattern, limitStr]) => [pattern, parseLimit(limitStr)])
    );
  }

  private getLimit(toolName: string): ParsedLimit | undefined {
    if (this.parsed.has(toolName)) return this.parsed.get(toolName);

    for (const [pattern, limit] of this.parsed.entries()) {
      if (pattern !== toolName && this.matchesPattern(toolName, pattern)) {
        return limit;
      }
    }

    return undefined;
  }

  private matchesPattern(name: string, pattern: string): boolean {
    if (pattern === name) return true;
    const re = new RegExp(
      "^" + pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".") + "$"
    );
    return re.test(name);
  }

  /**
   * Assert that *toolName* is within its rate limit.
   * Records the current call timestamp and throws if the window is full.
   */
  check(toolName: string): void {
    const limit = this.getLimit(toolName);
    if (!limit) return;

    const now = Date.now();
    const cutoff = now - limit.windowMs;

    if (!this.windows.has(toolName)) {
      this.windows.set(toolName, []);
    }

    const timestamps = this.windows.get(toolName)!;

    // Evict expired timestamps.
    while (timestamps.length > 0 && timestamps[0] <= cutoff) {
      timestamps.shift();
    }

    if (timestamps.length >= limit.maxCalls) {
      throw new RateLimitExceededError(
        `Rate limit exceeded for '${toolName}': ${limit.maxCalls}/${limit.label}.`,
        { toolName, limit: `${limit.maxCalls}/${limit.label}` }
      );
    }

    timestamps.push(now);
  }

  reset(toolName?: string): void {
    if (toolName === undefined) {
      this.windows.clear();
    } else {
      this.windows.delete(toolName);
    }
  }
}
