// AgentSentinel — Safety controls for AI agents
// Copyright (c) 2026 Leland E. Doss. All rights reserved.
// Licensed under the Business Source License 1.1

// customer-events: POST /functions/v1/customer-events
//
// Receives batched tool-decision events from the Python / TypeScript SDK and
// stores them in agent_events.  Authentication is via the license_key field in
// the request body; the corresponding customer_dashboard row is resolved
// server-side so the customer never needs a separate dashboard credential.
//
// Rate limit: 1 000 requests / minute per license key (in-memory, best-effort).

import { serve } from "https://deno.land/std@0.220.1/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";
import { createRateLimiter } from "../_shared/rate-limit.ts";

const supabaseUrl = Deno.env.get("SUPABASE_URL") as string;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") as string;

const supabase = createClient(supabaseUrl, supabaseServiceKey);

// 1 000 req / min per license key
const rateLimiter = createRateLimiter({ max: 1000, windowMs: 60_000 });

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

interface EventPayload {
  license_key: string;
  agent_id: string;
  tool_name: string;
  status: "allowed" | "blocked" | "pending" | "expired";
  cost?: number;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: CORS_HEADERS });
  }

  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  let body: { events?: EventPayload[] } & Partial<EventPayload>;
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "Invalid JSON" }), {
      status: 400,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  // Support both a single event and a batch { events: [...] }
  const events: EventPayload[] = Array.isArray(body.events)
    ? body.events
    : [body as EventPayload];

  if (!events.length) {
    return new Response(JSON.stringify({ error: "No events provided" }), {
      status: 400,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  const licenseKey = events[0]?.license_key;
  if (!licenseKey) {
    return new Response(JSON.stringify({ error: "license_key is required" }), {
      status: 400,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  // Rate limit check (keyed on license key to prevent noisy customers from
  // flooding the DB; in-memory so it's per-isolate best-effort).
  if (!rateLimiter.check(licenseKey)) {
    return new Response(
      JSON.stringify({ error: "Rate limit exceeded. Max 1000 requests/minute per license." }),
      {
        status: 429,
        headers: { ...CORS_HEADERS, "Content-Type": "application/json", "Retry-After": "60" },
      },
    );
  }

  // Resolve the dashboard_id from the license key
  const { data: licenseRow, error: licenseErr } = await supabase
    .from("licenses")
    .select("id")
    .eq("license_key", licenseKey)
    .eq("status", "active")
    .maybeSingle();

  if (licenseErr || !licenseRow) {
    return new Response(JSON.stringify({ error: "Invalid or inactive license key" }), {
      status: 401,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  const { data: dashboardRow, error: dashErr } = await supabase
    .from("customer_dashboards")
    .select("id")
    .eq("license_id", licenseRow.id)
    .eq("status", "active")
    .maybeSingle();

  if (dashErr || !dashboardRow) {
    return new Response(JSON.stringify({ error: "No active dashboard found for this license" }), {
      status: 404,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  const VALID_STATUSES = new Set(["allowed", "blocked", "pending", "expired"]);
  const rows = events.map((ev) => ({
    dashboard_id: dashboardRow.id,
    agent_id: String(ev.agent_id || "unknown").slice(0, 255),
    tool_name: String(ev.tool_name || "unknown").slice(0, 255),
    status: VALID_STATUSES.has(ev.status) ? ev.status : "allowed",
    cost: typeof ev.cost === "number" ? ev.cost : null,
    timestamp: ev.timestamp || new Date().toISOString(),
    metadata: ev.metadata ?? null,
  }));

  const { error: insertErr } = await supabase.from("agent_events").insert(rows);

  if (insertErr) {
    console.error("Error inserting events:", insertErr);
    return new Response(JSON.stringify({ error: "Failed to store events" }), {
      status: 500,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  return new Response(
    JSON.stringify({ ok: true, stored: rows.length }),
    { status: 200, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } },
  );
});
