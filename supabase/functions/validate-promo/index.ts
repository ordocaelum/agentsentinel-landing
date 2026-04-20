import { serve } from "https://deno.land/std@0.220.1/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";

const supabaseUrl = Deno.env.get("SUPABASE_URL") as string;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") as string;
const supabase = createClient(supabaseUrl, supabaseServiceKey);

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

// ─── In-memory rate limiting ──────────────────────────────────────────────────
const RATE_LIMIT_MAX = 10;
const RATE_LIMIT_WINDOW_MS = 60_000; // 1 minute

interface RateLimitEntry {
  timestamps: number[];
}

const rateLimitStore = new Map<string, RateLimitEntry>();

function checkRateLimit(ip: string): boolean {
  const now = Date.now();
  const windowStart = now - RATE_LIMIT_WINDOW_MS;

  let entry = rateLimitStore.get(ip);
  if (!entry) {
    entry = { timestamps: [] };
    rateLimitStore.set(ip, entry);
  }

  entry.timestamps = entry.timestamps.filter((t) => t > windowStart);

  if (entry.timestamps.length >= RATE_LIMIT_MAX) {
    return false;
  }

  entry.timestamps.push(now);
  return true;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

// POST /functions/v1/validate-promo
// Body:     { promo_code: string, tier?: string }
// Response: { valid: bool, discount: int, type: string, message: string, id?: string }
serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (req.method !== "POST") {
    return jsonResponse({ valid: false, message: "Method not allowed" }, 405);
  }

  // ── Request size guard ─────────────────────────────────────────────────────
  const MAX_BODY_BYTES = 8 * 1024;
  const contentLength = req.headers.get("content-length");
  if (contentLength && parseInt(contentLength, 10) > MAX_BODY_BYTES) {
    return jsonResponse({ valid: false, message: "Request payload too large" }, 413);
  }

  // ── Rate limiting ──────────────────────────────────────────────────────────
  const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0].trim() ?? "unknown";
  if (!checkRateLimit(clientIp)) {
    return jsonResponse({ valid: false, message: "Too many requests. Please retry later." }, 429);
  }

  let body: { promo_code?: string; tier?: string };
  try {
    body = await req.json();
  } catch {
    return jsonResponse({ valid: false, message: "Invalid JSON body" }, 400);
  }

  const rawCode = body.promo_code;
  if (!rawCode || typeof rawCode !== "string") {
    return jsonResponse({ valid: false, message: "promo_code is required" }, 400);
  }

  // Normalise: uppercase, trim whitespace, allow only safe chars
  const code = rawCode.trim().toUpperCase().replace(/[^A-Z0-9_\-]/g, "");
  if (!code || code.length > 64) {
    return jsonResponse({ valid: false, message: "Invalid promo code format" }, 400);
  }

  const tier = typeof body.tier === "string" ? body.tier.trim().toLowerCase() : null;

  // ── Look up promo code ─────────────────────────────────────────────────────
  const { data: promo, error } = await supabase
    .from("promo_codes")
    .select("*")
    .eq("code", code)
    .maybeSingle();

  if (error) {
    console.error("Error looking up promo code:", error);
    return jsonResponse({ valid: false, message: "Error validating promo code" }, 500);
  }

  if (!promo) {
    return jsonResponse({ valid: false, message: "Promo code not found" });
  }

  // ── Validation checks ─────────────────────────────────────────────────────
  if (!promo.active) {
    return jsonResponse({ valid: false, message: "This promo code is no longer active" });
  }

  if (promo.expires_at && new Date(promo.expires_at) < new Date()) {
    return jsonResponse({ valid: false, message: "This promo code has expired" });
  }

  if (promo.max_uses !== null && promo.used_count >= promo.max_uses) {
    return jsonResponse({ valid: false, message: "This promo code has reached its usage limit" });
  }

  // Check tier restriction
  if (promo.tier !== null && tier !== null && promo.tier !== tier) {
    return jsonResponse({
      valid: false,
      message: `This promo code is only valid for the ${promo.tier} plan`,
    });
  }

  // ── Build response message ─────────────────────────────────────────────────
  let message = "";
  switch (promo.type) {
    case "discount_percent":
      message = `${promo.value}% discount applied!`;
      break;
    case "discount_fixed":
      message = `$${(promo.value / 100).toFixed(2)} discount applied!`;
      break;
    case "trial_extension":
      message = `${promo.value} extra trial days added!`;
      break;
    case "unlimited_trial":
      message = "Unlimited trial activated!";
      break;
    default:
      message = "Promo code applied!";
  }

  if (promo.description) {
    message = promo.description;
  }

  return jsonResponse({
    valid: true,
    id: promo.id,
    code: promo.code,
    type: promo.type,
    value: promo.value,
    discount: promo.value,
    tier: promo.tier,
    message,
  });
});
