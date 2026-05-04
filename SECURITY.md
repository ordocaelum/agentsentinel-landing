# Security Policy

## Reporting Vulnerabilities

Please report security vulnerabilities privately to **contact@agentsentinel.net**.
Include reproduction steps, impact, and affected versions. Do not open public issues for active vulnerabilities.

## Deployment Security Best Practices

- Run with `AGENTSENTINEL_DEV_MODE=false` in production.
- Store secrets only in environment variables (never in source control).
- Restrict dashboard/network access to trusted origins and private networks.
- Enable TLS termination in front of any public-facing API endpoint.
- Monitor logs for repeated invalid license attempts and webhook failures.

## Required Environment Variables

- `AGENTSENTINEL_LICENSE_API` — backend endpoint for license validation.
- `AGENTSENTINEL_LICENSE_SIGNING_SECRET` — HMAC secret for offline signed license verification and portal token signing.
- `STRIPE_PUBLISHABLE_KEY` — public Stripe key for frontend checkout.
- `STRIPE_SECRET_KEY` — server-side Stripe API key.
- `STRIPE_WEBHOOK_SECRET` — Stripe webhook signature verification secret.
- `RESEND_API_KEY` — Resend email API key for transactional emails and OTP delivery.
- `AGENTSENTINEL_DEV_MODE` — must be `false` in production.

## Customer Portal Authentication

The customer portal uses a two-step email OTP flow to verify customer identity:

1. The customer enters their email address.
2. The `send-portal-otp` Edge Function looks up the customer (existence check only, no data returned), generates a random 6-digit OTP, stores a SHA-256 hash in the `portal_otps` table, and sends the plaintext code via Resend.
3. The customer enters the code. The `customer-portal` Edge Function hashes the supplied code and compares it to the stored hash, checking that the row has not expired (15-minute TTL) and deletes it after one successful use.
4. On success, `customer-portal` returns portal data and a short-lived HMAC-signed `portal_token` (1-hour TTL, signed with `AGENTSENTINEL_LICENSE_SIGNING_SECRET`).
5. The `create-billing-session` Edge Function accepts the `portal_token` instead of a raw `stripe_customer_id`, verifying the token's signature and expiry before creating a Stripe Billing Portal session.

This design means:
- Email addresses are never confirmed to exist or not exist to unauthenticated callers (enumeration resistance).
- License keys are never stored in `localStorage` or returned to unauthenticated callers.
- Stripe customer IDs are never directly exposed in the browser.

## Stripe Webhook Verification

1. Configure your webhook endpoint in Stripe Dashboard.
2. Set `STRIPE_WEBHOOK_SECRET` from the endpoint signing secret.
3. Verify the `Stripe-Signature` header against the raw request payload.
4. Reject requests with invalid signatures or stale timestamps.
5. Idempotency is enforced: `checkout.session.completed` checks for an existing license with the same `stripe_subscription_id` before creating a new one; `customer.subscription.deleted` checks for an existing cancellation before re-cancelling.

## Rate Limiting on License Validation

The `validate-license` Edge Function applies a sliding-window in-memory rate limit of **20 requests per minute per IP address** (read from the `x-forwarded-for` header). Excess requests receive HTTP 429 with a `Retry-After: 60` header.

Because Supabase Edge Function isolates are stateless and short-lived, this limit is enforced per-isolate as a best-effort mechanism. For stricter multi-instance rate limiting, back the counter with a Supabase table.

## License Key Format

New license keys use the `asv1_` HMAC-signed format and can be verified offline without a network request. Legacy `as_<tier>_*` keys are still accepted by the validation endpoint.

The `AGENTSENTINEL_LICENSE_SIGNING_SECRET` must be a sufficiently long random string (at least 32 bytes of entropy). Rotate it if you suspect it has been compromised.

## HMAC Signing Algorithm

All `asv1_*` license keys are signed with **HMAC-SHA256**.

**Payload canonicalization:**

```
payload_json = JSON({
  "exp": <unix_timestamp>,
  "iat": <unix_timestamp>,
  "nonce": "<base64url_random>",
  "tier": "<tier_string>"
}, keys_sorted_alphabetically, no_spaces)
```

Keys are sorted alphabetically (`exp`, `iat`, `nonce`, `tier`) and the JSON is compact (no spaces).  This ensures byte-for-byte identical output in Python (`sort_keys=True`) and TypeScript (`JSON.stringify` with explicit replacer array).

**Signature:**

```
payload_b64 = base64url(payload_json)   # no padding
sig_b64     = base64url(HMAC-SHA256(signing_secret, payload_b64))  # no padding
key         = "asv1_" + payload_b64 + "." + sig_b64
```

The HMAC is computed over `payload_b64` (the base64url-encoded string), **not** over the raw JSON bytes.

See [`docs/license-key-format.md`](docs/license-key-format.md) for the full specification and reference implementations in both Python and TypeScript.

## Key Rotation Procedure

1. Generate a new 48-byte secret:  
   `openssl rand -base64 48`
2. Update Supabase secrets:  
   `supabase secrets set AGENTSENTINEL_LICENSE_SIGNING_SECRET=<new_secret>`
3. Update the secret in all Python SDK deployments.
4. Re-issue licenses for all active customers (existing `asv1_*` keys signed with the old secret will fail offline verification after rotation).
5. Notify affected customers to update their license keys.

> **Revocation:** Key revocation (before expiry) is handled via the `licenses.status` column in the database.  Set `status = 'revoked'` to block a specific key.  Offline verification does not check revocation — only the database lookup does.
