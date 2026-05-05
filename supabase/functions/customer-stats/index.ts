// AgentSentinel — Safety controls for AI agents
// Copyright (c) 2026 Leland E. Doss. All rights reserved.
// Licensed under the Business Source License 1.1

// customer-stats: GET /functions/v1/customer-stats/{license_key}
//
// Returns aggregate statistics for the live dashboard:
//   total_spend, daily_budget, hourly_budget, approvals_pending, event_count,
//   agent_status (running/paused), tier, uptime_since

import { serve } from "https://deno.land/std@0.220.1/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";
import { TIER_LIMITS } from "../_shared/tiers.ts";

const supabaseUrl = Deno.env.get("SUPABASE_URL") as string;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") as string;

const supabase = createClient(supabaseUrl, supabaseServiceKey);

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: CORS_HEADERS });
  }

  const url = new URL(req.url);
  const pathParts = url.pathname.split("/").filter(Boolean);
  const licenseKey = pathParts[pathParts.length - 1];

  if (!licenseKey || licenseKey === "customer-stats") {
    return new Response(JSON.stringify({ error: "license_key path parameter required" }), {
      status: 400,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  // Resolve license → customer → dashboard
  const { data: licenseRow, error: licenseErr } = await supabase
    .from("licenses")
    .select("id, tier, status, created_at, customer_id, daily_budget, hourly_budget")
    .eq("license_key", licenseKey)
    .maybeSingle();

  if (licenseErr || !licenseRow) {
    return new Response(JSON.stringify({ error: "License not found" }), {
      status: 404,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  const { data: dashboardRow, error: dashErr } = await supabase
    .from("customer_dashboards")
    .select("id, status, created_at")
    .eq("license_id", licenseRow.id)
    .maybeSingle();

  if (dashErr || !dashboardRow) {
    return new Response(JSON.stringify({ error: "No dashboard found" }), {
      status: 404,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  // Total event count
  const { count: eventCount } = await supabase
    .from("agent_events")
    .select("id", { count: "exact", head: true })
    .eq("dashboard_id", dashboardRow.id)
    .neq("status", "dashboard_created");

  // Total spend (sum of cost column)
  const { data: spendData } = await supabase
    .from("agent_events")
    .select("cost")
    .eq("dashboard_id", dashboardRow.id)
    .not("cost", "is", null);

  const totalSpend = (spendData ?? []).reduce(
    (sum: number, row: { cost: number | null }) => sum + (row.cost ?? 0),
    0,
  );

  // Approvals pending (events with status = 'pending')
  const { count: approvalsPending } = await supabase
    .from("agent_events")
    .select("id", { count: "exact", head: true })
    .eq("dashboard_id", dashboardRow.id)
    .eq("status", "pending");

  const tierLimits = TIER_LIMITS[licenseRow.tier] ?? TIER_LIMITS["starter"];

  return new Response(
    JSON.stringify({
      total_spend: Math.round(totalSpend * 10000) / 10000,
      daily_budget: licenseRow.daily_budget ?? null,
      hourly_budget: licenseRow.hourly_budget ?? null,
      approvals_pending: approvalsPending ?? 0,
      event_count: (eventCount ?? 0),
      agent_status: dashboardRow.status === "active" ? "running" : "paused",
      tier: licenseRow.tier,
      license_status: licenseRow.status,
      uptime_since: dashboardRow.created_at,
      events_limit: tierLimits.events,
      agents_limit: tierLimits.agents,
    }),
    { status: 200, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } },
  );
});
