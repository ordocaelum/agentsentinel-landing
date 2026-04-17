import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const supabaseUrl = Deno.env.get("SUPABASE_URL") as string;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") as string;
const supabase = createClient(supabaseUrl, supabaseServiceKey);

const corsHeaders = {
  "Access-Control-Allow-Origin": "https://agentsentinel.net",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
};

serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (req.method !== "GET") {
    return new Response(
      JSON.stringify({ error: "Method not allowed" }),
      { status: 405, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }

  try {
    const url = new URL(req.url);
    const email = url.searchParams.get("email");

    if (!email) {
      return new Response(
        JSON.stringify({ error: "Missing email parameter" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // Look up customer by email
    const { data: customer, error: customerError } = await supabase
      .from("customers")
      .select("id, name, email, stripe_customer_id, created_at")
      .eq("email", email.toLowerCase().trim())
      .single();

    if (customerError || !customer) {
      return new Response(
        JSON.stringify({ error: "No account found for that email address" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // Look up the most recent active license for this customer
    const { data: license, error: licenseError } = await supabase
      .from("licenses")
      .select(
        "license_key, tier, status, agents_limit, events_limit, created_at, expires_at, cancelled_at",
      )
      .eq("customer_id", customer.id)
      .order("created_at", { ascending: false })
      .limit(1)
      .single();

    if (licenseError || !license) {
      return new Response(
        JSON.stringify({ error: "No license found for this account" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    return new Response(
      JSON.stringify({
        customer: {
          name: customer.name,
          email: customer.email,
          created_at: customer.created_at,
        },
        license: {
          license_key: license.license_key,
          tier: license.tier,
          status: license.status,
          agents_limit: license.agents_limit,
          events_limit: license.events_limit,
          created_at: license.created_at,
          expires_at: license.expires_at,
          cancelled_at: license.cancelled_at,
        },
        stripe_customer_id: customer.stripe_customer_id,
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  } catch (err) {
    console.error("Customer portal error:", err);
    return new Response(
      JSON.stringify({ error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
});
