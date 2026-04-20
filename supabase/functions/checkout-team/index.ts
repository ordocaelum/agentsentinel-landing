import { serve } from "https://deno.land/std@0.220.1/http/server.ts";

// Pro Team price IDs — must be set as Supabase secrets:
//   supabase secrets set STRIPE_PRICE_PRO_TEAM_BASE=<base_price_id>
//   supabase secrets set STRIPE_PRICE_PRO_TEAM_SEAT=<per_seat_price_id>
// See STRIPE_SETUP.md for the price IDs and full configuration instructions.
const STRIPE_SECRET_KEY = Deno.env.get("STRIPE_SECRET_KEY");
const PRICE_PRO_TEAM_BASE = Deno.env.get("STRIPE_PRICE_PRO_TEAM_BASE");
const PRICE_PRO_TEAM_SEAT = Deno.env.get("STRIPE_PRICE_PRO_TEAM_SEAT");

// Security headers — CORS is scoped to our own origin only.
// "Access-Control-Allow-Methods" advertises that only POST and the required
// OPTIONS preflight are accepted; all other methods are rejected with 405.
const corsHeaders = {
  "Access-Control-Allow-Origin": "https://agentsentinel.net",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

// POST /functions/v1/checkout-team
// Body:     { seats: number }
// Response: { checkoutUrl: string }  — redirect customer to this Stripe Checkout URL
//
// Creates a Stripe Checkout Session (subscription mode) with two line items:
//   1. Base flat fee (qty: 1)
//   2. Per-seat add-on (qty: seats)
//
// Invoice total = base_price + (seat_price × seat_count)
// Set SITE_BASE_URL to configure success/cancel redirect URLs (default: https://agentsentinel.net).
const SITE_BASE_URL = Deno.env.get("SITE_BASE_URL") || "https://agentsentinel.net";

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

    const auth = btoa(`${STRIPE_SECRET_KEY}:`);
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
