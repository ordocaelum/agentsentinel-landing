// AgentSentinel — Safety controls for AI agents
// Copyright (c) 2026 Leland E. Doss. All rights reserved.
// Licensed under the Business Source License 1.1

/**
 * Shared in-memory sliding-window rate limiter for Edge Functions.
 *
 * Usage:
 *   import { createRateLimiter } from "../_shared/rate-limit.ts";
 *   const limiter = createRateLimiter({ max: 20, windowMs: 60_000 });
 *   if (!limiter.check(clientIp)) { return 429; }
 *
 * Note: Because Deno Edge Function isolates are stateless and short-lived,
 * this provides best-effort protection per isolate.  For strict multi-instance
 * rate limiting, back the counter with a Supabase table.
 */

export interface RateLimiterOptions {
  /** Maximum number of requests allowed within the window. */
  max: number;
  /** Sliding-window duration in milliseconds. */
  windowMs: number;
}

export interface RateLimiter {
  /**
   * Check whether the given key is within the rate limit.
   * Returns true if the request should be allowed, false if rate-limited.
   * When allowed, the request is recorded so it counts against the window.
   */
  check(key: string): boolean;
}

interface RateLimitEntry {
  timestamps: number[];
}

/**
 * Create a new in-memory rate limiter with the given options.
 */
export function createRateLimiter(opts: RateLimiterOptions): RateLimiter {
  const store = new Map<string, RateLimitEntry>();
  const { max, windowMs } = opts;

  return {
    check(key: string): boolean {
      const now = Date.now();
      const windowStart = now - windowMs;

      let entry = store.get(key);
      if (!entry) {
        entry = { timestamps: [] };
        store.set(key, entry);
      }

      // Prune timestamps outside the sliding window.
      entry.timestamps = entry.timestamps.filter((t) => t > windowStart);

      if (entry.timestamps.length >= max) {
        return false;
      }

      entry.timestamps.push(now);
      return true;
    },
  };
}
