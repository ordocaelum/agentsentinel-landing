# AgentSentinel — Operational Runbooks

Step-by-step procedures for common operational tasks.

---

## Table of Contents

1. [Monitor Promo Code Usage](#1-monitor-promo-code-usage)
2. [Handle Invalid or Suspect Licenses](#2-handle-invalid-or-suspect-licenses)
3. [Recover Failed Webhooks](#3-recover-failed-webhooks)
4. [Scale Beyond Rate Limits](#4-scale-beyond-rate-limits)
5. [Rotate Secrets](#5-rotate-secrets)
6. [GDPR Data Deletion Request](#6-gdpr-data-deletion-request)
7. [Scheduled Maintenance Checklist](#7-scheduled-maintenance-checklist)
8. [Incident Response](#8-incident-response)

---

## 1. Monitor Promo Code Usage

### Daily check (< 2 minutes)

Open the admin dashboard → Promos page. Review:
- Codes with `used_count` approaching `max_uses` — top up if needed.
- Codes expiring in the next 7 days — extend or replace.
- Codes with unexpectedly high redemption rates (possible code leak).

### Weekly SQL check

```sql
-- Usage summary for all active codes
SELECT
    code,
    type,
    value,
    used_count,
    max_uses,
    CASE
        WHEN max_uses IS NULL THEN 'unlimited'
        ELSE ROUND(used_count::numeric / max_uses * 100, 1) || '%'
    END AS utilisation,
    expires_at,
    CASE
        WHEN expires_at IS NULL THEN 'never'
        WHEN expires_at < NOW() THEN 'EXPIRED'
        WHEN expires_at < NOW() + INTERVAL '7 days' THEN 'expires soon'
        ELSE 'ok'
    END AS expiry_status
FROM promo_codes
WHERE active = TRUE
ORDER BY used_count DESC;
```

### Investigate a suspicious redemption spike

```sql
-- Licenses created with code X in the last 24 hours
SELECT l.id, l.license_key, l.tier, l.status, l.created_at,
       c.email, c.stripe_customer_id
FROM licenses l
JOIN customers c ON l.customer_id = c.id
JOIN promo_codes p ON l.promo_code_id = p.id
WHERE p.code = 'SUSPECT_CODE'
  AND l.created_at > NOW() - INTERVAL '24 hours'
ORDER BY l.created_at DESC;
```

If abuse is detected:
1. Deactivate the code immediately (admin dashboard → Promos → Edit → uncheck Active).
2. Review the list of suspicious licenses.
3. Revoke fraudulent licenses (admin dashboard → Licenses → Revoke).
4. Notify the Stripe team if payment fraud is suspected.

---

## 2. Handle Invalid or Suspect Licenses

### Revoke a single license

**Via admin dashboard:**
1. Go to Licenses page.
2. Find the license by email or license key prefix.
3. Click "Revoke".
4. The SDK will return `{valid: false, error: "License is revoked"}` immediately (no cache expiry to wait for).

**Via SQL:**
```sql
UPDATE licenses
SET status = 'revoked', updated_at = NOW()
WHERE id = 'license-uuid-here';
```

**Via Supabase REST:**
```bash
curl -X PATCH \
  "https://YOUR_PROJECT.supabase.co/rest/v1/licenses?id=eq.LICENSE_UUID" \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"status": "revoked"}'
```

### Bulk revoke licenses (e.g., after a security incident)

```sql
-- Revoke all licenses created with a specific promo code
UPDATE licenses
SET status = 'revoked', updated_at = NOW()
WHERE promo_code_id = (SELECT id FROM promo_codes WHERE code = 'COMPROMISED_CODE')
  AND status = 'active';

-- Revoke all licenses for a specific customer
UPDATE licenses
SET status = 'revoked', updated_at = NOW()
WHERE customer_id = (SELECT id FROM customers WHERE email = 'bad-actor@example.com')
  AND status = 'active';
```

### Verify revocation is effective

After revoking, test that the SDK correctly rejects the key:
```bash
curl -X POST https://YOUR_PROJECT.supabase.co/functions/v1/validate-license \
  -H "Content-Type: application/json" \
  -d '{"license_key": "asv1_the_revoked_key"}'
# Expected: {"valid": false, "error": "License is revoked", "status": "revoked"}
```

---

## 3. Recover Failed Webhooks

### Identify failed webhooks

```sql
SELECT
    stripe_event_id,
    event_type,
    error_message,
    created_at,
    metadata
FROM webhook_events
WHERE status = 'failed'
ORDER BY created_at DESC
LIMIT 20;
```

### Re-deliver from Stripe (recommended path)

1. Go to [Stripe Dashboard → Developers → Webhooks](https://dashboard.stripe.com/webhooks).
2. Select your webhook endpoint.
3. Click on the failed event.
4. Click **"Resend"**.
5. The `stripe-webhook` Edge Function will process the event again.
6. Deduplication ensures no double-processing (the `webhook_events` unique constraint on `stripe_event_id` prevents duplicate rows — the idempotent webhook handler will update the existing row's status instead of inserting a new one).

### Manually re-process a specific event

If Stripe re-delivery is not possible (e.g., the event is too old):

```bash
# Retrieve the event from Stripe API
stripe events retrieve evt_xxxxxxxxxxxxxxxx

# Manually call the webhook with the event payload
curl -X POST https://YOUR_PROJECT.supabase.co/functions/v1/stripe-webhook \
  -H "Content-Type: application/json" \
  -H "Stripe-Signature: $(stripe webhooks trigger --forward-to ...)" \
  -d @event_payload.json
```

### Mark a failed webhook as resolved (after manual fix)

```sql
UPDATE webhook_events
SET
    status = 'processed',
    error_message = 'Manually resolved by admin',
    processed_at = NOW()
WHERE stripe_event_id = 'evt_xxxxxxxxxxxxxxxx';
```

### Prevent future failures

1. Check Edge Function logs for the root cause:
   ```bash
   supabase functions logs stripe-webhook --tail
   ```
2. Common causes:
   - `STRIPE_WEBHOOK_SECRET` mismatch → regenerate and update.
   - `RESEND_API_KEY` expired → regenerate in Resend dashboard and update Supabase secrets.
   - Database error → check Supabase logs for connection issues.
3. After fixing, re-deliver all failed events from Stripe.

---

## 4. Scale Beyond Rate Limits

### validate-license (20 req/min per IP)

The current in-memory sliding-window rate limiter is per-Deno-isolate. Under heavy traffic, multiple isolates may each allow up to 20/min (the limit is best-effort, not strict global).

**Short-term (no code change):**
- Cache validation results in your SDK consumer. License status changes are infrequent (hours/days) — cache for 5 minutes.
- Use offline HMAC verification for high-frequency checks (no network call, no rate limit).

**Medium-term (requires backend change):**
- Back the rate limiter with a Supabase table (atomic counter with TTL) for strict global limiting across isolates.
- Example schema:
  ```sql
  CREATE TABLE rate_limit_counters (
    key TEXT PRIMARY KEY,        -- e.g. "validate-license:1.2.3.4"
    count INTEGER DEFAULT 0,
    window_start TIMESTAMPTZ DEFAULT NOW()
  );
  ```

**Long-term:**
- Consider Cloudflare Workers in front of the Edge Function for WAF + rate limiting at the edge.

### validate-promo (10 req/min per IP)

Same strategy as `validate-license`. Promo validation happens at checkout UI — cache the result for the duration of the checkout session (typically <10 minutes).

### OTP rate limits (3 sends + 5 verifies per 15 min)

These limits are intentionally strict for security. If legitimate users are hitting them:
- Investigate if a bot is hitting the endpoint.
- Add CAPTCHA to the portal OTP request form.
- If a specific customer is locked out, see [TROUBLESHOOTING.md § 5](TROUBLESHOOTING.md#5-otp--portal-login-issues).

---

## 5. Rotate Secrets

### When to rotate

- Suspected credential leak (check git history, Slack, error logs).
- Quarterly security review.
- Team member offboarding.

### Rotate `AGENTSENTINEL_LICENSE_SIGNING_SECRET`

⚠️ **Warning:** Rotating this secret invalidates all existing offline-verifiable `asv1_` license keys. Online validation (database lookup) will still work — only offline HMAC verification will fail until the new secret is deployed to all consumers.

1. Generate a new secret:
   ```bash
   ./scripts/generate-secrets.sh --regenerate AGENTSENTINEL_LICENSE_SIGNING_SECRET
   ```
2. Update the Supabase secret:
   ```bash
   supabase secrets set AGENTSENTINEL_LICENSE_SIGNING_SECRET=new_secret_here
   ```
3. Update the Python SDK environment variable in all deployments.
4. Notify SDK users to update their `AGENTSENTINEL_LICENSE_SIGNING_SECRET`.

### Rotate `ADMIN_API_SECRET`

1. Generate:
   ```bash
   ./scripts/generate-secrets.sh --regenerate ADMIN_API_SECRET
   ```
2. Update Supabase:
   ```bash
   supabase secrets set ADMIN_API_SECRET=new_secret_here
   ```
3. Update the admin dashboard config (re-enter in the login form).

### Rotate Stripe Webhook Secret

1. In Stripe Dashboard → Webhooks → select endpoint → "Roll secret".
2. Update in Supabase:
   ```bash
   supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_new_secret
   ```

### Rotate Resend API Key

1. Generate a new key in the [Resend dashboard](https://resend.com/api-keys).
2. Update in Supabase:
   ```bash
   supabase secrets set RESEND_API_KEY=re_new_key
   ```

---

## 6. GDPR Data Deletion Request

When a customer submits a data deletion ("right to erasure") request:

### What data exists

| Table | Data |
|---|---|
| `customers` | `email`, `name`, `stripe_customer_id` |
| `licenses` | License keys (HMAC-signed with customer data) |
| `portal_otps` | Email addresses |
| `license_validations` | Hashed license keys (not plaintext emails) |
| `admin_logs` | Any admin actions on the customer's record |

### Deletion procedure

```sql
-- 1. Find the customer
SELECT id, email FROM customers WHERE email = 'customer@example.com';

-- 2. Revoke all active licenses
UPDATE licenses SET status = 'revoked' WHERE customer_id = 'customer-uuid';

-- 3. Delete OTPs
DELETE FROM portal_otps WHERE email = 'customer@example.com';

-- 4. Anonymise customer record (preferred over deletion to preserve license audit trail)
UPDATE customers
SET
    email = 'deleted_' || id || '@gdpr.invalid',
    name = 'DELETED',
    stripe_customer_id = NULL
WHERE id = 'customer-uuid';

-- 5. Cancel Stripe subscription (if active) — do this in the Stripe Dashboard
--    or via Stripe API: stripe subscriptions cancel sub_xxxxxxxxxxxxxxxx
```

**Note:** `license_validations` contains only SHA-256 hashes of license keys, not email addresses. Hashes cannot be reversed to identify the customer. No deletion required for GDPR compliance.

**Note:** Per your data retention policy, `webhook_events` and `admin_logs` are operational records and may be retained for the audit period (typically 7 years for financial records). Review with your legal team.

---

## 7. Scheduled Maintenance Checklist

### Weekly (10 minutes)

- [ ] Review failed webhooks in admin dashboard → Webhooks page.
- [ ] Check promo code utilisation (Promos page or SQL above).
- [ ] Review license validation failures (Metrics page → validation failure rate).
- [ ] Check `admin_logs` for unexpected admin actions.

### Monthly (30 minutes)

- [ ] Run `scripts/db-integrity-check.sql` and address any non-zero results.
- [ ] Review Stripe subscription churn (cancelled + past_due licenses).
- [ ] Check Resend delivery rates (Resend dashboard → Analytics).
- [ ] Review rate limit hit rates (Supabase Edge Function logs).
- [ ] Test OTP flow end-to-end with a test account.

### Quarterly (2 hours)

- [ ] Rotate secrets (see [Section 5](#5-rotate-secrets)).
- [ ] Review and update tier limits if pricing has changed.
- [ ] Review GDPR deletion requests backlog.
- [ ] Update `.env.example` if new environment variables have been added.
- [ ] Test disaster recovery: can you restore the database from a Supabase backup?

---

## 8. Incident Response

### Severity levels

| Level | Example | Response Time | Actions |
|---|---|---|---|
| **P0 — Critical** | All webhooks failing; no licenses being issued | Immediate | Page on-call, escalate |
| **P1 — High** | Portal OTP not sending; rate limit overrun | Within 1 hour | Notify team |
| **P2 — Medium** | Admin dashboard shows wrong data | Within 4 hours | Fix in next deploy |
| **P3 — Low** | Documentation gap; cosmetic bug | Next sprint | Create issue |

### P0 response playbook

1. **Acknowledge** — post in incident channel within 5 minutes.
2. **Diagnose** — check Edge Function logs, Supabase dashboard, Stripe dashboard.
3. **Mitigate** — if webhooks failing: check `STRIPE_WEBHOOK_SECRET`; re-deliver failed events from Stripe.
4. **Communicate** — email affected customers if license delivery was delayed >1 hour.
5. **Resolve** — fix root cause; verify with integration test.
6. **Post-mortem** — document timeline, root cause, and preventive measures within 48 hours.

### Communication template for license delivery delay

```
Subject: AgentSentinel — License delivery delay (resolved)

Hi [Name],

We experienced a brief delay in license delivery on [DATE] between [TIME] and [TIME] UTC.
Your license has now been issued and should be available in your portal at agentsentinel.net/portal.

If you don't see your license, please reply to this email and we'll assist immediately.

We apologise for the inconvenience.

The AgentSentinel Team
```
