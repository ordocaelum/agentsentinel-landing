import { serve } from "https://deno.land/std@0.220.1/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.39.3";

const supabaseUrl = Deno.env.get("SUPABASE_URL") as string;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") as string;
const supabase = createClient(supabaseUrl, supabaseServiceKey);

const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY") as string;

const corsHeaders = {
  "Access-Control-Allow-Origin": "https://agentsentinel.net",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

// ─── OTP request rate limiting (per email) ───────────────────────────────────
// Sliding-window: max 5 OTP requests per 15 minutes per email address.
// Prevents OTP spam and brute-force via mail-provider rate limits.
//
// Note: this is in-memory, best-effort protection within a single isolate
// lifetime.  It does not persist across cold starts or scale across multiple
// function instances.  For production-grade multi-instance rate limiting, back
// this with a Supabase table or an external store (same caveat as validate-license).
const OTP_RATE_LIMIT_MAX = 5;
const OTP_RATE_LIMIT_WINDOW_MS = 15 * 60 * 1000; // 15 minutes

interface RateLimitEntry {
  timestamps: number[];
}

const otpRateLimitStore = new Map<string, RateLimitEntry>();

/**
 * Returns true when the caller should be allowed, false when rate-limited.
 * Prunes timestamps outside the sliding window before checking.
 */
function checkOtpRateLimit(email: string): boolean {
  const now = Date.now();
  const windowStart = now - OTP_RATE_LIMIT_WINDOW_MS;

  let entry = otpRateLimitStore.get(email);
  if (!entry) {
    entry = { timestamps: [] };
    otpRateLimitStore.set(email, entry);
  }

  entry.timestamps = entry.timestamps.filter((t) => t > windowStart);

  if (entry.timestamps.length >= OTP_RATE_LIMIT_MAX) {
    return false;
  }

  entry.timestamps.push(now);
  return true;
}

/** Hash a plaintext OTP with SHA-256 for safe storage. */
async function hashOtp(otp: string): Promise<string> {
  const data = new TextEncoder().encode(otp);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Basic RFC-5322-approximate email format check. */
function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// POST /functions/v1/send-portal-otp
// Body: { email: string }
// Sends a 6-digit one-time password to the given email address if a customer
// account exists for it.  Always returns 200 to avoid leaking whether the
// email is registered (timing-safe enumeration resistance).
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

    if (!email || !isValidEmail(email)) {
      return new Response(
        JSON.stringify({ error: "Invalid email format" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // ── OTP request rate limiting ─────────────────────────────────────────
    if (!checkOtpRateLimit(email)) {
      console.warn(`send-portal-otp: rate limit exceeded for ${email}`);
      return new Response(
        JSON.stringify({ error: "Too many OTP requests. Please wait 15 minutes before trying again." }),
        {
          status: 429,
          headers: {
            ...corsHeaders,
            "Content-Type": "application/json",
            "Retry-After": "900",
          },
        },
      );
    }

    // Look up the customer — existence check only (no data returned to caller).
    const { data: customer } = await supabase
      .from("customers")
      .select("id")
      .eq("email", email)
      .maybeSingle();

    // Delete any expired OTPs for this email to keep the table tidy.
    await supabase
      .from("portal_otps")
      .delete()
      .eq("email", email)
      .lt("expires_at", new Date().toISOString())
      .then(() => {}, (err) => console.warn("Failed to clean up expired OTPs:", err));

    // If no customer exists we still return 200 to prevent email enumeration.
    if (!customer) {
      console.log(`send-portal-otp: no account for ${email} — returning 200 silently`);
      return new Response(
        JSON.stringify({ message: "If an account exists, an OTP has been sent." }),
        { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // Generate a 6-digit numeric OTP using rejection sampling to avoid
    // modulo bias (CodeQL: js/biased-cryptographic-random).
    // The range 100000–999999 has 900000 values; we sample 32-bit random
    // values and reject those that would introduce bias.
    function generateOtp(): string {
      const range = 900000; // 999999 - 100000 + 1
      // 2^32 = 4294967296; max unbiased value = floor(4294967296 / range) * range - 1
      const maxUnbiased = Math.floor(4294967296 / range) * range;
      let value: number;
      do {
        value = crypto.getRandomValues(new Uint32Array(1))[0];
      } while (value >= maxUnbiased);
      return String(100000 + (value % range));
    }

    const otp = generateOtp();
    const otpHash = await hashOtp(otp);
    const expiresAt = new Date(Date.now() + 15 * 60 * 1000).toISOString(); // 15 minutes

    // Atomically replace any existing OTP for this email using upsert.
    // The previous delete+insert pattern had a race condition where two
    // concurrent requests could both insert a row, leaving two valid OTPs.
    const { error: upsertError } = await supabase.from("portal_otps").upsert(
      { email, otp_hash: otpHash, expires_at: expiresAt },
      { onConflict: "email" },
    );

    if (upsertError) {
      console.error("Failed to store OTP:", upsertError);
      return new Response(
        JSON.stringify({ error: "Failed to send OTP. Please try again." }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // Send the OTP via Resend.
    const emailHtml = `<!DOCTYPE html>
<html>
<head>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }
    .container { max-width: 500px; margin: 0 auto; padding: 20px; }
    .header { background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%); color: white; padding: 24px; border-radius: 12px 12px 0 0; text-align: center; }
    .content { background: #f8fafc; padding: 30px; border: 1px solid #e2e8f0; }
    .otp-box { background: #1e293b; color: #38bdf8; padding: 24px; border-radius: 8px; font-family: monospace; font-size: 36px; font-weight: bold; text-align: center; margin: 20px 0; letter-spacing: 0.25em; }
    .footer { text-align: center; padding: 16px; color: #64748b; font-size: 13px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1 style="margin: 0;">AgentSentinel&#x2122;</h1>
      <p style="margin: 8px 0 0 0; opacity: 0.9;">Portal Sign-In Code</p>
    </div>
    <div class="content">
      <p>Use this one-time code to access your AgentSentinel customer portal:</p>
      <div class="otp-box">${otp}</div>
      <p style="color:#64748b;font-size:14px;">This code expires in <strong>15 minutes</strong> and can only be used once.</p>
      <p style="color:#64748b;font-size:14px;">If you didn't request this, you can safely ignore this email.</p>
    </div>
    <div class="footer">
      <p>&#x2014; The AgentSentinel team</p>
    </div>
  </div>
</body>
</html>`;

    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${RESEND_API_KEY}`,
      },
      body: JSON.stringify({
        from: "AgentSentinel <noreply@agentsentinel.net>",
        to: [email],
        subject: "Your AgentSentinel portal sign-in code",
        html: emailHtml,
      }),
    });

    if (!res.ok) {
      const errText = await res.text();
      console.error("Failed to send OTP email:", errText);
      return new Response(
        JSON.stringify({ error: "Failed to send OTP email. Please try again." }),
        { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    console.log(`\u2705 OTP sent to ${email}`);
    return new Response(
      JSON.stringify({ message: "If an account exists, an OTP has been sent." }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  } catch (err) {
    console.error("send-portal-otp error:", err);
    return new Response(
      JSON.stringify({ error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
});
