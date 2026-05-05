// AgentSentinel — Safety controls for AI agents
// Copyright (c) 2026 Leland E. Doss. All rights reserved.
// Licensed under the Business Source License 1.1

// customer-dashboard: GET /functions/v1/customer-dashboard/{license_key}
//
// Returns the customer dashboard configuration (dashboard URL, status, tier)
// for a given license key.  Used by the onboarding wizard to prefill the
// webhook_url and license_key into generated setup code.

import { serve } from "https://deno.land/std@0.220.1/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";

const supabaseUrl = Deno.env.get("SUPABASE_URL") as string;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") as string;
const DASHBOARD_BASE_URL = Deno.env.get("CUSTOMER_DASHBOARD_BASE_URL") ||
  "https://dash.agentsentinel.net";

const supabase = createClient(supabaseUrl, supabaseServiceKey);

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: CORS_HEADERS });
  }

  // Extract license key from URL path: /customer-dashboard/{license_key}
  const url = new URL(req.url);
  const pathParts = url.pathname.split("/").filter(Boolean);
  const licenseKey = pathParts[pathParts.length - 1];

  if (!licenseKey || licenseKey === "customer-dashboard") {
    return new Response(JSON.stringify({ error: "license_key path parameter required" }), {
      status: 400,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  const { data: licenseRow, error: licenseErr } = await supabase
    .from("licenses")
    .select("id, tier, status, created_at, customer_id")
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
    .select("id, dashboard_token, status, created_at, config")
    .eq("license_id", licenseRow.id)
    .maybeSingle();

  if (dashErr || !dashboardRow) {
    return new Response(JSON.stringify({ error: "No dashboard found for this license" }), {
      status: 404,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }

  const dashboardUrl =
    `${DASHBOARD_BASE_URL}/d/${licenseRow.customer_id}/${dashboardRow.dashboard_token}`;
  const webhookUrl = `${supabaseUrl}/functions/v1/customer-events`;

  return new Response(
    JSON.stringify({
      agent_id: licenseRow.customer_id,
      status: licenseRow.status,
      tier: licenseRow.tier,
      created_at: licenseRow.created_at,
      live_url: dashboardUrl,
      webhook_url: webhookUrl,
      dashboard_token: dashboardRow.dashboard_token,
      dashboard_status: dashboardRow.status,
    }),
    { status: 200, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } },
  );
});
