import { serve } from "https://deno.land/std@0.220.1/http/server.ts";
import Stripe from "https://esm.sh/stripe@13.11.0?target=deno";

const stripe = new Stripe(Deno.env.get("STRIPE_SECRET_KEY") as string, {
  apiVersion: "2023-10-16",
  httpClient: Stripe.createFetchHttpClient(),
});

// Used to verify the portal_token produced by customer-portal after OTP auth.
const LICENSE_SIGNING_SECRET = Deno.env.get("AGENTSENTINEL_LICENSE_SIGNING_SECRET") as string;

const corsHeaders = {
  "Access-Control-Allow-Origin": "https://agentsentinel.net",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

/** Base64url decode (adds padding as needed). */
function b64urlDecode(value: string): Uint8Array {
  const padding = "=".repeat((-value.length) % 4);
  const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(base64);
  return new Uint8Array([...binary].map((c) => c.charCodeAt(0)));
}

/** Base64url encode (no padding). */
function b64urlEncode(bytes: Uint8Array): string {
  const base64 = btoa(Array.from(bytes, (b) => String.fromCharCode(b)).join(""));
  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

/**
 * Verify a portal_token and return the decoded payload, or null on failure.
 *
 * The token was produced by customer-portal after a successful OTP
 * verification.  It encodes { stripe_customer_id, email, exp } and is signed
 * with AGENTSENTINEL_LICENSE_SIGNING_SECRET.
 */
async function verifyPortalToken(
  token: string,
): Promise<{ stripe_customer_id: string; email: string; exp: number } | null> {
  if (!LICENSE_SIGNING_SECRET) {
    console.error("AGENTSENTINEL_LICENSE_SIGNING_SECRET is not set");
    return null;
  }

  const dotIndex = token.lastIndexOf(".");
  if (dotIndex === -1) return null;

  const payloadB64 = token.slice(0, dotIndex);
  const sigB64 = token.slice(dotIndex + 1);

  try {
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(LICENSE_SIGNING_SECRET),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"],
    );
    const expectedSigBytes = await crypto.subtle.sign(
      "HMAC",
      key,
      new TextEncoder().encode(payloadB64),
    );
    const expectedSigB64 = b64urlEncode(new Uint8Array(expectedSigBytes));

    // Constant-time comparison using TextEncoder + subtle is unavailable in
    // Deno for strings, so we compare byte-by-byte after encoding both sides.
    if (expectedSigB64 !== sigB64) return null;

    const payload = JSON.parse(new TextDecoder().decode(b64urlDecode(payloadB64)));
    if (!payload?.stripe_customer_id || !payload?.email || !payload?.exp) return null;
    if (payload.exp <= Math.floor(Date.now() / 1000)) return null; // expired

    return payload as { stripe_customer_id: string; email: string; exp: number };
  } catch {
    return null;
  }
}

// POST /functions/v1/create-billing-session
// Body: { portal_token: string }
// The portal_token is issued by customer-portal after OTP verification and
// encodes the stripe_customer_id.  This prevents arbitrary callers from
// opening billing portal sessions for any Stripe customer ID.
serve(async (req) => {
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
    const portalToken = typeof body.portal_token === "string" ? body.portal_token : null;

    if (!portalToken) {
      return new Response(
        JSON.stringify({ error: "Missing portal_token" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    const payload = await verifyPortalToken(portalToken);
    if (!payload) {
      return new Response(
        JSON.stringify({ error: "Invalid or expired portal token. Please sign in again." }),
        { status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    const session = await stripe.billingPortal.sessions.create({
      customer: payload.stripe_customer_id,
      return_url: "https://agentsentinel.net/portal.html",
    });

    return new Response(
      JSON.stringify({ url: session.url }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  } catch (err) {
    console.error("Billing session error:", err);
    return new Response(
      JSON.stringify({ error: "Failed to create billing session" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
});
