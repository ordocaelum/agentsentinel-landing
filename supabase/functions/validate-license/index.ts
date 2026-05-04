import { serve } from "https://deno.land/std@0.220.1/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";
import { VALID_TIERS } from "../_shared/tiers.ts";
import { createRateLimiter } from "../_shared/rate-limit.ts";

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
// 20 requests per minute per IP, sliding-window counter.
// Because Deno Edge Function isolates are stateless and short-lived, this is
// best-effort per isolate.  For strict multi-instance limiting, back the
// counter with a Supabase table.
const rateLimiter = createRateLimiter({ max: 20, windowMs: 60_000 });

// POST /functions/v1/validate-license
// Body: { license_key: string }
serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  // ── Request size guard ───────────────────────────────────────────────────
  // Reject bodies larger than 1 MB before parsing to prevent OOM DoS attacks.
  const MAX_BODY_BYTES = 1024 * 1024;
  const contentLength = req.headers.get("content-length");
  if (contentLength && parseInt(contentLength, 10) > MAX_BODY_BYTES) {
    return new Response(
      JSON.stringify({ valid: false, error: "Request payload too large" }),
      { status: 413, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }

  // ── Rate limiting ────────────────────────────────────────────────────────
  const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0].trim() ?? "unknown";
  if (!rateLimiter.check(clientIp)) {
    // Log the rate-limited request (best-effort, no license key available yet).
    await supabase.from("license_validations").insert({
      license_key_hash: null,
      license_id: null,
      is_valid: false,
      validation_outcome: "rate_limited",
      validation_source: req.headers.get("x-validation-source") || "api",
      ip_address: clientIp,
      user_agent: req.headers.get("user-agent") || "unknown",
    }).then(() => {}, (err) => console.warn("Failed to log rate-limited request:", err));

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
    // Legacy format: check for a recognised `as_<valid_tier>_` prefix using
    // the canonical VALID_TIERS set (handles multi-word tiers like "pro_team").
    const isLegacyFormat = [...VALID_TIERS].some((t) =>
      license_key.startsWith(`as_${t}_`)
    );
    const isSignedFormat = license_key.startsWith("asv1_");
    if (!isLegacyFormat && !isSignedFormat) {
      return new Response(
        JSON.stringify({ valid: false, reason: "malformed", error: "Unrecognised license key format" }),
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

    // Hash the license key for safe storage in the audit log.
    // Never store the plaintext key in license_validations (see migration 007).
    const licenseKeyHash = await (async () => {
      const data = new TextEncoder().encode(license_key);
      const buf = await crypto.subtle.digest("SHA-256", data);
      return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
    })();

    // Log the validation attempt (best-effort)
    await supabase.from("license_validations").insert({
      license_key_hash: licenseKeyHash,
      license_id: license?.id || null,
      is_valid: !!license && license.status === "active",
      validation_outcome: !license ? "not_found"
        : license.status !== "active" ? "invalid"
        : (license.expires_at && new Date(license.expires_at) < new Date()) ? "expired"
        : "valid",
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
        JSON.stringify({ valid: false, reason: "expired", error: "License has expired" }),
        { status: 403, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // Strict enum check: reject licenses whose tier is not in the recognised set.
    // This guards against stale or corrupted DB records returning unexpected values.
    if (!license.tier) {
      console.error(`Missing tier in license record ${license.id}`);
      return new Response(
        JSON.stringify({ valid: false, error: "Invalid license configuration" }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }
    if (!VALID_TIERS.has(license.tier)) {
      console.error(`Unrecognised tier value "${license.tier}" in license record ${license.id}`);
      return new Response(
        JSON.stringify({ valid: false, error: "Invalid license configuration" }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
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
