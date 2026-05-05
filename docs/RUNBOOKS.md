# AgentSentinel Operational Runbooks

> **TL;DR:** Step-by-step procedures for on-call engineers. Each runbook is self-contained — you should be able to resolve the incident without asking anyone.

---

## Table of Contents

1. [Failed Stripe Webhooks](#1-failed-stripe-webhooks)
2. [Stuck or Invalid License](#2-stuck-or-invalid-license)
3. [OTP Brute-Force Investigation](#3-otp-brute-force-investigation)
4. [Rate Limit Breach](#4-rate-limit-breach)
5. [Rotate Secrets](#5-rotate-secrets)
   - [Rotate `ADMIN_API_SECRET`](#51-rotate-admin_api_secret)
   - [Rotate `AGENTSENTINEL_LICENSE_SIGNING_SECRET`](#52-rotate-agentsentinel_license_signing_secret)
   - [Rotate Stripe Webhook Secret](#53-rotate-stripe-webhook-secret)
   - [Rotate Resend API Key](#54-rotate-resend-api-key)
6. [Database Integrity Checks](#6-database-integrity-checks)
7. [GDPR Data Deletion](#7-gdpr-data-deletion)
8. [Incident Response Playbook](#8-incident-response-playbook)

---

## 1. Failed Stripe Webhooks

**When to use:** Customer paid but no license email received; `webhook_events` shows `status = 'failed'`; Stripe dashboard shows a delivery failure.

### Diagnose

**Step 1 — Find failed webhooks:**
```sql
SELECT id, stripe_event_id, event_type, status, error_message, created_at
FROM webhook_events
WHERE status = 'failed'
ORDER BY created_at DESC
LIMIT 20;
```

**Step 2 — Check Edge Function logs:**
```bash
supabase functions logs stripe-webhook --tail
# Look for error messages in the last 50 lines
```

**Step 3 — Check Stripe Dashboard:**
1. Go to [Stripe Dashboard → Developers → Webhooks](https://dashboard.stripe.com/webhooks)
2. Select your endpoint
3. Click on the failed event
4. Read the **Response** tab for the error body

### Common root causes

| Symptom | Root cause | Fix |
|---------|-----------|-----|
| `403 Forbidden` or `401 Unauthorized` | `STRIPE_WEBHOOK_SECRET` mismatch | Re-push correct secret (see Step 4) |
| `500 Internal Server Error` | Database error or `RESEND_API_KEY` expired | Check logs, fix broken secret |
| Timeout | Edge Function execution exceeded Supabase limit | Code optimisation needed |
| `409 Conflict` from DB | Duplicate event processed twice | Inspect dedup logic; this should not happen |

**Fix `STRIPE_WEBHOOK_SECRET` mismatch:**
```bash
# Get the correct secret from Stripe Dashboard → Webhooks → your endpoint → Signing secret
supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_the_correct_secret
```

### Recover

**Option A — Re-deliver from Stripe (recommended):**
1. In Stripe Dashboard, find the failed event (by `stripe_event_id`)
2. Click **"Resend"**
3. The `stripe-webhook` Edge Function will reprocess it
4. The `INSERT … ON CONFLICT DO NOTHING` deduplication ensures it runs exactly once even if it was partially processed before

**Option B — Manual license creation (last resort — only if Stripe re-delivery fails):**
```sql
-- First, find the customer or create them
INSERT INTO customers (email, name, stripe_customer_id)
VALUES ('customer@example.com', 'Customer Name', 'cus_stripe_id_here')
ON CONFLICT (stripe_customer_id) DO NOTHING;

-- Then create the license
INSERT INTO licenses (
  customer_id, license_key, tier, status,
  agents_limit, events_limit, stripe_subscription_id
) VALUES (
  (SELECT id FROM customers WHERE email = 'customer@example.com'),
  'asv1_manually_generated_key',  -- generate with scripts/keygen
  'pro',
  'active',
  10,
  100000,
  'sub_stripe_id_here'
);
```

**Mark webhook as resolved:**
```sql
UPDATE webhook_events
SET status = 'processed', error_message = 'Manually resolved by admin on ' || NOW()::text
WHERE stripe_event_id = 'evt_xxxxxxxxxxxxxxxx';
```

### Prevent future failures

- Monitor `failed_webhooks` KPI on the admin Overview page daily
- Set up Stripe webhook failure alerts: Dashboard → Webhooks → Alert settings
- Rotate `STRIPE_WEBHOOK_SECRET` only through the safe procedure in [Section 5.3](#53-rotate-stripe-webhook-secret)

---

## 2. Stuck or Invalid License

**When to use:** License shows `active` but customer reports it's not working; license has wrong tier; license expired but subscription is still active.

### Diagnose

**Find a customer's licenses:**
```sql
SELECT
    l.id,
    l.license_key,
    l.tier,
    l.status,
    l.expires_at,
    l.stripe_subscription_id,
    l.created_at
FROM licenses l
JOIN customers c ON l.customer_id = c.id
WHERE c.email = 'customer@example.com';
```

**Check for active-but-expired licenses (should be zero):**
```sql
SELECT id, license_key, status, expires_at, NOW() - expires_at AS overdue_by
FROM licenses
WHERE expires_at < NOW() AND status = 'active';
```

**Check Stripe subscription status:**
```bash
stripe subscriptions retrieve sub_xxxxxxxxxxxxxxxx
```

### Fix active-but-expired licenses (batch)
```sql
UPDATE licenses
SET status = 'expired', updated_at = NOW()
WHERE expires_at < NOW() AND status = 'active';
```

### Fix wrong status after Stripe subscription cancelled
```sql
UPDATE licenses
SET status = 'cancelled', updated_at = NOW()
WHERE stripe_subscription_id = 'sub_xxxxxxxxxxxxxxxx'
  AND status NOT IN ('cancelled', 'revoked');
```

### Extend a license (customer service goodwill)
```sql
-- Extend by 30 days from now (or from current expiry, whichever is later)
UPDATE licenses
SET expires_at = GREATEST(expires_at, NOW()) + INTERVAL '30 days',
    updated_at = NOW()
WHERE id = 'license-uuid-here';
```

### Revoke a license
```sql
UPDATE licenses
SET status = 'revoked', updated_at = NOW()
WHERE id = 'license-uuid-here';
```

### Verify the fix
```bash
curl -X POST https://YOUR_PROJECT.supabase.co/functions/v1/validate-license \
  -H "Content-Type: application/json" \
  -d '{"license_key": "asv1_the_affected_key"}'
# Check the response — status, tier, expires_at should be correct
```

---

## 3. OTP Brute-Force Investigation

**When to use:** Suspicious spike in OTP send/verify requests; customer locked out; security alert.

### Signs of brute-force

- Many OTP send requests from a single email in a short window
- Repeated verify failures (rate limit kicking in)
- Unusual traffic pattern in Edge Function logs

### Diagnose

**Check OTP send rate for a specific email:**
```sql
SELECT
    email,
    COUNT(*) AS sends_last_hour,
    MIN(created_at) AS first_send,
    MAX(created_at) AS last_send
FROM portal_otps
WHERE email = 'suspect@example.com'
  AND created_at > NOW() - INTERVAL '1 hour'
GROUP BY email;
```

**Check overall OTP send volume:**
```sql
SELECT
    email,
    COUNT(*) AS sends,
    MIN(created_at) AS first,
    MAX(created_at) AS last
FROM portal_otps
WHERE created_at > NOW() - INTERVAL '15 minutes'
GROUP BY email
ORDER BY sends DESC
LIMIT 20;
```

**Check verify failures (exhausted rate limit = locked out):**
```sql
SELECT
    email,
    COUNT(*) AS failed_attempts
FROM portal_otps
WHERE verified = FALSE
  AND created_at > NOW() - INTERVAL '15 minutes'
GROUP BY email
HAVING COUNT(*) >= 5
ORDER BY failed_attempts DESC;
```

**View Edge Function logs:**
```bash
supabase functions logs send-portal-otp --tail
supabase functions logs customer-portal --tail
```

### Respond

**Temporary IP block (requires Supabase Edge Function or Cloudflare WAF rule):**

If a specific IP is sending abuse volume, add a Cloudflare WAF rule to block it, or update the `send-portal-otp` function to check an IP blocklist.

**Clear rate limit for a locked-out legitimate customer:**
```sql
-- Delete recent pending OTPs so customer can request a new one
DELETE FROM portal_otps
WHERE email = 'customer@example.com'
  AND verified = FALSE
  AND created_at > NOW() - INTERVAL '15 minutes';
```

**Invalidate all OTPs for a suspected victim account:**
```sql
-- Expire all unverified OTPs for an account under attack
UPDATE portal_otps
SET expires_at = NOW()
WHERE email = 'victim@example.com'
  AND verified = FALSE;
```

### Rate limits (current configuration)

| Endpoint | Limit | Window |
|----------|-------|--------|
| `send-portal-otp` | 3 sends | Per email, 15 min |
| `customer-portal` (verify) | 5 failures | Per email, 15 min |

---

## 4. Rate Limit Breach

**When to use:** `validate-license` or `validate-promo` returning 429; SDK throwing `LicenseError: Too many requests`.

### Current limits

| Endpoint | Limit | Window | Scope |
|----------|-------|--------|-------|
| `validate-license` | 20 req/min | Sliding window | Per IP |
| `validate-promo` | 10 req/min | Sliding window | Per IP |

### Short-term response (no code change required)

**For SDK consumers hitting validate-license:**

Tell the SDK consumer to switch to offline HMAC verification:
```python
# Python SDK — offline mode, no network call, no rate limit
sentinel = AgentSentinel(
    license_key="asv1_…",
    offline=True,
)
```

This requires `AGENTSENTINEL_LICENSE_SIGNING_SECRET` to be set in the consumer's environment (must match the server-side secret).

**Cache validation results:**

License status changes are rare (hours/days). Cache the result in your application:
```python
import time

_cache = {}

def validate_with_cache(license_key: str, ttl_seconds: int = 300) -> dict:
    now = time.time()
    if license_key in _cache:
        result, ts = _cache[license_key]
        if now - ts < ttl_seconds:
            return result
    result = sentinel.validate()
    _cache[license_key] = (result, now)
    return result
```

**For validate-promo at checkout:**

Cache the promo validation for the duration of the checkout session (the customer isn't going to change their promo code mid-checkout):
```javascript
// Cache per code per tier for the checkout session lifetime
const promoCache = new Map();

async function validatePromo(code, tier) {
  const key = `${code}:${tier}`;
  if (promoCache.has(key)) return promoCache.get(key);
  const result = await callValidatePromo(code, tier);
  promoCache.set(key, result);
  return result;
}
```

### Medium-term (if sustained high traffic)

The current in-memory rate limiter is per-Deno-isolate. Under high traffic, Supabase may spin up multiple isolates, each with their own counter, resulting in an effective rate higher than the configured limit.

For strict global rate limiting, add a database-backed counter:

```sql
-- Create rate limit counter table
CREATE TABLE IF NOT EXISTS rate_limit_counters (
    key TEXT PRIMARY KEY,
    count INTEGER DEFAULT 0,
    window_start TIMESTAMPTZ DEFAULT NOW()
);
```

This requires updating the Edge Function to use the DB for rate limit checks.

---

## 5. Rotate Secrets

### When to rotate

- Suspected credential leak (check git history with `git log -p | grep ADMIN_API_SECRET`)
- Team member offboarding
- Quarterly security review
- Any secret appeared in logs, Slack, or error messages

### 5.1 Rotate `ADMIN_API_SECRET`

**Zero-downtime strategy:** Deploy the new value to Supabase first, then update the admin dashboard session.

1. **Generate a new secret:**
   ```bash
   openssl rand -hex 32
   # Copy the output
   ```

2. **Update Supabase (Edge Functions pick up new secrets on cold-start — ~60 seconds):**
   ```bash
   supabase secrets set ADMIN_API_SECRET=your_new_secret_here
   ```

3. **Update your local `.env`:**
   ```bash
   # Edit .env and update ADMIN_API_SECRET=
   # Or use the setup script:
   ./scripts/setup-env.sh --regenerate ADMIN_API_SECRET
   ```

4. **Update CI/CD secrets** (GitHub Actions, etc.) with the new value.

5. **Log out of the admin dashboard** and log back in — the new secret will be required for all admin API calls.

6. **Verify:**
   ```bash
   agentsentinel-config-check
   # ADMIN_API_SECRET should show ✅
   ```

---

### 5.2 Rotate `AGENTSENTINEL_LICENSE_SIGNING_SECRET`

> ⚠️ **Warning:** This invalidates all existing `asv1_`-prefixed (HMAC-signed) license keys for **offline verification**. Online validation via the database still works. SDK consumers using offline mode will fail until they receive the new secret.

**Plan this rotation carefully — coordinate with all SDK consumers.**

1. **Generate a new secret:**
   ```bash
   openssl rand -hex 32
   ```

2. **Notify SDK consumers** that offline verification will briefly fail while the secret propagates.

3. **Update Supabase:**
   ```bash
   supabase secrets set AGENTSENTINEL_LICENSE_SIGNING_SECRET=new_secret_here
   ```

4. **Update your local `.env` and all consumer environments:**
   ```bash
   ./scripts/setup-env.sh --regenerate AGENTSENTINEL_LICENSE_SIGNING_SECRET
   ```

5. **Re-deploy Edge Functions** to pick up the new secret:
   ```bash
   supabase functions deploy
   ```

6. **Update Python SDK deployments** (set `AGENTSENTINEL_LICENSE_SIGNING_SECRET` in production environments).

7. **Verify cross-platform parity:**
   ```bash
   cd python && python -m pytest tests/test_licensing_parity.py -v
   ```

---

### 5.3 Rotate Stripe Webhook Secret

1. In [Stripe Dashboard → Developers → Webhooks](https://dashboard.stripe.com/webhooks):
   - Select your webhook endpoint
   - Click **"Roll secret"**
   - Copy the new `whsec_…` value

2. **Update Supabase immediately** (before Stripe stops accepting the old secret — you have ~24 hours):
   ```bash
   supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_new_secret_here
   ```

3. **Test with a manual Stripe event:**
   ```bash
   stripe events retrieve evt_any_recent_event_id | \
     curl -X POST https://YOUR_PROJECT.supabase.co/functions/v1/stripe-webhook \
       -H "Content-Type: application/json" \
       --data-binary @-
   ```

---

### 5.4 Rotate Resend API Key

1. In [Resend dashboard → API Keys](https://resend.com/api-keys):
   - Create a new API key
   - Copy the `re_…` value
   - Delete the old key (after updating Supabase)

2. **Update Supabase:**
   ```bash
   supabase secrets set RESEND_API_KEY=re_new_key_here
   ```

3. **Test email delivery:**
   ```bash
   # Trigger an OTP send to verify Resend is working
   curl -X POST https://YOUR_PROJECT.supabase.co/functions/v1/send-portal-otp \
     -H "Content-Type: application/json" \
     -d '{"email": "your-test@example.com"}'
   # Expected: 200 OK (or rate-limited 429 if sent recently)
   ```

---

## 6. Database Integrity Checks

Run these queries regularly to catch data inconsistencies before they become customer-facing issues.

### Full integrity check script

```bash
# Run the included integrity check script
psql "$DATABASE_URL" -f scripts/db-integrity-check.sql

# Or via Supabase CLI
supabase db execute --file scripts/db-integrity-check.sql
```

### Manual queries

**1. Orphaned `promo_code_id` references:**
```sql
-- Licenses referencing a deleted promo code
SELECT l.id, l.license_key, l.promo_code_id
FROM licenses l
LEFT JOIN promo_codes p ON l.promo_code_id = p.id
WHERE l.promo_code_id IS NOT NULL
  AND p.id IS NULL;
-- Expected: 0 rows
```

**2. Active licenses past their expiry:**
```sql
SELECT id, license_key, status, expires_at, NOW() - expires_at AS overdue_by
FROM licenses
WHERE expires_at < NOW() AND status = 'active';
-- Expected: 0 rows
-- Fix: UPDATE licenses SET status='expired' WHERE expires_at < NOW() AND status='active';
```

**3. Over-redeemed promo codes:**
```sql
SELECT code, used_count, max_uses, used_count - max_uses AS over_by
FROM promo_codes
WHERE max_uses IS NOT NULL
  AND used_count > max_uses;
-- Expected: 0 rows
-- Fix: UPDATE promo_codes SET used_count = max_uses WHERE used_count > max_uses AND max_uses IS NOT NULL;
```

**4. Invalid tier values:**
```sql
SELECT id, license_key, tier
FROM licenses
WHERE tier NOT IN ('free', 'starter', 'pro', 'pro_team', 'team', 'enterprise');
-- Expected: 0 rows
```

**5. Licenses without customers:**
```sql
SELECT l.id, l.license_key
FROM licenses l
LEFT JOIN customers c ON l.customer_id = c.id
WHERE c.id IS NULL;
-- Expected: 0 rows
```

**6. Stuck pending webhooks (>1 hour old):**
```sql
SELECT id, stripe_event_id, event_type, created_at,
       NOW() - created_at AS age
FROM webhook_events
WHERE status = 'pending'
  AND created_at < NOW() - INTERVAL '1 hour';
-- If non-zero: investigate and mark as failed; re-deliver from Stripe
```

### Recommended schedule

| Check | Frequency | Action if non-zero |
|-------|-----------|-------------------|
| Active-but-expired licenses | Daily (automated) | Run fix query |
| Orphaned promo refs | Weekly | Deactivate or delete the promo code |
| Over-redeemed codes | Weekly | Reset `used_count` if extra redemptions were accidental |
| Stuck pending webhooks | Daily | Mark as failed, re-deliver from Stripe |
| Invalid tier values | Weekly | Investigate the webhook that created the license |

---

## 7. GDPR Data Deletion

**When to use:** Customer submits a "right to erasure" request.

### Data inventory

| Table | Customer data | Retention recommendation |
|-------|--------------|--------------------------|
| `customers` | `email`, `name`, `stripe_customer_id` | Anonymise (not delete) to preserve audit trail |
| `licenses` | License keys | Revoke; retain anonymised row for financial records |
| `portal_otps` | Email addresses | Delete immediately |
| `license_validations` | Hashed keys only (no email) | No action needed — cannot identify customer |
| `admin_logs` | Admin actions on the customer's record | Retain for audit period (legal requirement) |

### Deletion procedure

```sql
-- Step 1: Find the customer
SELECT id, email FROM customers WHERE email = 'customer@example.com';
-- Note the UUID (customer-uuid)

-- Step 2: Revoke all active licenses
UPDATE licenses
SET status = 'revoked', updated_at = NOW()
WHERE customer_id = 'customer-uuid'
  AND status = 'active';

-- Step 3: Delete OTPs
DELETE FROM portal_otps WHERE email = 'customer@example.com';

-- Step 4: Anonymise the customer record
-- (preferred over deleting — preserves the license audit trail for financial records)
UPDATE customers
SET
    email    = 'deleted_' || id || '@gdpr.invalid',
    name     = 'DELETED',
    stripe_customer_id = NULL
WHERE id = 'customer-uuid';

-- Step 5: Cancel Stripe subscription (do this in Stripe Dashboard or via API)
-- stripe subscriptions cancel sub_xxxxxxxxxxxxxxxx
```

**After completing:** Confirm to the customer (within 30 days of their request, per GDPR Article 12).

---

## 8. Incident Response Playbook

### Severity levels

| Level | Example | Response time | Actions |
|-------|---------|---------------|---------|
| **P0 — Critical** | All webhooks failing; no licenses issued | Immediate (< 15 min) | Page on-call, escalate, communicate to customers |
| **P1 — High** | Portal OTP not sending; rate limit overrun blocking SDK | Within 1 hour | Notify team |
| **P2 — Medium** | Admin dashboard shows wrong data; single webhook failure | Within 4 hours | Fix in next deploy |
| **P3 — Low** | Documentation gap; cosmetic bug | Next sprint | Create issue |

### P0 Response checklist

1. **Acknowledge** — post in incident channel within 5 minutes: "Investigating [ISSUE] — [NAME] is on it"
2. **Diagnose** — check these in order:
   - Edge Function logs: `supabase functions logs stripe-webhook --tail`
   - Supabase status: [status.supabase.com](https://status.supabase.com)
   - Stripe status: [status.stripe.com](https://status.stripe.com)
   - Failed webhook count: `SELECT COUNT(*) FROM webhook_events WHERE status='failed' AND created_at > NOW() - INTERVAL '1 hour'`
3. **Mitigate** — use the relevant runbook above to resolve
4. **Communicate** — if license delivery was delayed >1 hour, email affected customers:

```
Subject: AgentSentinel — License delivery delay (resolved)

Hi [Name],

We experienced a brief delay in license delivery on [DATE] between [TIME] and [TIME] UTC.
Your license is now available at https://agentsentinel.net/portal.

If you don't see it, reply to this email and we'll help immediately.

The AgentSentinel Team
```

5. **Verify** — confirm resolution with the check in [Section 9 of DEPLOYMENT.md](DEPLOYMENT.md#9-verify-your-deployment)
6. **Post-mortem** — document timeline, root cause, and preventive measures within 48 hours

### Emergency quick reference

```bash
# View recent Edge Function errors
supabase functions logs stripe-webhook --tail
supabase functions logs validate-license --tail
supabase functions logs send-portal-otp --tail

# Check recent failed webhooks
supabase db execute --sql \
  "SELECT stripe_event_id, error_message, created_at FROM webhook_events WHERE status='failed' ORDER BY created_at DESC LIMIT 10"

# Fix active-but-expired licenses
supabase db execute --sql \
  "UPDATE licenses SET status='expired' WHERE expires_at < NOW() AND status='active'"

# Clear OTP rate limit for locked-out customer
supabase db execute --sql \
  "DELETE FROM portal_otps WHERE email='customer@example.com' AND verified=FALSE AND created_at > NOW() - INTERVAL '15 minutes'"

# Run full integrity check
psql "$DATABASE_URL" -f scripts/db-integrity-check.sql
```

---

For detailed troubleshooting of specific errors, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

For secret generation and environment setup, see [DEPLOYMENT.md](DEPLOYMENT.md#6-generate-secrets).
