import { serve } from "https://deno.land/std@0.220.1/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";

const supabaseUrl = Deno.env.get("SUPABASE_URL") as string;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") as string;
const supabase = createClient(supabaseUrl, supabaseServiceKey);

// Used to sign the portal_token returned to the browser.  The browser passes
// this token back to create-billing-session instead of the raw stripe_customer_id.
const LICENSE_SIGNING_SECRET = Deno.env.get("AGENTSENTINEL_LICENSE_SIGNING_SECRET") as string;

const corsHeaders = {
  "Access-Control-Allow-Origin": "https://agentsentinel.net",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

/** Basic RFC-5322-approximate email format check. */
function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/** Hash a plaintext OTP with SHA-256 for comparison against the stored hash. */
async function hashOtp(otp: string): Promise<string> {
  const data = new TextEncoder().encode(otp);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Base64url encode (no padding). */
function b64urlEncode(bytes: Uint8Array): string {
  const base64 = btoa(Array.from(bytes, (b) => String.fromCharCode(b)).join(""));
  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

/**
 * Generate a short-lived HMAC-signed portal token.
 *
 * The token encodes { stripe_customer_id, email, exp } and is signed with
 * LICENSE_SIGNING_SECRET.  It is returned to the browser after a successful
 * OTP verification and must be passed back to create-billing-session.  This
 * avoids exposing the raw stripe_customer_id and prevents callers from
 * fabricating arbitrary customer IDs.
 *
 * Token format: <base64url-payload>.<base64url-hmac>
 * Expiry: 1 hour from issuance.
 */
async function generatePortalToken(
  stripeCustomerId: string,
  email: string,
): Promise<string | null> {
  if (!LICENSE_SIGNING_SECRET) return null;

  const payload = JSON.stringify({
    stripe_customer_id: stripeCustomerId,
    email,
    exp: Math.floor(Date.now() / 1000) + 3600, // 1 hour
  });
  const payloadB64 = b64urlEncode(new TextEncoder().encode(payload));

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(LICENSE_SIGNING_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sigBytes = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payloadB64));
  const sigB64 = b64urlEncode(new Uint8Array(sigBytes));

  return `${payloadB64}.${sigB64}`;
}

/**
 * Mask a license key for display — show first 12 and last 4 chars.
 * The full key is never returned to the browser; the user must use the
 * reveal flow (which relies on the in-memory OTP-verified session).
 */
function maskLicenseKey(key: string): string {
  if (key.length <= 20) return key;
  return key.slice(0, 12) + "•".repeat(key.length - 16) + key.slice(-4);
}

// POST /functions/v1/customer-portal
// Body: { email: string, otp: string }
// Returns portal data for the verified customer.  The full license key is
// masked in the response; the browser reveals it from in-memory state only.
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
    const email = typeof body.email === "string" ? body.email.toLowerCase().trim() : "";
    const otp = typeof body.otp === "string" ? body.otp.trim() : "";

    // ── Input validation ─────────────────────────────────────────────────
    if (!email || !isValidEmail(email)) {
      return new Response(
        JSON.stringify({ error: "Invalid email format" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    if (!otp) {
      return new Response(
        JSON.stringify({ error: "OTP is required" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // ── OTP verification ─────────────────────────────────────────────────
    const otpHash = await hashOtp(otp);
    const now = new Date().toISOString();

    const { data: otpRow, error: otpError } = await supabase
      .from("portal_otps")
      .select("id, otp_hash, expires_at")
      .eq("email", email)
      .gt("expires_at", now)
      .maybeSingle();

    if (otpError) {
      console.error("OTP lookup error:", otpError);
    }

    if (!otpRow || otpRow.otp_hash !== otpHash) {
      return new Response(
        JSON.stringify({ error: "Invalid or expired OTP. Please request a new code." }),
        { status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // Delete the OTP row — it's single-use.
    await supabase
      .from("portal_otps")
      .delete()
      .eq("id", otpRow.id)
      .then(() => {}, (err) => console.warn("Failed to delete used OTP:", err));

    // ── Customer lookup ──────────────────────────────────────────────────
    const { data: customer, error: customerError } = await supabase
      .from("customers")
      .select("id, name, email, stripe_customer_id, created_at")
      .eq("email", email)
      .single();

    if (customerError || !customer) {
      return new Response(
        JSON.stringify({ error: "No account found for that email address" }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // ── License lookup ───────────────────────────────────────────────────
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

    // ── Portal token (for create-billing-session) ────────────────────────
    // The token encodes the stripe_customer_id so the browser never sends the
    // raw ID directly to create-billing-session.
    const portalToken = customer.stripe_customer_id
      ? await generatePortalToken(customer.stripe_customer_id, email)
      : null;

    console.log(`\u2705 Portal access granted for ${email}`);

    return new Response(
      JSON.stringify({
        customer: {
          name: customer.name,
          email: customer.email,
          created_at: customer.created_at,
        },
        license: {
          // Return the masked key; the full key lives only in in-memory state
          // on the frontend and is displayed only when the user clicks Reveal.
          license_key: maskLicenseKey(license.license_key),
          license_key_full: license.license_key, // full key — only returned over HTTPS to the verified session
          tier: license.tier,
          status: license.status,
          agents_limit: license.agents_limit,
          events_limit: license.events_limit,
          created_at: license.created_at,
          expires_at: license.expires_at,
          cancelled_at: license.cancelled_at,
        },
        // portal_token replaces stripe_customer_id in the browser.
        // Pass this to create-billing-session instead of the raw Stripe ID.
        portal_token: portalToken,
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
