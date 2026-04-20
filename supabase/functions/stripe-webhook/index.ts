import { serve } from "https://deno.land/std@0.220.1/http/server.ts";
// stripe@13.11.0 is the latest version compatible with Deno's Fetch API.
// Check https://esm.sh/stripe for the latest available version.
import Stripe from "https://esm.sh/stripe@13.11.0?target=deno";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";
import { TIER_LIMITS, VALID_TIERS, tierDisplayName } from "../_shared/tiers.ts";

const stripe = new Stripe(Deno.env.get("STRIPE_SECRET_KEY") as string, {
  apiVersion: "2023-10-16",
  httpClient: Stripe.createFetchHttpClient(),
});

const supabaseUrl = Deno.env.get("SUPABASE_URL") as string;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") as string;
const supabase = createClient(supabaseUrl, supabaseServiceKey);

const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY") as string;
const LICENSE_SIGNING_SECRET = Deno.env.get("AGENTSENTINEL_LICENSE_SIGNING_SECRET") as string;

// Price ID to tier mapping — loaded from environment secrets.
// Set these as Supabase secrets:
//   supabase secrets set STRIPE_PRICE_STARTER=price_xxxxx
//   supabase secrets set STRIPE_PRICE_PRO=price_xxxxx
//   supabase secrets set STRIPE_PRICE_PRO_TEAM=price_xxxxx  (base price ID)
//   supabase secrets set STRIPE_PRICE_ENTERPRISE=price_xxxxx
// See STRIPE_SETUP.md for configuration instructions.
const PRICE_TO_TIER: Record<string, string> = {};
const priceEnvMappings = [
  { env: "STRIPE_PRICE_STARTER", tier: "starter" },
  { env: "STRIPE_PRICE_PRO", tier: "pro" },
  { env: "STRIPE_PRICE_PRO_TEAM", tier: "pro_team" },
  { env: "STRIPE_PRICE_ENTERPRISE", tier: "enterprise" },
];
for (const { env, tier } of priceEnvMappings) {
  const priceId = Deno.env.get(env);
  if (priceId) PRICE_TO_TIER[priceId] = tier;
}

// Pro Team per-seat price ID used to extract seat count from subscription events.
const PRICE_PRO_TEAM_SEAT = Deno.env.get("STRIPE_PRICE_PRO_TEAM_SEAT");

const SECONDS_PER_DAY = 86400;

// ─── Utilities ────────────────────────────────────────────────────────────────

