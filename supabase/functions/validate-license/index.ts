import { serve } from "https://deno.land/std@0.220.1/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";

const supabaseUrl = Deno.env.get("SUPABASE_URL") as string;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") as string;
const supabase = createClient(supabaseUrl, supabaseServiceKey);

// SDK calls are server-to-server and do not require CORS, but restricting the
// header to our own domain prevents browser-based abuse of this endpoint.
const corsHeaders = {
  "Access-Control-Allow-Origin": "https://agentsentinel.net",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

// ─── In-memory rate limiting ──────────────────────────────────────────────────
// 20 requests per minute per IP, implemented as a sliding-window counter.
// Because Deno Edge Function isolates are short-lived and stateless, this
// provides best-effort protection within a single isolate lifetime.
// For production-grade, multi-instance rate limiting, back this with a
// Supabase table or an external store.

const RATE_LIMIT_MAX = 20;
const RATE_LIMIT_WINDOW_MS = 60_000; // 1 minute

interface RateLimitEntry {
  timestamps: number[];
}

const rateLimitStore = new Map<string, RateLimitEntry>();

/**
 * Returns true when the caller should be allowed, false when rate-limited.
 * Prunes timestamps older than the window before checking.
 */
function checkRateLimit(ip: string): boolean {
  const now = Date.now();
  const windowStart = now - RATE_LIMIT_WINDOW_MS;

  let entry = rateLimitStore.get(ip);
  if (!entry) {
    entry = { timestamps: [] };
    rateLimitStore.set(ip, entry);
  }

  // Remove timestamps outside the sliding window.
  entry.timestamps = entry.timestamps.filter((t) => t > windowStart);

  if (entry.timestamps.length >= RATE_LIMIT_MAX) {
    return false;
  }

  entry.timestamps.push(now);
  return true;
}

// POST /functions/v1/validate-license
// Body: { license_key: string }
serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  // ── Rate limiting ────────────────────────────────────────────────────────
  const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0].trim() ?? "unknown";
  if (!checkRateLimit(clientIp)) {
    return new Response(
      JSON.stringify({ valid: false, error: "Too many requests. Please retry later." }),
      {
        status: 429,
        headers: {
          ...corsHeaders,
          "Content-Type": "application/json",
          "Retry-After": "60",
        },
      },
    );
  }

  try {
    const { license_key } = await req.json();

    if (!license_key) {
      return new Response(
        JSON.stringify({ valid: false, error: "No license key provided" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // Accept both legacy `as_<tier>_*` keys and new HMAC-signed `asv1_*` keys.
    const isLegacyFormat = /^as_(free|starter|pro|pro_team|team|enterprise)_/.test(license_key);
    const isSignedFormat = license_key.startsWith("asv1_");
    if (!isLegacyFormat && !isSignedFormat) {
      return new Response(
        JSON.stringify({ valid: false, error: "Unrecognised license key format" }),
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

    // Log the validation attempt (best-effort)
    await supabase.from("license_validations").insert({
      license_key,
      license_id: license?.id || null,
      is_valid: !!license && license.status === "active",
      validation_source: req.headers.get("x-validation-source") || "api",
      ip_address: clientIp,
      user_agent: req.headers.get("user-agent") || "unknown",
    }).then(() => {}, (err) => console.warn("Failed to log validation:", err));

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

    return new Response(
      JSON.stringify({
        valid: true,
        tier: license.tier,
        limits: {
          max_agents: license.agents_limit,
          max_events_per_month: license.events_limit,
        },
        features: {
          dashboard_enabled: true,
          integrations_enabled: license.tier !== "starter",
          multi_agent_enabled: ["pro_team", "enterprise"].includes(license.tier),
          policy_editor: ["pro_team", "enterprise"].includes(license.tier)
            ? "full"
            : ["starter", "pro"].includes(license.tier)
            ? "basic"
            : "basic",
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
