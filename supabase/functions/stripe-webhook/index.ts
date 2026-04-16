import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import Stripe from "https://esm.sh/stripe@13.0.0?target=deno";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const stripe = new Stripe(Deno.env.get("STRIPE_SECRET_KEY") as string, {
  apiVersion: "2023-10-16",
  httpClient: Stripe.createFetchHttpClient(),
});

const supabaseUrl = Deno.env.get("SUPABASE_URL") as string;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") as string;
const supabase = createClient(supabaseUrl, supabaseServiceKey);

const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY") as string;
const LICENSE_SIGNING_SECRET = Deno.env.get("AGENTSENTINEL_LICENSE_SIGNING_SECRET") as string;

// Price ID to tier mapping
const PRICE_TO_TIER: Record<string, string> = {};

// Load price-to-tier mappings from environment
// Set these as Supabase secrets:
//   supabase secrets set STRIPE_PRICE_PRO=price_xxxxx
//   supabase secrets set STRIPE_PRICE_TEAM=price_xxxxx
//   supabase secrets set STRIPE_PRICE_ENTERPRISE=price_xxxxx
const priceEnvMappings = [
  { env: "STRIPE_PRICE_PRO", tier: "pro" },
  { env: "STRIPE_PRICE_TEAM", tier: "team" },
  { env: "STRIPE_PRICE_ENTERPRISE", tier: "enterprise" },
];
for (const { env, tier } of priceEnvMappings) {
  const priceId = Deno.env.get(env);
  if (priceId) PRICE_TO_TIER[priceId] = tier;
}

// Tier limits
const TIER_LIMITS: Record<string, { agents: number; events: number }> = {
  free: { agents: 1, events: 1000 },
  pro: { agents: 5, events: 50000 },
  team: { agents: 20, events: 500000 },
  enterprise: { agents: 999999, events: 999999999 },
};

const SECONDS_PER_DAY = 86400;

// Base64url encode (no padding), compatible with Python's _b64url_encode
function b64urlEncode(bytes: Uint8Array): string {
  const base64 = btoa(Array.from(bytes, (b) => String.fromCharCode(b)).join(""));
  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

// Generate an HMAC-signed license key in asv1_ format, compatible with
// the Python SDK's verify_license_key() in python/agentsentinel/utils/keygen.py
async function generateLicenseKey(tier: string, validDays = 365): Promise<string> {
  if (!LICENSE_SIGNING_SECRET) {
    throw new Error(
      "AGENTSENTINEL_LICENSE_SIGNING_SECRET is not set. " +
      "Configure it with: supabase secrets set AGENTSENTINEL_LICENSE_SIGNING_SECRET=your_secret",
    );
  }

  const now = Math.floor(Date.now() / 1000);
  // Generate nonce: 9 random bytes → 12 base64url chars (matches Python token_urlsafe(12) length)
  const nonceBytes = crypto.getRandomValues(new Uint8Array(9));
  const nonce = b64urlEncode(nonceBytes);

  // Build payload with alphabetically sorted keys to match Python's sort_keys=True
  // Key order: exp, iat, nonce, tier
  const payloadJson = JSON.stringify({
    exp: now + validDays * SECONDS_PER_DAY,
    iat: now,
    nonce: nonce,
    tier: tier.toLowerCase(),
  }, ["exp", "iat", "nonce", "tier"]);

  const payloadB64 = b64urlEncode(new TextEncoder().encode(payloadJson));

  // HMAC-SHA256 sign the base64url-encoded payload
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(LICENSE_SIGNING_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sigBytes = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payloadB64));
  const sigB64 = b64urlEncode(new Uint8Array(sigBytes));

  return `asv1_${payloadB64}.${sigB64}`;
}