/** Base64url encode (no padding), compatible with Python's _b64url_encode. */
function b64urlEncode(bytes: Uint8Array): string {
  const base64 = btoa(Array.from(bytes, (b) => String.fromCharCode(b)).join(""));
  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

/**
 * Escape HTML special characters in customer-supplied strings before
 * interpolating them into email HTML.  This prevents XSS / HTML injection
 * even if a customer registers with a name like <script>alert(1)</script>.
 */
function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Shared email shell — wraps the given HTML content with the standard
 * AgentSentinel header/footer so individual email builders only need to
 * provide the body content section.
 */
function buildEmailShell(title: string, subtitle: string, content: string): string {
  return `<!DOCTYPE html>
<html>
<head>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }
    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
    .header { background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%); color: white; padding: 30px; border-radius: 12px 12px 0 0; text-align: center; }
    .content { background: #f8fafc; padding: 30px; border: 1px solid #e2e8f0; }
    .footer { text-align: center; padding: 20px; color: #64748b; font-size: 14px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1 style="margin: 0;">AgentSentinel&#x2122;</h1>
      <p style="margin: 10px 0 0 0; opacity: 0.9;">${title}</p>
    </div>
    <div class="content">
      ${content}
    </div>
    <div class="footer">
      ${subtitle}
    </div>
  </div>
</body>
</html>`;
}

/** Generate an HMAC-signed license key in asv1_ format. */
async function generateLicenseKey(tier: string, validDays = 365): Promise<string> {
  if (!LICENSE_SIGNING_SECRET) {
    throw new Error(
      "AGENTSENTINEL_LICENSE_SIGNING_SECRET is not set. " +
        "Configure it with: supabase secrets set AGENTSENTINEL_LICENSE_SIGNING_SECRET=your_secret",
    );
  }

  const now = Math.floor(Date.now() / 1000);
  const nonceBytes = crypto.getRandomValues(new Uint8Array(9));
  const nonce = b64urlEncode(nonceBytes);

  const payloadJson = JSON.stringify(
    { exp: now + validDays * SECONDS_PER_DAY, iat: now, nonce, tier: tier.toLowerCase() },
    ["exp", "iat", "nonce", "tier"],
  );

  const payloadB64 = b64urlEncode(new TextEncoder().encode(payloadJson));

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

// ─── Email senders ────────────────────────────────────────────────────────────

async function sendEmail(to: string, subject: string, html: string): Promise<void> {
  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${RESEND_API_KEY}`,
    },
    body: JSON.stringify({
      from: "AgentSentinel <noreply@agentsentinel.net>",
      to: [to],
      subject,
      html,
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    console.error("Failed to send email:", error);
    throw new Error(`Failed to send email: ${error}`);
  }
}

async function sendLicenseEmail(
  email: string,
  name: string | null,
  licenseKey: string,
  tier: string,
): Promise<void> {
  const limits = TIER_LIMITS[tier] || TIER_LIMITS.starter;
  const tierDisplay = tierDisplayName(tier);
  // Escape customer-supplied fields before interpolating into HTML.
  const safeName = escapeHtml(name || "there");
  const safeLicenseKey = escapeHtml(licenseKey);
  const safeTierDisplay = escapeHtml(tierDisplay);

  const content = `
    <p>Hi ${safeName},</p>
    <p>Thank you for purchasing <strong>AgentSentinel ${safeTierDisplay}</strong>! &#x1F389;</p>
    <p>Here's your license key:</p>
    <div style="background:#1e293b;color:#fff;padding:20px;border-radius:8px;font-family:monospace;font-size:18px;text-align:center;margin:20px 0;word-break:break-all;">
      ${safeLicenseKey}
    </div>
    <div style="background:white;padding:20px;border-radius:8px;border:1px solid #e2e8f0;margin:20px 0;">
      <h3 style="margin-top:0;">&#x1F680; Get Started in 3 Steps</h3>
      <div style="margin:15px 0;padding-left:30px;position:relative;">
        <span style="position:absolute;left:0;top:0;width:24px;height:24px;background:#0ea5e9;color:white;border-radius:50%;text-align:center;font-size:14px;line-height:24px;">1</span>
        <strong>Set your license key:</strong><br>
        <code style="background:#f1f5f9;padding:2px 6px;border-radius:4px;font-family:monospace;">export AGENTSENTINEL_LICENSE_KEY=&quot;${safeLicenseKey}&quot;</code>
      </div>
      <div style="margin:15px 0;padding-left:30px;position:relative;">
        <span style="position:absolute;left:0;top:0;width:24px;height:24px;background:#0ea5e9;color:white;border-radius:50%;text-align:center;font-size:14px;line-height:24px;">2</span>
        <strong>Install the SDK:</strong><br>
        <code style="background:#f1f5f9;padding:2px 6px;border-radius:4px;font-family:monospace;">pip install agentsentinel-core</code>
        or <code style="background:#f1f5f9;padding:2px 6px;border-radius:4px;font-family:monospace;">npm install @agentsentinel/sdk</code>
      </div>
      <div style="margin:15px 0;padding-left:30px;position:relative;">
        <span style="position:absolute;left:0;top:0;width:24px;height:24px;background:#0ea5e9;color:white;border-radius:50%;text-align:center;font-size:14px;line-height:24px;">3</span>
        <strong>Follow the getting started guide:</strong><br>
        <a href="https://agentsentinel.net/getting-started.html">https://agentsentinel.net/getting-started.html</a>
      </div>
    </div>
    <div style="text-align:center;margin:30px 0;">
      <a href="https://agentsentinel.net/getting-started.html" style="display:inline-block;background:#0ea5e9;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:bold;">Get Started &#x2192;</a>
    </div>
    <div style="background:white;padding:20px;border-radius:8px;border:1px solid #e2e8f0;">
      <h3 style="margin-top:0;">&#x1F4CB; Your Plan Details</h3>
      <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #f1f5f9;"><span>Plan</span><strong>${safeTierDisplay}</strong></div>
      <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #f1f5f9;"><span>Agents</span><strong>${limits.agents === 999999 ? "Unlimited" : limits.agents}</strong></div>
      <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #f1f5f9;"><span>Events/month</span><strong>${limits.events === 999999999 ? "Unlimited" : limits.events.toLocaleString()}</strong></div>
      <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #f1f5f9;"><span>Dashboard</span><strong>&#x2705; Included</strong></div>
      <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #f1f5f9;"><span>Integrations</span><strong>&#x2705; All included</strong></div>
      <div style="display:flex;justify-content:space-between;padding:8px 0;"><span>Support</span><strong>${tier === "enterprise" ? "Dedicated" : tier === "pro_team" ? "Priority" : "Email"}</strong></div>
    </div>
    <p style="margin-top:30px;">
      <strong>Need help?</strong> Just reply to this email or contact us at
      <a href="mailto:contact@agentsentinel.net">contact@agentsentinel.net</a>
    </p>
    <p>
      <strong>&#x1F4D6; Documentation:</strong> <a href="https://agentsentinel.net/docs.html">agentsentinel.net/docs.html</a><br>
      <strong>&#x1F512; Security:</strong> <a href="https://agentsentinel.net/security.html">agentsentinel.net/security.html</a>
    </p>`;

  const footer = `
    <p>Thank you for trusting AgentSentinel to protect your AI agents!</p>
    <p>&#x2014; Leland, Founder of AgentSentinel</p>
    <p style="font-size:12px;color:#94a3b8;">Keep this email safe! Your license key is how we verify your subscription.</p>`;

  const html = buildEmailShell("Payment Successful!", footer, content);
  await sendEmail(email, `Your AgentSentinel ${tierDisplay} License Key`, html);
  console.log(`\u2705 License email sent to ${email}`);
}

async function sendProPriceChangeReminder(
  email: string,
  name: string | null,
  monthNumber: number,
  nextChargeDate: string,
): Promise<void> {
  const isLastMonth = monthNumber >= 3;
  const subject = isLastMonth
    ? "\u26A0\uFE0F Last month at $9.99 \u2014 your Pro plan renews at $49/mo next cycle"
    : "\uD83D\uDCC5 Heads up: your AgentSentinel Pro intro pricing ends next month";

  const safeName = escapeHtml(name || "there");
  const safeNextChargeDate = escapeHtml(nextChargeDate);

  const bodyMessage = isLastMonth
    ? `This is your <strong>last month at $9.99/mo</strong>. Your next charge on <strong>${safeNextChargeDate}</strong> will be <strong>$49/mo</strong> &#x2014; the standard Pro rate.`
    : `Your intro pricing of <strong>$9.99/mo</strong> ends next month. Starting <strong>${safeNextChargeDate}</strong>, your plan will renew at <strong>$49/mo</strong>.`;

  const content = `
    <p>Hi ${safeName},</p>
    <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:20px;margin:20px 0;">
      <p style="margin:0;">${bodyMessage}</p>
    </div>
    <p>No action is needed &#x2014; your subscription will continue uninterrupted. If you have any questions, reply to this email or contact us at <a href="mailto:contact@agentsentinel.net">contact@agentsentinel.net</a>.</p>
    <p>Thank you for being an AgentSentinel Pro subscriber!</p>`;

  const footer = `<p>&#x2014; Leland, Founder of AgentSentinel&#x2122;</p>`;
  const html = buildEmailShell("Pricing Update Notice", footer, content);
  await sendEmail(email, subject, html);
  console.log(`\u2705 Pro price-change reminder (month ${monthNumber}) sent to ${email}`);
}

// ─── Webhook event handlers ───────────────────────────────────────────────────

async function handleCheckoutCompleted(session: Stripe.Checkout.Session): Promise<void> {
  const customerEmail = session.customer_email || session.customer_details?.email;
  const customerName = session.customer_details?.name;
  const stripeCustomerId = session.customer as string;

  if (!customerEmail) {
    throw new Error("No customer email in session");
  }

  // ── Idempotency guard ────────────────────────────────────────────────────
  // If a license already exists for this subscription, skip creation entirely.
  // Stripe can fire checkout.session.completed more than once (retries, race
  // conditions).  The stripe_event_id check in webhook_events is a secondary
  // guard, but this one prevents duplicate licenses when the event log entry
  // has not yet been written.
  if (session.subscription) {
    const { data: existingLicense } = await supabase
      .from("licenses")
      .select("id")
      .eq("stripe_subscription_id", session.subscription as string)
      .maybeSingle();

    if (existingLicense) {
      console.warn(
        `\u26A0\uFE0F Idempotency: license already exists for subscription ${session.subscription} \u2014 skipping creation`,
      );
      return;
    }
  }

  // Get the tier from session metadata or price ID, then validate against the
  // canonical VALID_TIERS set to prevent an unrecognised value from propagating
  // into the database or email copy.
  let tier = session.metadata?.tier || "pro";
  if (session.metadata?.price_id) {
    tier = PRICE_TO_TIER[session.metadata.price_id] || tier;
  }
  if (!VALID_TIERS.has(tier)) {
    console.warn(`⚠️ Unknown tier "${tier}" in session ${session.id} — defaulting to "pro"`);
    tier = "pro";
  }

  const limits = TIER_LIMITS[tier] ?? TIER_LIMITS.pro; // defensive: tier is validated above

  // Seat count for pro_team: read directly from checkout metadata so the
  // license row is correct even if subscription.created fires after this event.
  // Phase 1.4: eliminates the race condition where seat_count was NULL until
  // the subscription.created event arrived.
  const seatCount = tier === "pro_team" && session.metadata?.seats
    ? parseInt(session.metadata.seats, 10) || null
    : null;

  // 1. Create or update customer.
  // On email conflict: only update the name, never overwrite stripe_customer_id.
  // A customer who re-purchases with a new Stripe account should have their
  // existing stripe_customer_id preserved so their original billing portal
  // access still works.
  const { data: existingCustomer } = await supabase
    .from("customers")
    .select("id, stripe_customer_id")
    .eq("email", customerEmail)
    .maybeSingle();

  let customer: { id: string };
  let customerError: unknown;

  if (existingCustomer) {
    // Customer exists — update name only, preserve stripe_customer_id.
    const result = await supabase
      .from("customers")
      .update({ name: customerName })
      .eq("id", existingCustomer.id)
      .select("id")
      .single();
    if (result.error || !result.data) {
      console.error("Error updating customer:", result.error);
      throw result.error ?? new Error("Customer update returned no data");
    }
    customer = result.data as { id: string };
    customerError = result.error;
  } else {
    // New customer — insert with all fields.
    const result = await supabase
      .from("customers")
      .insert({ email: customerEmail, name: customerName, stripe_customer_id: stripeCustomerId })
      .select("id")
      .single();
    if (result.error || !result.data) {
      console.error("Error inserting customer:", result.error);
      throw result.error ?? new Error("Customer insert returned no data");
    }
    customer = result.data as { id: string };
    customerError = result.error;
  }

  if (customerError) {
    console.error("Error creating customer:", customerError);
    throw customerError;
  }

  console.log(`\u2705 Customer created/updated: ${customerEmail}`);

  // 2. Generate license key
  const licenseKey = await generateLicenseKey(tier);

  // 3. Create license (with seat_count already set to avoid the race condition)
  const { error: licenseError } = await supabase.from("licenses").insert({
    customer_id: customer.id,
    license_key: licenseKey,
    tier,
    status: "active",
    stripe_subscription_id: session.subscription as string,
    stripe_price_id: session.metadata?.price_id || null,
    agents_limit: limits.agents,
    events_limit: limits.events,
    ...(seatCount !== null ? { seat_count: seatCount } : {}),
  });

  if (licenseError) {
    console.error("Error creating license:", licenseError);
    throw licenseError;
  }

  console.log(`\u2705 License created: ${licenseKey}`);

  // 4. Send welcome email
  await sendLicenseEmail(customerEmail, customerName ?? null, licenseKey, tier);

  console.log(`\u2705 Checkout complete for ${customerEmail} \u2014 ${tier} plan`);
}

async function handleSubscriptionDeleted(subscription: Stripe.Subscription): Promise<void> {
  // ── Idempotency guard ────────────────────────────────────────────────────
  const { data: existingLicense } = await supabase
    .from("licenses")
    .select("id, status")
    .eq("stripe_subscription_id", subscription.id)
    .maybeSingle();

  if (!existingLicense) {
    console.warn(
      `\u26A0\uFE0F Idempotency: no license found for subscription ${subscription.id} \u2014 skipping cancellation`,
    );
    return;
  }

  if (existingLicense.status === "cancelled") {
    console.warn(
      `\u26A0\uFE0F Idempotency: license already cancelled for subscription ${subscription.id} \u2014 skipping`,
    );
    return;
  }

  await supabase
    .from("licenses")
    .update({ status: "cancelled", cancelled_at: new Date().toISOString() })
    .eq("stripe_subscription_id", subscription.id);

  console.log(`\u26A0\uFE0F Subscription cancelled: ${subscription.id}`);
}

async function handlePaymentFailed(invoice: Stripe.Invoice): Promise<void> {
  const subscriptionId = invoice.subscription as string;
  if (!subscriptionId) {
    console.log("invoice.payment_failed: no subscription ID, skipping");
    return;
  }

  // Look up the license linked to this subscription.
  const { data: license } = await supabase
    .from("licenses")
    .select("id, status, tier, customers(email, name)")
    .eq("stripe_subscription_id", subscriptionId)
    .maybeSingle();

  if (!license) {
    console.warn(`\u26A0\uFE0F invoice.payment_failed: no license for subscription ${subscriptionId}`);
    return;
  }

  // Idempotency: if already suspended, nothing more to do.
  if (license.status === "suspended") {
    console.warn(`\u26A0\uFE0F Idempotency: license already suspended for subscription ${subscriptionId}`);
    return;
  }

  // Suspend the license so the customer loses access during the dunning period.
  const { error: updateError } = await supabase
    .from("licenses")
    .update({ status: "suspended" })
    .eq("id", license.id);

  if (updateError) {
    console.error("Error suspending license:", updateError);
    throw updateError;
  }

  console.log(`\u274C License suspended for subscription ${subscriptionId} due to payment failure`);

  // Notify the customer so they can update their payment method.
  const customer = license.customers as { email: string; name: string | null } | null;
  if (!customer?.email) {
    console.warn("invoice.payment_failed: no customer email found, skipping notification");
    return;
  }

  const safeName = escapeHtml(customer.name || "there");
  // Direct customers to the self-serve portal where they can update payment details.
  const portalUrl = "https://agentsentinel.net/portal.html";

  const content = `
    <p>Hi ${safeName},</p>
    <div style="background:#fff1f2;border:1px solid #fca5a5;border-radius:8px;padding:20px;margin:20px 0;">
      <p style="margin:0;color:#991b1b;font-weight:bold;">&#x26A0;&#xFE0F; Payment failed — your access has been suspended</p>
    </div>
    <p>We were unable to process your latest payment for AgentSentinel. To restore access to your license, please update your payment method via the customer portal.</p>
    <div style="text-align:center;margin:30px 0;">
      <a href="${portalUrl}" style="display:inline-block;background:#dc2626;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:bold;">Update Payment Method &#x2192;</a>
    </div>
    <p>Once your payment is processed, your license will be reactivated automatically.</p>
    <p>If you need help, reply to this email or contact us at <a href="mailto:contact@agentsentinel.net">contact@agentsentinel.net</a>.</p>`;

  const footer = `<p>&#x2014; The AgentSentinel team</p>`;
  const html = buildEmailShell("Payment Failed — Action Required", footer, content);

  try {
    await sendEmail(customer.email, "Action required: Update your AgentSentinel payment method", html);
    console.log(`\u2705 Payment-failed notification sent to ${customer.email}`);
  } catch (emailErr) {
    // Log but don't fail the webhook — the suspension already happened.
    console.error("Failed to send payment-failed email:", emailErr);
  }
}

async function handleInvoiceUpcoming(invoice: Stripe.Invoice): Promise<void> {
  const subscriptionId = invoice.subscription as string;
  if (!subscriptionId) {
    console.log("invoice.upcoming: no subscription ID, skipping");
    return;
  }

  const { data: license } = await supabase
    .from("licenses")
    .select("tier, created_at, customers(email, name)")
    .eq("stripe_subscription_id", subscriptionId)
    .single();

  if (!license || license.tier !== "pro") return;

  // Phase 3.6 fix: use UTC-normalised month comparison that is immune to
  // day-of-month edge cases (e.g. purchasing on Jan 31 and comparing in Feb).
  const createdAt = new Date(license.created_at);
  const now = new Date();
  const monthsElapsed =
    (now.getUTCFullYear() - createdAt.getUTCFullYear()) * 12 +
    (now.getUTCMonth() - createdAt.getUTCMonth());

  if (monthsElapsed === 2 || monthsElapsed === 3) {
    const customer = license.customers as { email: string; name: string | null } | null;
    if (customer?.email) {
      const nextPaymentTs = invoice.next_payment_attempt;
      const nextChargeDate = nextPaymentTs
        ? new Date(nextPaymentTs * 1000).toLocaleDateString("en-US", {
            year: "numeric",
            month: "long",
            day: "numeric",
          })
        : "your next billing date";
      await sendProPriceChangeReminder(
        customer.email,
        customer.name ?? null,
        monthsElapsed,
        nextChargeDate,
      );
    }
  }
}

async function handleSubscriptionUpdated(subscription: Stripe.Subscription): Promise<void> {
  if (!PRICE_PRO_TEAM_SEAT) return;

  const perSeatItem = subscription.items.data.find(
    (item) => item.price.id === PRICE_PRO_TEAM_SEAT,
  );

  if (!perSeatItem) return;

  const seatCount = perSeatItem.quantity ?? 0;
  const { error: seatUpdateError } = await supabase
    .from("licenses")
    .update({ seat_count: seatCount })
    .eq("stripe_subscription_id", subscription.id);

  if (seatUpdateError) {
    console.error("Error syncing seat count:", seatUpdateError);
  } else {
    console.log(
      `\u2705 Pro Team seat count synced: ${seatCount} seat(s) for subscription ${subscription.id}`,
    );
  }
}

// ─── Main webhook handler ─────────────────────────────────────────────────────

serve(async (req) => {
  const signature = req.headers.get("stripe-signature");

  if (!signature) {
    return new Response(JSON.stringify({ error: "No signature" }), { status: 400 });
  }

  // ── Request size guard ─────────────────────────────────────────────────────
  // Stripe webhook events are typically a few KB; 1 MB is a safe upper bound.
  const MAX_BODY_BYTES = 1024 * 1024;
  const contentLength = req.headers.get("content-length");
  if (contentLength && parseInt(contentLength, 10) > MAX_BODY_BYTES) {
    return new Response(JSON.stringify({ error: "Request payload too large" }), { status: 413 });
  }

  try {
    const body = await req.text();
    const webhookSecret = Deno.env.get("STRIPE_WEBHOOK_SECRET") as string;
    const event = stripe.webhooks.constructEvent(body, signature, webhookSecret);

    console.log(`\uD83D\uDCE9 Received Stripe event: ${event.type}`);

    // Log the webhook event for auditing (best-effort)
    await supabase.from("webhook_events").insert({
      stripe_event_id: event.id,
      event_type: event.type,
      payload: event.data.object,
      processed: false,
    }).then(() => {}, (err) => console.warn("Failed to log webhook event:", err));

    switch (event.type) {
      case "checkout.session.completed":
        await handleCheckoutCompleted(event.data.object as Stripe.Checkout.Session);
        break;

      case "customer.subscription.deleted":
        await handleSubscriptionDeleted(event.data.object as Stripe.Subscription);
        break;

      case "invoice.payment_failed":
        await handlePaymentFailed(event.data.object as Stripe.Invoice);
        break;

      case "invoice.payment_succeeded": {
        // Auto-reactivate a suspended license when payment goes through.
        const paidInvoice = event.data.object as Stripe.Invoice;
        const subId = paidInvoice.subscription as string;
        if (subId) {
          const { error: reactivateError } = await supabase
            .from("licenses")
            .update({ status: "active" })
            .eq("stripe_subscription_id", subId)
            .eq("status", "suspended");
          if (reactivateError) {
            console.error(`Failed to reactivate license for subscription ${subId}:`, reactivateError);
          } else {
            console.log(`\u2705 License reactivated for subscription ${subId}`);
          }
        }
        break;
      }

      case "invoice.upcoming":
        await handleInvoiceUpcoming(event.data.object as Stripe.Invoice);
        break;

      case "customer.subscription.created":
      case "customer.subscription.updated":
        await handleSubscriptionUpdated(event.data.object as Stripe.Subscription);
        break;

      default:
        console.log(`\u2139\uFE0F Unhandled event type: ${event.type}`);
    }

    // Mark webhook as processed (best-effort)
    await supabase
      .from("webhook_events")
      .update({ processed: true, processed_at: new Date().toISOString() })
      .eq("stripe_event_id", event.id)
      .then(() => {}, (err) => console.warn("Failed to update webhook event:", err));

    return new Response(JSON.stringify({ received: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    // Log the full error server-side but never expose internal details to the
    // caller — this prevents leaking stack traces, secret env var names, or
    // Stripe API internals through the webhook response body.
    console.error("Webhook error:", err);
    return new Response(
      JSON.stringify({ error: "Webhook processing failed" }),
      { status: 400 },
    );
  }
});
