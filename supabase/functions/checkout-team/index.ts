import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import Stripe from "https://esm.sh/stripe@13.0.0?target=deno";

const stripe = new Stripe(Deno.env.get("STRIPE_SECRET_KEY") as string, {
  apiVersion: "2023-10-16",
  httpClient: Stripe.createFetchHttpClient(),
});

// Pro Team price IDs — must be set as Supabase secrets:
//   supabase secrets set STRIPE_PRICE_PRO_TEAM_BASE=<base_price_id>
//   supabase secrets set STRIPE_PRICE_PRO_TEAM_SEAT=<per_seat_price_id>
// See STRIPE_SETUP.md for the price IDs and full configuration instructions.
const PRICE_PRO_TEAM_BASE = Deno.env.get("STRIPE_PRICE_PRO_TEAM_BASE");
const PRICE_PRO_TEAM_SEAT = Deno.env.get("STRIPE_PRICE_PRO_TEAM_SEAT");

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
    const seatCount = parseInt(body.seats, 10);

    if (!seatCount || seatCount < 1 || seatCount > 1000) {
      return new Response(
        JSON.stringify({ error: "Invalid seat count. Must be between 1 and 1000." }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
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

    const session = await stripe.checkout.sessions.create({
      payment_method_types: ["card"],
      mode: "subscription",
      line_items: [
        {
          // Base flat fee — always 1 unit
          price: PRICE_PRO_TEAM_BASE,
          quantity: 1,
        },
        {
          // Per-seat add-on — quantity matches customer's selection
          price: PRICE_PRO_TEAM_SEAT,
          quantity: seatCount,
        },
      ],
      metadata: {
        tier: "pro_team",
        seats: String(seatCount),
      },
      success_url: `${SITE_BASE_URL}/success.html`,
      cancel_url: `${SITE_BASE_URL}/pricing-team.html`,
    });

    console.log(`✅ Checkout session created: ${session.id}`);

    return new Response(
      JSON.stringify({ checkoutUrl: session.url }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  } catch (err) {
    console.error("Checkout session error:", err);
    return new Response(
      JSON.stringify({ error: "Failed to create checkout session" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
});