// Send email via Resend
async function sendLicenseEmail(
  email: string,
  name: string | null,
  licenseKey: string,
  tier: string,
): Promise<void> {
  const limits = TIER_LIMITS[tier] || TIER_LIMITS.free;
  const tierDisplay = tier.charAt(0).toUpperCase() + tier.slice(1);

  const emailHtml = `
<!DOCTYPE html>
<html>
<head>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }
    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
    .header { background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%); color: white; padding: 30px; border-radius: 12px 12px 0 0; text-align: center; }
    .content { background: #f8fafc; padding: 30px; border: 1px solid #e2e8f0; }
    .license-box { background: #1e293b; color: #fff; padding: 20px; border-radius: 8px; font-family: monospace; font-size: 18px; text-align: center; margin: 20px 0; word-break: break-all; }
    .steps { background: white; padding: 20px; border-radius: 8px; border: 1px solid #e2e8f0; margin: 20px 0; }
    .step { margin: 15px 0; padding-left: 30px; position: relative; }
    .step-number { position: absolute; left: 0; top: 0; width: 24px; height: 24px; background: #0ea5e9; color: white; border-radius: 50%; text-align: center; font-size: 14px; line-height: 24px; }
    .cta-button { display: inline-block; background: #0ea5e9; color: white; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: bold; margin: 10px 0; }
    .plan-details { background: white; padding: 20px; border-radius: 8px; border: 1px solid #e2e8f0; }
    .plan-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f1f5f9; }
    .footer { text-align: center; padding: 20px; color: #64748b; font-size: 14px; }
    code { background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-family: monospace; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1 style="margin: 0;">🛡️ AgentSentinel</h1>
      <p style="margin: 10px 0 0 0; opacity: 0.9;">Payment Successful!</p>
    </div>

    <div class="content">
      <p>Hi ${name || "there"},</p>

      <p>Thank you for purchasing <strong>AgentSentinel ${tierDisplay}</strong>! 🎉</p>

      <p>Here's your license key:</p>

      <div class="license-box">
        ${licenseKey}
      </div>

      <div class="steps">
        <h3 style="margin-top: 0;">🚀 Get Started in 3 Steps</h3>

        <div class="step">
          <span class="step-number">1</span>
          <strong>Set your license key:</strong><br>
          <code>export AGENTSENTINEL_LICENSE_KEY="${licenseKey}"</code>
        </div>

        <div class="step">
          <span class="step-number">2</span>
          <strong>Install the SDK:</strong><br>
          <code>pip install agentsentinel</code> or <code>npm install @agentsentinel/sdk</code>
        </div>

        <div class="step">
          <span class="step-number">3</span>
          <strong>Follow the getting started guide:</strong><br>
          <a href="https://agentsentinel.net/getting-started.html">https://agentsentinel.net/getting-started.html</a>
        </div>
      </div>

      <div style="text-align: center; margin: 30px 0;">
        <a href="https://agentsentinel.net/getting-started.html" class="cta-button">Get Started →</a>
      </div>

      <div class="plan-details">
        <h3 style="margin-top: 0;">📋 Your Plan Details</h3>
        <div class="plan-row"><span>Plan</span><strong>${tierDisplay}</strong></div>
        <div class="plan-row"><span>Agents</span><strong>${limits.agents === 999999 ? "Unlimited" : limits.agents}</strong></div>
        <div class="plan-row"><span>Events/month</span><strong>${limits.events === 999999999 ? "Unlimited" : limits.events.toLocaleString()}</strong></div>
        <div class="plan-row"><span>Dashboard</span><strong>✅ Included</strong></div>
        <div class="plan-row"><span>Integrations</span><strong>✅ All included</strong></div>
        <div class="plan-row" style="border: none;"><span>Support</span><strong>${tier === "enterprise" ? "Dedicated" : tier === "team" ? "Priority" : "Email"}</strong></div>
      </div>

      <p style="margin-top: 30px;">
        <strong>Need help?</strong> Just reply to this email or contact us at
        <a href="mailto:contact@agentsentinel.net">contact@agentsentinel.net</a>
      </p>

      <p>
        <strong>📖 Documentation:</strong> <a href="https://agentsentinel.net/docs.html">agentsentinel.net/docs.html</a><br>
        <strong>🔒 Security:</strong> <a href="https://agentsentinel.net/security.html">agentsentinel.net/security.html</a>
      </p>
    </div>

    <div class="footer">
      <p>Thank you for trusting AgentSentinel to protect your AI agents!</p>
      <p>— Leland, Founder of AgentSentinel</p>
      <p style="font-size: 12px; color: #94a3b8;">
        Keep this email safe! Your license key is how we verify your subscription.
      </p>
    </div>
  </div>
</body>
</html>
  `;

  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${RESEND_API_KEY}`,
    },
    body: JSON.stringify({
      from: "AgentSentinel <noreply@agentsentinel.net>",
      to: [email],
      subject: `🎉 Your AgentSentinel ${tierDisplay} License Key`,
      html: emailHtml,
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    console.error("Failed to send email:", error);
    throw new Error(`Failed to send email: ${error}`);
  }

  console.log(`✅ License email sent to ${email}`);
}

// Main webhook handler
serve(async (req) => {
  const signature = req.headers.get("stripe-signature");

  if (!signature) {
    return new Response(JSON.stringify({ error: "No signature" }), {
      status: 400,
    });
  }

  try {
    const body = await req.text();
    const webhookSecret = Deno.env.get("STRIPE_WEBHOOK_SECRET") as string;

    // Verify webhook signature
    const event = stripe.webhooks.constructEvent(body, signature, webhookSecret);

    console.log(`📩 Received Stripe event: ${event.type}`);

    // Log the webhook event
    await supabase.from("webhook_events").insert({
      stripe_event_id: event.id,
      event_type: event.type,
      payload: event.data.object,
      processed: false,
    });

    // Handle checkout.session.completed
    if (event.type === "checkout.session.completed") {
      const session = event.data.object as Stripe.Checkout.Session;

      const customerEmail = session.customer_email || session.customer_details?.email;
      const customerName = session.customer_details?.name;
      const stripeCustomerId = session.customer as string;

      if (!customerEmail) {
        throw new Error("No customer email in session");
      }

      // Get the tier from metadata or price ID
      let tier = session.metadata?.tier || "pro";

      // If tier not in metadata, try to get from line items
      if (session.metadata?.price_id) {
        tier = PRICE_TO_TIER[session.metadata.price_id] || tier;
      }

      const limits = TIER_LIMITS[tier] || TIER_LIMITS.pro;

      // 1. Create or update customer
      const { data: customer, error: customerError } = await supabase
        .from("customers")
        .upsert(
          {
            email: customerEmail,
            name: customerName,
            stripe_customer_id: stripeCustomerId,
          },
          { onConflict: "email" },
        )
        .select()
        .single();

      if (customerError) {
        console.error("Error creating customer:", customerError);
        throw customerError;
      }

      console.log(`✅ Customer created/updated: ${customerEmail}`);

      // 2. Generate license key
      const licenseKey = await generateLicenseKey(tier);

      // 3. Create license
      const { error: licenseError } = await supabase.from("licenses").insert({
        customer_id: customer.id,
        license_key: licenseKey,
        tier: tier,
        status: "active",
        stripe_subscription_id: session.subscription as string,
        agents_limit: limits.agents,
        events_limit: limits.events,
      });

      if (licenseError) {
        console.error("Error creating license:", licenseError);
        throw licenseError;
      }

      console.log(`✅ License created: ${licenseKey}`);

      // 4. Send email with license key
      await sendLicenseEmail(customerEmail, customerName ?? null, licenseKey, tier);

      // 5. Mark webhook as processed
      await supabase
        .from("webhook_events")
        .update({ processed: true, processed_at: new Date().toISOString() })
        .eq("stripe_event_id", event.id);

      console.log(`✅ Checkout complete for ${customerEmail} - ${tier} plan`);
    }

    // Handle subscription cancelled
    if (event.type === "customer.subscription.deleted") {
      const subscription = event.data.object as Stripe.Subscription;

      // Mark license as cancelled
      await supabase
        .from("licenses")
        .update({
          status: "cancelled",
          cancelled_at: new Date().toISOString(),
        })
        .eq("stripe_subscription_id", subscription.id);

      console.log(`⚠️ Subscription cancelled: ${subscription.id}`);
    }

    // Handle payment failed
    if (event.type === "invoice.payment_failed") {
      const invoice = event.data.object as Stripe.Invoice;
      console.log(`❌ Payment failed for customer: ${invoice.customer}`);
      // Could send a "payment failed" email here
    }

    return new Response(JSON.stringify({ received: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    console.error("Webhook error:", err);
    return new Response(
      JSON.stringify({ error: (err as Error).message }),
      { status: 400 },
    );
  }
});
