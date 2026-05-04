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

function jsonResponse(body: unknown, status = 200, extraHeaders: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json", ...extraHeaders },
  });
}

// POST /functions/v1/validate-promo
// Body:     { code: string, tier?: string }   (also accepts legacy field name promo_code)
// Response (valid):   { valid: true, id, type, value, description }
// Response (invalid): { valid: false, reason }  — reasons: not_found | inactive | expired | exhausted | tier_mismatch
serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (req.method !== "POST") {
    return jsonResponse({ valid: false, reason: "not_found" }, 405);
  }

  // ── Request size guard ─────────────────────────────────────────────────────
  const MAX_BODY_BYTES = 8 * 1024;
  const contentLength = req.headers.get("content-length");
  if (contentLength && parseInt(contentLength, 10) > MAX_BODY_BYTES) {
    return jsonResponse({ valid: false, reason: "not_found" }, 413);
  }

  // ── Rate limiting ──────────────────────────────────────────────────────────
  const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0].trim() ?? "unknown";
  if (!checkRateLimit(clientIp)) {
    return jsonResponse(
      { valid: false, reason: "not_found" },
      429,
      { "Retry-After": "60" },
    );
  }

  let body: { code?: string; promo_code?: string; tier?: string };
  try {
    body = await req.json();
  } catch {
    return jsonResponse({ valid: false, reason: "not_found" }, 400);
  }

  // Accept both `code` (preferred) and legacy `promo_code`
  const rawCode = body.code ?? body.promo_code;
  if (!rawCode || typeof rawCode !== "string") {
    return jsonResponse({ valid: false, reason: "not_found" }, 400);
  }

  // Normalise: uppercase, trim whitespace, allow only safe chars
  const code = rawCode.trim().toUpperCase().replace(/[^A-Z0-9_\-]/g, "");
  if (!code || code.length < 3 || code.length > 20) {
    return jsonResponse({ valid: false, reason: "not_found" }, 400);
  }

  const tier = typeof body.tier === "string" ? body.tier.trim().toLowerCase() : null;

  // ── Look up promo code ─────────────────────────────────────────────────────
  const { data: promo, error } = await supabase
    .from("promo_codes")
    .select("id, type, value, description, active, expires_at, max_uses, used_count, tier")
    .eq("code", code)
    .maybeSingle();

  if (error) {
    console.error("Error looking up promo code:", error);
    return jsonResponse({ valid: false, reason: "not_found" }, 500);
  }

  if (!promo) {
    return jsonResponse({ valid: false, reason: "not_found" });
  }

  // ── Validation checks — return structured reason codes ────────────────────
  if (!promo.active) {
    return jsonResponse({ valid: false, reason: "inactive" });
  }

  if (promo.expires_at && new Date(promo.expires_at) < new Date()) {
    return jsonResponse({ valid: false, reason: "expired" });
  }

  if (promo.max_uses !== null && promo.used_count >= promo.max_uses) {
    return jsonResponse({ valid: false, reason: "exhausted" });
  }

  // Tier restriction: only check when both the promo and the caller specify a tier
  if (promo.tier && tier && promo.tier !== tier) {
    return jsonResponse({ valid: false, reason: "tier_mismatch" });
  }

  // ── Success — return only the fields needed by the client ─────────────────
  return jsonResponse({
    valid: true,
    id: promo.id,
    type: promo.type,
    value: promo.value,
    description: promo.description ?? null,
  });
});
