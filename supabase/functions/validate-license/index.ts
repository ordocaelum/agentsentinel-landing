import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const supabaseUrl = Deno.env.get("SUPABASE_URL") as string;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") as string;
const supabase = createClient(supabaseUrl, supabaseServiceKey);

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const { license_key } = await req.json();

    if (!license_key) {
      return new Response(
        JSON.stringify({ valid: false, error: "No license key provided" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // Look up the license
    const { data: license, error } = await supabase
      .from("licenses")
      .select(`
        *,
        customers (
          email,
          name
        )
      `)
      .eq("license_key", license_key)
      .single();

    // Log the validation attempt
    await supabase.from("license_validations").insert({
      license_key: license_key,
      license_id: license?.id || null,
      is_valid: !!license && license.status === "active",
      validation_source: req.headers.get("x-validation-source") || "api",
      ip_address: req.headers.get("x-forwarded-for") || "unknown",
      user_agent: req.headers.get("user-agent") || "unknown",
    });

    if (error || !license) {
      return new Response(
        JSON.stringify({ valid: false, error: "Invalid license key" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    if (license.status !== "active") {
      return new Response(
        JSON.stringify({
          valid: false,
          error: `License is ${license.status}`,
          status: license.status,
        }),
        { status: 403, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // Check expiration
    if (license.expires_at && new Date(license.expires_at) < new Date()) {
      return new Response(
        JSON.stringify({ valid: false, error: "License has expired" }),
        { status: 403, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // License is valid!
    return new Response(
      JSON.stringify({
        valid: true,
        tier: license.tier,
        limits: {
          max_agents: license.agents_limit,
          max_events_per_month: license.events_limit,
        },
        features: {
          dashboard_enabled: license.tier !== "free",
          integrations_enabled: license.tier !== "free",
          multi_agent_enabled: ["team", "enterprise"].includes(license.tier),
          policy_editor: license.tier === "free"
            ? "none"
            : license.tier === "pro"
            ? "basic"
            : "full",
        },
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  } catch (err) {
    console.error("Validation error:", err);
    return new Response(
      JSON.stringify({ valid: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
});
