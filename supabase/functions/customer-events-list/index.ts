// AgentSentinel — Safety controls for AI agents
// Copyright (c) 2026 Leland E. Doss. All rights reserved.
// Licensed under the Business Source License 1.1

// customer-events-list: GET /functions/v1/customer-events-list/{license_key}
//   ?limit=100&offset=0&order=desc
//
// Returns paginated agent_events for the dashboard identified by the given
// license key.  Auth: license key is sufficient because it uniquely identifies
// the dashboard.

import { serve } from "https://deno.land/std@0.220.1/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";

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

  if (!licenseKey || licenseKey === "customer-events-list") {
    return new Response(JSON.stringify({ error: "license_key path parameter required" }), {
      status: 400,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  const limitParam = parseInt(url.searchParams.get("limit") || "20", 10);
  const offsetParam = parseInt(url.searchParams.get("offset") || "0", 10);
  const order = url.searchParams.get("order") === "asc" ? "asc" : "desc";

  const limit = Math.min(Math.max(1, isNaN(limitParam) ? 20 : limitParam), 100);
  const offset = Math.max(0, isNaN(offsetParam) ? 0 : offsetParam);

  // Resolve license → dashboard
  const { data: licenseRow, error: licenseErr } = await supabase
    .from("licenses")
    .select("id")
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
    .select("id")
    .eq("license_id", licenseRow.id)
    .maybeSingle();

  if (dashErr || !dashboardRow) {
    return new Response(JSON.stringify({ error: "No dashboard found for this license" }), {
      status: 404,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  const { data: events, error: eventsErr, count } = await supabase
    .from("agent_events")
    .select("*", { count: "exact" })
    .eq("dashboard_id", dashboardRow.id)
    .order("timestamp", { ascending: order === "asc" })
    .range(offset, offset + limit - 1);

  if (eventsErr) {
    console.error("Error fetching events:", eventsErr);
    return new Response(JSON.stringify({ error: "Failed to fetch events" }), {
      status: 500,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  return new Response(
    JSON.stringify({ events: events ?? [], total: count ?? 0, limit, offset }),
    { status: 200, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } },
  );
});
