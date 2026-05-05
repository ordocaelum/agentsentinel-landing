# AgentSentinel — Troubleshooting Guide

Common issues, their causes, and recovery steps.

---

## Table of Contents

1. [Failed Webhooks](#1-failed-webhooks)
2. [Stuck / Incorrect License Status](#2-stuck--incorrect-license-status)
3. [Rate Limit Overflow](#3-rate-limit-overflow)
4. [Promo Code Issues](#4-promo-code-issues)
5. [OTP / Portal Login Issues](#5-otp--portal-login-issues)
6. [Admin Dashboard Issues](#6-admin-dashboard-issues)
7. [SDK Validation Issues](#7-sdk-validation-issues)
8. [Database Integrity Issues](#8-database-integrity-issues)
9. [Email Delivery Issues](#9-email-delivery-issues)

---

## 1. Failed Webhooks

### Symptoms
- Customer paid but didn't receive a license email.
- Webhook event shows `status = 'failed'` in the admin dashboard.
- Stripe Dashboard shows a webhook delivery failure.

### Diagnosis

**Step 1 — Check the webhook_events table:**

```sql
SELECT id, stripe_event_id, event_type, status, error_message, created_at
FROM webhook_events
WHERE status = 'failed'
ORDER BY created_at DESC
LIMIT 20;
```

**Step 2 — Check Stripe Dashboard:**
1. Go to [Stripe Dashboard → Webhooks](https://dashboard.stripe.com/webhooks).
2. Select your webhook endpoint.
3. Find the failed event and inspect the response body.

**Step 3 — Check Edge Function logs:**
```bash
supabase functions logs stripe-webhook --tail
```

### Recovery

**Re-deliver from Stripe (recommended):**
1. In Stripe Dashboard, find the failed event.
2. Click "Resend" — the webhook will be re-delivered.
3. The `INSERT … ON CONFLICT DO NOTHING` deduplication ensures the event is processed once even if it was partially processed before.

**Manual license creation (last resort):**
```sql
-- Only use if Stripe re-delivery is not possible
INSERT INTO licenses (
  customer_id, license_key, tier, status,
  agents_limit, events_limit, stripe_subscription_id
) VALUES (
  'customer-uuid', 'asv1_manually_generated_key', 'pro', 'active',
  10, 100000, 'sub_stripe_id_here'
);
```

**Mark failed webhook as processed (after manual resolution):**
```sql
UPDATE webhook_events
SET status = 'processed', error_message = 'Manually resolved'
WHERE stripe_event_id = 'evt_xxxxxxxxxxxxxxxx';
```

### Prevention
- Monitor the `failed_webhooks` KPI on the admin dashboard Overview page.
- Set up Stripe webhook failure alerts (Dashboard → Webhooks → Alert settings).
- Ensure `STRIPE_WEBHOOK_SECRET` is correctly set in Supabase secrets.

---

## 2. Stuck / Incorrect License Status

### Symptoms
- License shows `active` but subscription was cancelled.
- License shows `active` but expiry date has passed.
- Customer can't access portal — license shows wrong status.

### Diagnosis

**Check license and subscription:**
```sql
SELECT id, license_key, tier, status, expires_at, stripe_subscription_id
FROM licenses
WHERE customer_id = (SELECT id FROM customers WHERE email = 'customer@example.com');
```

**Check for active licenses past expiry:**
```sql
SELECT id, license_key, status, expires_at, NOW() - expires_at AS overdue_by
FROM licenses
WHERE expires_at < NOW() AND status = 'active';
```

### Recovery

**Fix active-but-expired licenses:**
```sql
UPDATE licenses
SET status = 'expired', updated_at = NOW()
WHERE expires_at < NOW() AND status = 'active';
```

**Fix status after subscription cancellation:**
```sql
UPDATE licenses
SET status = 'cancelled', updated_at = NOW()
WHERE stripe_subscription_id = 'sub_xxxxxxxxxxxxxxxx'
  AND status != 'cancelled';
```

**Manually extend expiry:**
```sql
UPDATE licenses
SET expires_at = NOW() + INTERVAL '30 days', updated_at = NOW()
WHERE id = 'license-uuid-here';
```

**Revoke a license (admin action):**
Via the admin dashboard → Licenses page → find license → click "Revoke".

Or directly:
```sql
UPDATE licenses
SET status = 'revoked', updated_at = NOW()
WHERE id = 'license-uuid-here';
```

---

## 3. Rate Limit Overflow

### Symptoms
- `validate-license` returns HTTP 429 with `Retry-After: 60`.
- `validate-promo` returns HTTP 429.
- OTP send returns 429.

### Rate Limit Configuration

| Endpoint | Limit | Window |
|---|---|---|
| `validate-license` | 20 req/min | Per IP, sliding window |
| `validate-promo` | 10 req/min | Per IP, sliding window |
| `send-portal-otp` | 3 sends | Per email, 15 min |
| `customer-portal` | 5 failures | Per email, 15 min |

### Recovery

**For SDK rate limits:**
The in-memory rate limiter resets after the window expires (60 seconds). No action needed — the SDK will retry after `Retry-After`.

For high-frequency validation (>20/min), switch to **offline HMAC verification**:

```python
# Python SDK — offline verification bypasses the rate limit
sentinel = AgentSentinel(
    license_key="asv1_…",
    offline=True,  # use local HMAC verification
)
```

**For OTP rate limits:**
The OTP rate limit is per-email per 15-minute window. If a customer is locked out:

```sql
-- Check OTP send attempts for a specific email
SELECT email, created_at, verified, expires_at
FROM portal_otps
WHERE email = 'customer@example.com'
ORDER BY created_at DESC
LIMIT 10;

-- Manually clear OTP rate limit (deletes pending OTPs — customer can request new one)
DELETE FROM portal_otps
WHERE email = 'customer@example.com'
  AND verified = FALSE
  AND expires_at > NOW();
```

### Prevention for SDK at scale
- Cache validation results in your application (licenses change infrequently).
- Use offline HMAC verification for per-request checks.
- Avoid calling `validate-license` on every API request — validate at startup and cache.

---

## 4. Promo Code Issues

### Code not working at checkout

**Check code validity:**
```bash
curl -X POST https://YOUR_PROJECT.supabase.co/functions/v1/validate-promo \
  -H "Content-Type: application/json" \
  -d '{"code": "LAUNCH50", "tier": "pro"}'
```

| Response `reason` | Meaning | Fix |
|---|---|---|
| `not_found` | Code doesn't exist | Check the code spelling (case-insensitive) |
| `inactive` | Code has been deactivated | Reactivate via admin dashboard |
| `expired` | Code's `expires_at` has passed | Extend expiry or create a new code |
| `exhausted` | `used_count >= max_uses` | Increase `max_uses` or create a new code |
| `tier_mismatch` | Code restricted to a different tier | Remove tier restriction or use the correct plan |

**Reactivate a deactivated code:**
```bash
curl -X PATCH \
  https://YOUR_PROJECT.supabase.co/rest/v1/promo_codes?code=eq.LAUNCH50 \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"active": true}'
```

**Extend expiry:**
```bash
curl -X PATCH \
  https://YOUR_PROJECT.supabase.co/rest/v1/promo_codes?code=eq.LAUNCH50 \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"expires_at": "2027-12-31T23:59:59Z"}'
```

**Reset over-redeemed count:**
```sql
-- Only if the extra redemptions were accidental
UPDATE promo_codes
SET used_count = max_uses - 10  -- leave 10 uses available
WHERE code = 'LAUNCH50';
```

### Promo applied but not showing in portal

The portal displays `promo_applied_at` and `discount_type` from the `licenses` table. If these are null after checkout:

1. Check that the Stripe metadata contained `promo_code_id`.
2. Verify the `stripe-webhook` Edge Function correctly parsed and saved the promo fields.

```sql
SELECT id, promo_code_id, discount_type, discount_value, promo_applied_at
FROM licenses
WHERE stripe_session_id = 'cs_xxxxxxxxxxxxxxxx';
```

---

## 5. OTP / Portal Login Issues

### Customer not receiving OTP email

1. Check that `RESEND_API_KEY` is set in Supabase secrets.
2. Check Resend dashboard for delivery status.
3. Ask customer to check spam folder.
4. Verify the OTP was created:
   ```sql
   SELECT id, email, otp_hash, verified, created_at, expires_at
   FROM portal_otps
   WHERE email = 'customer@example.com'
   ORDER BY created_at DESC
   LIMIT 5;
   ```
5. Ensure the `send-portal-otp` Edge Function is deployed:
   ```bash
   supabase functions list
   ```

### OTP expired

OTPs expire after 10 minutes. The customer should request a new OTP.

**Check for edge cases (customer entered OTP after expiry):**
```sql
SELECT expires_at, NOW(), NOW() > expires_at AS is_expired
FROM portal_otps
WHERE email = 'customer@example.com'
ORDER BY created_at DESC
LIMIT 1;
```

### Customer locked out (too many failed attempts)

```sql
-- Check failure count
SELECT email, COUNT(*) AS recent_failures
FROM portal_otps
WHERE email = 'customer@example.com'
  AND verified = FALSE
  AND created_at > NOW() - INTERVAL '15 minutes'
GROUP BY email;

-- Clear the rate limit window by deleting recent failed attempts
DELETE FROM portal_otps
WHERE email = 'customer@example.com'
  AND verified = FALSE
  AND created_at > NOW() - INTERVAL '15 minutes';
```

---

## 6. Admin Dashboard Issues

### "Unauthorized" or blank data

1. Verify the Supabase URL, service-role key, and admin API secret are correct.
2. In the admin dashboard login form, re-enter credentials.
3. Verify credentials with:
   ```bash
   curl https://YOUR_PROJECT.supabase.co/rest/v1/licenses?limit=1 \
     -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
     -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY"
   ```

### Dashboard not loading / JavaScript errors

1. Open browser DevTools → Console.
2. Check for module import errors (ES module compatibility).
3. Ensure the dashboard is served over HTTP/HTTPS (not `file://`).
4. Start the dashboard server: `agentsentinel-dashboard`

### Webhook KPIs showing wrong counts

This was a known bug (fixed in this PR). If you see all zeros in the processed/failed/pending KPIs:
- Ensure you're running the latest dashboard version.
- The fix uses the `status` column (added in migration 012) instead of the deprecated `processed` boolean.

---

## 7. SDK Validation Issues

### `LicenseError: Invalid license key`

- Verify the key exists: check the portal at [agentsentinel.net/portal](https://agentsentinel.net/portal).
- Check the key format: should start with `asv1_` or `as_<tier>_`.
- Run the integrity check: `scripts/db-integrity-check.sql`.

### `LicenseError: Unrecognised license key format`

The key doesn't match any known format. Common causes:
- Copied key with leading/trailing spaces — trim whitespace.
- Copied partial key — use the full key from the portal.
- Using an API key instead of a license key.

### Offline verification failing

Ensure `AGENTSENTINEL_LICENSE_SIGNING_SECRET` in the Python environment matches the secret in Supabase:

```bash
# In Python env
echo $AGENTSENTINEL_LICENSE_SIGNING_SECRET

# In Supabase
supabase secrets list | grep LICENSE_SIGNING_SECRET
```

Both should be the same 64-character hex string. If they differ, regenerate with:
```bash
./scripts/generate-secrets.sh --regenerate AGENTSENTINEL_LICENSE_SIGNING_SECRET
```
Then update both the Python environment and Supabase secrets.

---

## 8. Database Integrity Issues

Run [`scripts/db-integrity-check.sql`](../scripts/db-integrity-check.sql) to detect:

| Check | Fix |
|---|---|
| Orphaned `promo_code_id` refs | Deactivate rather than delete promo codes |
| Active licenses past expiry | `UPDATE licenses SET status='expired' WHERE expires_at < NOW() AND status='active'` |
| Invalid tier values | Investigate; correct the tier in the `licenses` table |
| Over-redeemed promo codes | `UPDATE promo_codes SET used_count = max_uses WHERE used_count > max_uses AND max_uses IS NOT NULL` |
| Licenses without customers | Investigate; the webhook should always create customer first |
| Stuck pending webhooks >1h | Mark as `failed`; re-deliver from Stripe |

---

## 9. Email Delivery Issues

### Resend API errors

Check Edge Function logs:
```bash
supabase functions logs stripe-webhook --tail
supabase functions logs send-portal-otp --tail
```

Common errors:

| Error | Fix |
|---|---|
| `401 Unauthorized` | Regenerate `RESEND_API_KEY` and update Supabase secret |
| `422 Unprocessable Entity` | Check that `from` address is verified in Resend dashboard |
| `429 Too Many Requests` | Resend rate limit — check your Resend plan limits |

### Verify Supabase secrets are set

```bash
supabase secrets list
```

All of the following should appear:
- `RESEND_API_KEY`
- `AGENTSENTINEL_LICENSE_SIGNING_SECRET`
- `ADMIN_API_SECRET`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Missing secrets → set them:
```bash
supabase secrets set RESEND_API_KEY=re_your_key_here
```

---

## Quick Reference — Emergency Commands

```bash
# View recent Edge Function errors
supabase functions logs stripe-webhook --tail
supabase functions logs validate-license --tail

# Check recent failed webhooks
supabase db execute --sql "SELECT stripe_event_id, error_message, created_at FROM webhook_events WHERE status='failed' ORDER BY created_at DESC LIMIT 10"

# Fix active-but-expired licenses
supabase db execute --sql "UPDATE licenses SET status='expired' WHERE expires_at < NOW() AND status='active'"

# Check OTP rate limit status for a customer
supabase db execute --sql "SELECT email, COUNT(*) FROM portal_otps WHERE created_at > NOW() - INTERVAL '15 minutes' GROUP BY email"

# Run full integrity check
psql "$DATABASE_URL" -f scripts/db-integrity-check.sql
```
