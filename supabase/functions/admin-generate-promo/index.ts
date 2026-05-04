import { serve } from "https://deno.land/std@0.220.1/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";

const supabaseUrl = Deno.env.get("SUPABASE_URL") as string;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") as string;
const supabase = createClient(supabaseUrl, supabaseServiceKey);

// Admin JWT secret — must match Supabase JWT secret or a custom shared secret
// set via: supabase secrets set ADMIN_API_SECRET=your_strong_secret
const ADMIN_API_SECRET = Deno.env.get("ADMIN_API_SECRET") as string;

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

const VALID_PROMO_TYPES = new Set([
  "discount_percent",
  "discount_fixed",
  "trial_extension",
  "unlimited_trial",
]);

const VALID_TIERS = new Set(["free", "pro", "team"]);

// POST /functions/v1/admin-generate-promo
// Headers: Authorization: Bearer <ADMIN_API_SECRET>
// Body: {
//   code: string,           — required; regex ^[A-Z0-9_-]{3,20}$
//   type: 'discount_percent' | 'discount_fixed' | 'trial_extension' | 'unlimited_trial',
//   value: number,          — required for all types except unlimited_trial (defaults to 0)
//   tier?: 'free'|'pro'|'team'|null,
//   max_uses?: number | null,
//   expires_at?: ISO string | null,
//   description?: string,
//   active?: boolean        — defaults to true
// }
serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (req.method !== "POST") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  // ── Authentication ────────────────────────────────────────────────────────
  const authHeader = req.headers.get("authorization") || "";
  const token = authHeader.startsWith("Bearer ") ? authHeader.slice(7).trim() : "";

  if (!ADMIN_API_SECRET || !token || token !== ADMIN_API_SECRET) {
    return jsonResponse({ error: "Unauthorized" }, 401);
  }

  // ── Request size guard ─────────────────────────────────────────────────────
  const MAX_BODY_BYTES = 8 * 1024;
  const contentLength = req.headers.get("content-length");
  if (contentLength && parseInt(contentLength, 10) > MAX_BODY_BYTES) {
    return jsonResponse({ error: "Request payload too large" }, 413);
  }

  let body: {
    code?: string;
    type?: string;
    value?: number;
    tier?: string | null;
    max_uses?: number | null;
    expires_at?: string | null;
    description?: string;
    active?: boolean;
    created_by?: string;
  };

  try {
    body = await req.json();
  } catch {
    return jsonResponse({ error: "Invalid JSON body" }, 400);
  }

  // ── Input validation ──────────────────────────────────────────────────────
  if (!body.code || typeof body.code !== "string") {
    return jsonResponse({ error: "code is required" }, 400);
  }

  const code = body.code.trim().toUpperCase().replace(/[^A-Z0-9_\-]/g, "");
  if (!code || !/^[A-Z0-9_-]{3,20}$/.test(code)) {
    return jsonResponse({ error: "code must be 3-20 characters: letters, numbers, dash, underscore" }, 400);
  }

  if (!body.type || !VALID_PROMO_TYPES.has(body.type)) {
    return jsonResponse({
      error: `type must be one of: ${[...VALID_PROMO_TYPES].join(", ")}`,
    }, 400);
  }

  // value is optional for unlimited_trial (defaults to 0); required for all others
  let value: number;
  if (body.type === "unlimited_trial") {
    value = body.value !== undefined ? body.value : 0;
    if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
      return jsonResponse({ error: "value must be a non-negative integer" }, 400);
    }
  } else {
    if (typeof body.value !== "number" || !Number.isInteger(body.value) || body.value < 0) {
      return jsonResponse({ error: "value is required and must be a non-negative integer" }, 400);
    }
    value = body.value;
  }

  if (body.type === "discount_percent" && value > 100) {
    return jsonResponse({ error: "discount_percent value must be 0-100" }, 400);
  }

  // Validate tier if provided
  if (body.tier !== null && body.tier !== undefined && body.tier !== "") {
    if (!VALID_TIERS.has(body.tier)) {
      return jsonResponse({ error: `tier must be one of: ${[...VALID_TIERS].join(", ")}` }, 400);
    }
  }

  // Validate expires_at if provided
  if (body.expires_at !== null && body.expires_at !== undefined) {
    const expDate = new Date(body.expires_at);
    if (isNaN(expDate.getTime())) {
      return jsonResponse({ error: "expires_at must be a valid ISO 8601 date string" }, 400);
    }
    if (expDate < new Date()) {
      return jsonResponse({ error: "expires_at must be in the future" }, 400);
    }
  }

  const active = body.active !== undefined ? Boolean(body.active) : true;

  // ── Insert promo code ─────────────────────────────────────────────────────
  const { data: promo, error } = await supabase
    .from("promo_codes")
    .insert({
      code,
      type: body.type,
      value,
      description: body.description || null,
      tier: body.tier || null,
      active,
      expires_at: body.expires_at || null,
      max_uses: body.max_uses !== undefined ? body.max_uses : null,
      used_count: 0,
      created_by: body.created_by || "admin",
    })
    .select()
    .single();

  if (error) {
    if (error.code === "23505") {
      // Idempotency: return the existing row's id alongside the 409
      const { data: existing } = await supabase
        .from("promo_codes")
        .select("id, code, type, value, active, created_at")
        .eq("code", code)
        .single();
      return jsonResponse(
        { error: `Promo code "${code}" already exists`, id: existing?.id ?? null },
        409,
      );
    }
    console.error("Error creating promo code:", error);
    return jsonResponse({ error: "Failed to create promo code" }, 500);
  }

  console.log(`✅ Promo code created: ${code} (${body.type}, value=${value})`);

  return jsonResponse(promo, 201);
});
