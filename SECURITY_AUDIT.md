# AgentSentinel Security Audit

> **Last Updated:** 2026-04-20

This document records the security controls implemented across the AgentSentinel
platform and maps them to the OWASP Top 10 (2021 edition).

---

## OWASP Top 10 Mitigations

| # | Category | Status | Implementation |
|---|----------|--------|----------------|
| A01 | Broken Access Control | ✅ Mitigated | CORS scoped to `https://agentsentinel.net` on all Edge Functions. Stripe webhook endpoint rejects all requests without a valid `Stripe-Signature` header. Customer portal uses email OTP + short-lived HMAC-signed portal tokens — Stripe customer IDs are never exposed to the browser. |
| A02 | Cryptographic Failures | ✅ Mitigated | License keys are HMAC-SHA-256 signed (`asv1_` format). Webhook payloads are verified with `stripe.webhooks.constructEvent`. Portal tokens signed with `AGENTSENTINEL_LICENSE_SIGNING_SECRET`. All secrets stored as Supabase Edge Function secrets, never in source control. |
| A03 | Injection | ✅ Mitigated | All customer-supplied strings are HTML-escaped before interpolation into email HTML (`escapeHtml`). Seat counts are strictly validated as integers (no `parseInt` on arbitrary strings). Tier values are validated against the canonical `VALID_TIERS` set before use. Supabase client uses parameterised queries. |
| A04 | Insecure Design | ✅ Mitigated | Rate limiting on license validation (20 req/min per IP, sliding window). Idempotency guards on checkout and subscription cancellation events. UTC-normalised date comparisons for billing reminders. |
| A05 | Security Misconfiguration | ✅ Mitigated | JWT verification required for internal endpoints; disabled only for `checkout-team` (public-facing) and `validate-license`. Error responses never expose stack traces or internal error messages. `AGENTSENTINEL_DEV_MODE=false` required in production. |
| A06 | Vulnerable & Outdated Components | ✅ Mitigated | Dependabot enabled for npm (TypeScript SDK) and GitHub Actions (`.github/dependabot.yml`). `npm audit` runs on `prepublishOnly` with `--audit-level=high`. |
| A07 | Identification & Authentication Failures | ✅ Mitigated | License validation enforces strict format checks (VALID_TIERS enum, HMAC signature for `asv1_` keys). Portal OTPs are SHA-256 hashed at rest and expire after 15 minutes with single-use deletion. |
| A08 | Software & Data Integrity Failures | ✅ Mitigated | Stripe webhook signature verification prevents tampered payloads. All webhook events are logged to `webhook_events` for audit. License key generation uses `crypto.subtle` (WebCrypto). |
| A09 | Security Logging & Monitoring Failures | ✅ Mitigated | Every webhook event is persisted to `webhook_events`. License validation attempts (including failures) are logged to `license_validations`. Consistent `console.log` / `console.error` patterns throughout Edge Functions. |
| A10 | Server-Side Request Forgery (SSRF) | ✅ Mitigated | No user-supplied URLs are fetched server-side. Outbound calls are only made to fixed endpoints: `api.stripe.com`, `api.resend.com`, and the Supabase project URL (from env). |

---

## Security Headers

The following headers are set on all Edge Function responses:

| Header | Value | Purpose |
|--------|-------|---------|
| `Access-Control-Allow-Origin` | `https://agentsentinel.net` | Restrict cross-origin requests to the production domain only |
| `Access-Control-Allow-Headers` | `authorization, x-client-info, apikey, content-type` | Allowlist required request headers |
| `Access-Control-Allow-Methods` | `POST, OPTIONS` | Explicitly advertise accepted methods |
| `Content-Type` | `application/json` | Prevent MIME-type sniffing on all JSON responses |
| `Retry-After` | `60` | Included on HTTP 429 responses from `validate-license` |

Recommended additional headers for the static front-end (served via CDN):

```
Content-Security-Policy: default-src 'self'; script-src 'self' https://js.stripe.com; frame-src https://js.stripe.com; connect-src 'self' https://hjjeowbgqyabpacxqbww.supabase.co https://api.stripe.com
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

---

## Error Response Policy

All Edge Functions follow this policy:

- **Never** include raw exception messages, stack traces, or internal identifiers (e.g., Stripe price IDs) in HTTP responses.
- Server-side `console.error` logs the full error for operator investigation.
- The HTTP response body contains only a generic, user-facing message.

Example:
```typescript
// ✅ Safe
return new Response(JSON.stringify({ error: "Failed to create checkout session. Please try again." }), ...);

// ❌ Unsafe — leaks internal Stripe error details
return new Response(JSON.stringify({ error: session?.error?.message }), ...);
```

---

## Tier Validation Policy

All tier names must appear in the `VALID_TIERS` set defined in
`supabase/functions/_shared/tiers.ts` before being persisted or used for
business logic. If a tier value from an external source (Stripe metadata,
license key) is not in `VALID_TIERS`, the code defaults to `"pro"` and logs a
warning.

This prevents unrecognised tier names from propagating into the database, email
copy, or feature-flag evaluation.

---

## Incident Response Procedures

### Compromised `AGENTSENTINEL_LICENSE_SIGNING_SECRET`

1. Immediately rotate the secret:
   ```bash
   supabase secrets set AGENTSENTINEL_LICENSE_SIGNING_SECRET=<new-random-secret>
   ```
2. Redeploy all Edge Functions that import the secret.
3. Invalidate all existing `asv1_` license keys by bumping the `expires_at` on
   all active licenses to `NOW()` in the Supabase database.
4. Re-issue new license keys to affected customers via the `generate-license`
   admin endpoint or manual SQL insertion.
5. Notify affected customers by email.

### Compromised `STRIPE_WEBHOOK_SECRET`

1. Rotate the signing secret in the Stripe Dashboard → Webhooks → endpoint settings.
2. Update the secret immediately:
   ```bash
   supabase secrets set STRIPE_WEBHOOK_SECRET=<new-secret>
   ```
3. Review `webhook_events` for any suspicious replayed or tampered events in
   the window between compromise and rotation.

### Compromised `STRIPE_SECRET_KEY`

1. Roll the API key in the Stripe Dashboard → Developers → API keys.
2. Update all Supabase secrets that reference the key:
   ```bash
   supabase secrets set STRIPE_SECRET_KEY=<new-key>
   ```
3. Review Stripe event logs for unauthorised activity.
4. Notify Stripe support if fraudulent charges are suspected.

### Suspected License Key Brute-Force

1. Check `license_validations` for repeated failed lookups from a single IP.
2. Block the IP at the Supabase project level or via Cloudflare (if in use).
3. Optionally lower `RATE_LIMIT_MAX` in `validate-license/index.ts` and redeploy.

---

## Dependency Security

- **npm**: `npm audit` runs automatically on `prepublishOnly`.
  Run `npm run audit` at any time from the `typescript/` directory.
- **Dependabot**: Configured in `.github/dependabot.yml` for npm and GitHub Actions.
  Security advisories trigger PRs immediately regardless of the weekly schedule.
- **Deno**: Edge Function imports pin to explicit versions (e.g., `@0.220.1`).
  Review `esm.sh` release notes when bumping Deno std or Supabase JS versions.
