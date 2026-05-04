import { serve } from "https://deno.land/std@0.220.1/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";

// Pro Team price IDs — must be set as Supabase secrets:
//   supabase secrets set STRIPE_PRICE_PRO_TEAM_BASE=<base_price_id>
//   supabase secrets set STRIPE_PRICE_PRO_TEAM_SEAT=<per_seat_price_id>
// See STRIPE_SETUP.md for the price IDs and full configuration instructions.
const STRIPE_SECRET_KEY = Deno.env.get("STRIPE_SECRET_KEY");
const PRICE_PRO_TEAM_BASE = Deno.env.get("STRIPE_PRICE_PRO_TEAM_BASE");
const PRICE_PRO_TEAM_SEAT = Deno.env.get("STRIPE_PRICE_PRO_TEAM_SEAT");

const supabaseUrl = Deno.env.get("SUPABASE_URL") as string;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") as string;
const supabase = createClient(supabaseUrl, supabaseServiceKey);

// Security headers — CORS is scoped to our own origin only.
// "Access-Control-Allow-Methods" advertises that only POST and the required
// OPTIONS preflight are accepted; all other methods are rejected with 405.
const corsHeaders = {
  "Access-Control-Allow-Origin": "https://agentsentinel.net",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

// POST /functions/v1/checkout-team
// Body:     { seats: number, promo_code?: string }
// Response: { checkoutUrl: string }  — redirect customer to this Stripe Checkout URL
//
// Creates a Stripe Checkout Session (subscription mode) with two line items:
//   1. Base flat fee (qty: 1)
//   2. Per-seat add-on (qty: seats)
//
// If promo_code is provided:
//   - discount_percent / discount_fixed → Stripe Coupon applied via discounts[]
//   - trial_extension / unlimited_trial → subscription_data.trial_period_days set
//   - promo_code_id stored in metadata for the webhook to attach to the license
//
// Invoice total = base_price + (seat_price × seat_count)
// Set SITE_BASE_URL to configure success/cancel redirect URLs (default: https://agentsentinel.net).
const SITE_BASE_URL = Deno.env.get("SITE_BASE_URL") || "https://agentsentinel.net";

// ── Promo validation ──────────────────────────────────────────────────────────

/** Normalise a raw promo code string to match the stored format. */
function normalisePromoCode(raw: string): string {
  return raw.trim().toUpperCase().replace(/[^A-Z0-9_-]/g, "");
}

interface PromoRow {
  id: string;
  type: string;
  value: number;
  active: boolean;
  expires_at: string | null;
  max_uses: number | null;
  used_count: number;
  tier: string | null;
}

async function validatePromoCode(
  code: string,
  tier: string | null,
): Promise<{ valid: true; promo: PromoRow } | { valid: false; reason: string }> {
  const normalised = normalisePromoCode(code);
  if (!normalised || normalised.length < 3 || normalised.length > 20) {
    return { valid: false, reason: "not_found" };
  }

  const { data: promo, error } = await supabase
    .from("promo_codes")
    .select("id, type, value, active, expires_at, max_uses, used_count, tier")
    .eq("code", normalised)
    .maybeSingle();

  if (error || !promo) return { valid: false, reason: "not_found" };
  if (!promo.active) return { valid: false, reason: "inactive" };
  if (promo.expires_at && new Date(promo.expires_at) < new Date()) {
    return { valid: false, reason: "expired" };
  }
  if (promo.max_uses !== null && promo.used_count >= promo.max_uses) {
    return { valid: false, reason: "exhausted" };
  }
  if (promo.tier && tier && promo.tier !== tier) {
    return { valid: false, reason: "tier_mismatch" };
  }

  return { valid: true, promo };
}

/**
 * Ensure a Stripe Coupon exists for the given promo code.
 * Uses the normalised promo code as the coupon ID for idempotent create-or-reuse.
 * Returns the coupon ID on success, or throws on unexpected errors.
 */
async function getOrCreateStripeCoupon(
  promoCode: string,
  type: string,
  value: number,
  auth: string,
): Promise<string> {
  const couponId = normalisePromoCode(promoCode);

  // Try to fetch existing coupon first
  const getRes = await fetch(`https://api.stripe.com/v1/coupons/${encodeURIComponent(couponId)}`, {
    headers: { "Authorization": `Basic ${auth}` },
  });

  if (getRes.ok) {
    return couponId; // reuse existing
  }

  if (getRes.status !== 404) {
    const err = await getRes.json();
    throw new Error(`Stripe coupon lookup failed: ${err?.error?.message ?? getRes.status}`);
  }

  // Create a new coupon
  const couponData = new URLSearchParams({ "id": couponId });
  if (type === "discount_percent") {
    couponData.set("percent_off", String(value));
    couponData.set("duration", "once");
  } else {
    // discount_fixed: value is in cents
    couponData.set("amount_off", String(value));
    couponData.set("currency", "usd");
    couponData.set("duration", "once");
  }

  const createRes = await fetch("https://api.stripe.com/v1/coupons", {
    method: "POST",
    headers: {
      "Authorization": `Basic ${auth}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: couponData.toString(),
  });

  if (!createRes.ok) {
    const err = await createRes.json();
    // Handle race condition: another request may have created it between our GET and POST
    if (err?.error?.code === "resource_already_exists") {
      return couponId;
    }
    throw new Error(`Stripe coupon creation failed: ${err?.error?.message ?? createRes.status}`);
  }

  return couponId;
}

/** Trial days to assign for unlimited_trial promo type — effectively no limit. */
const UNLIMITED_TRIAL_DAYS = 36500; // 100 years

serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (req.method !== "POST") {
    return new Response(
      JSON.stringify({ error: "Method not allowed" }),
      { status: 405, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }

  try {
    // ── Request size guard ───────────────────────────────────────────────────
    const MAX_BODY_BYTES = 1024 * 1024;
    const contentLength = req.headers.get("content-length");
    if (contentLength && parseInt(contentLength, 10) > MAX_BODY_BYTES) {
      return new Response(
        JSON.stringify({ error: "Request payload too large" }),
        { status: 413, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    const body = await req.json();
    // Phase 3.3: reject non-integer values like "5abc" or "5.7" that parseInt
    // would silently accept.  Only a plain integer string or a safe integer
    // number is accepted; all other types (null, undefined, objects, floats
    // with decimal parts) are rejected immediately.
    const seatsRaw = body.seats;
    let seatCount: number;
    if (typeof seatsRaw === "number") {
      if (!Number.isInteger(seatsRaw)) {
        return new Response(
          JSON.stringify({ error: "Invalid seat count. Must be a positive integer." }),
          { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
        );
      }
      seatCount = seatsRaw;
    } else if (typeof seatsRaw === "string" && /^\d+$/.test(seatsRaw)) {
      seatCount = parseInt(seatsRaw, 10);
    } else {
      return new Response(
        JSON.stringify({ error: "Invalid seat count. Must be a positive integer." }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    if (!seatCount || seatCount < 1 || seatCount > 1000) {
      return new Response(
        JSON.stringify({ error: "Invalid seat count. Must be between 1 and 1000." }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    if (!STRIPE_SECRET_KEY) {
      console.error("STRIPE_SECRET_KEY is not set");
      return new Response(
        JSON.stringify({ error: "Checkout is not configured. Please contact support." }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    if (!PRICE_PRO_TEAM_BASE || !PRICE_PRO_TEAM_SEAT) {
      console.error("STRIPE_PRICE_PRO_TEAM_BASE or STRIPE_PRICE_PRO_TEAM_SEAT is not set");
      return new Response(
        JSON.stringify({ error: "Checkout is not configured. Please contact support." }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // ── Promo code handling ──────────────────────────────────────────────────
    const promoCodeRaw = typeof body.promo_code === "string" ? body.promo_code : null;
    let promoCodeId: string | null = null;
    let couponId: string | null = null;
    let trialPeriodDays: number | null = null;

    const auth = btoa(`${STRIPE_SECRET_KEY}:`);

    if (promoCodeRaw) {
      const result = await validatePromoCode(promoCodeRaw, "pro_team");
      if (!result.valid) {
        return new Response(
          JSON.stringify({ error: `Promo code is invalid: ${result.reason}` }),
          { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
        );
      }

      const promo = result.promo;
      promoCodeId = promo.id;

      if (promo.type === "discount_percent" || promo.type === "discount_fixed") {
        couponId = await getOrCreateStripeCoupon(
          normalisePromoCode(promoCodeRaw),
          promo.type,
          promo.value,
          auth,
        );
      } else if (promo.type === "trial_extension") {
        trialPeriodDays = promo.value;
      } else if (promo.type === "unlimited_trial") {
        // A large trial window effectively makes it an unlimited trial
        trialPeriodDays = UNLIMITED_TRIAL_DAYS;
      }

      console.log(`🎟 Promo code applied: ${promoCodeRaw} (${promo.type}, value=${promo.value})`);
    }

    console.log(`🛒 Creating checkout session for ${seatCount} seat(s)`);

    // Use raw Stripe HTTP API instead of the SDK to avoid Deno compatibility issues
    // (stripe@13.0.0 triggers "Deno.core.runMicrotasks() is not supported" errors)
    const checkoutData = new URLSearchParams({
      "payment_method_types[0]": "card",
      "line_items[0][price]": PRICE_PRO_TEAM_BASE,
      "line_items[0][quantity]": "1",
      "line_items[1][price]": PRICE_PRO_TEAM_SEAT,
      "line_items[1][quantity]": String(seatCount),
      "mode": "subscription",
      "success_url": `${SITE_BASE_URL}/success.html`,
      "cancel_url": `${SITE_BASE_URL}/pricing-team.html`,
      "metadata[tier]": "pro_team",
      "metadata[seats]": String(seatCount),
    });

    // Apply promo: discount coupon
    if (couponId) {
      checkoutData.set("discounts[0][coupon]", couponId);
    }

    // Apply promo: trial days
    if (trialPeriodDays !== null) {
      checkoutData.set("subscription_data[trial_period_days]", String(trialPeriodDays));
    }

    // Persist promo code ID for the webhook to attach to the license
    if (promoCodeId) {
      checkoutData.set("metadata[promo_code_id]", promoCodeId);
    }

    const stripeRes = await fetch("https://api.stripe.com/v1/checkout/sessions", {
      method: "POST",
      headers: {
        "Authorization": `Basic ${auth}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: checkoutData.toString(),
    });

    const session = await stripeRes.json();

    if (!stripeRes.ok) {
      console.error("Stripe API error:", session);
      // Do not forward raw Stripe error messages to the client — they may
      // contain internal price IDs or account details.
      return new Response(
        JSON.stringify({ error: "Failed to create checkout session. Please try again." }),
        { status: 502, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    console.log(`✅ Checkout session created: ${session.id}`);

    return new Response(
      JSON.stringify({ checkoutUrl: session.url }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  } catch (err) {
    console.error("Checkout session error:", err);
    return new Response(
      JSON.stringify({ error: "Failed to create checkout session. Please try again." }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
});
