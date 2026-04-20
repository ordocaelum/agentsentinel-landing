// AgentSentinel — Safety controls for AI agents
// Copyright (c) 2026 Leland E. Doss. All rights reserved.
// Licensed under the Business Source License 1.1

/**
 * Shared tier definitions used by stripe-webhook and validate-license.
 *
 * Keeping them in one place prevents the definitions from drifting between
 * functions.  Import with a relative path:
 *
 *   import { TIER_LIMITS, VALID_TIERS } from "../_shared/tiers.ts";
 *
 * The Python SDK equivalent lives in python/agentsentinel/licensing.py.
 * Keep the two in sync when adding new tiers.
 */

/** All valid tier names recognised by the system. */
export const VALID_TIERS = new Set([
  "free",
  "starter",
  "pro",
  "pro_team",
  "team",
  "enterprise",
]);

/** Per-tier hard limits enforced by Edge Functions and the SDK. */
export const TIER_LIMITS: Record<string, { agents: number; events: number }> = {
  free: { agents: 1, events: 1000 },
  starter: { agents: 1, events: 1000 },
  pro: { agents: 5, events: 50000 },
  pro_team: { agents: 5, events: 50000 },
  team: { agents: 20, events: 500000 },
  enterprise: { agents: 999999, events: 999999999 },
};

/** Human-readable tier labels for email and UI use. */
export function tierDisplayName(tier: string): string {
  switch (tier) {
    case "pro_team":
      return "Pro Team";
    case "free":
      return "Free";
    default:
      return tier.charAt(0).toUpperCase() + tier.slice(1);
  }
}
