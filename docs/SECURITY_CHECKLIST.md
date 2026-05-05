# AgentSentinel Security Checklist — Production Sign-Off

> **TL;DR:** Complete this checklist before going live. Every item must be ✅ before handling real customer payments.

---

## How to Use This Checklist

Work through each section. Check off items as you verify them. Items marked **🔴 CRITICAL** will cause a security incident if missed. Items marked **🟡 IMPORTANT** degrade security but may not be immediately exploitable.

---

## Section 1 — Secrets and Environment Variables

| # | Check | Status |
|---|-------|--------|
| 1.1 | 🔴 `AGENTSENTINEL_LICENSE_SIGNING_SECRET` is a 64-char hex string generated with `openssl rand -hex 32` | ☐ |
| 1.2 | 🔴 `ADMIN_API_SECRET` is a 64-char hex string generated with `openssl rand -hex 32` | ☐ |
| 1.3 | 🔴 Neither secret appears in source code, git history, or log files | ☐ |
| 1.4 | 🔴 `.env` and `supabase/.env` are in `.gitignore` and have never been committed | ☐ |
| 1.5 | 🔴 All secrets are set in Supabase Edge Function environment: `supabase secrets list` shows all required vars | ☐ |
| 1.6 | 🟡 `AGENTSENTINEL_DEV=1` and `AGENTSENTINEL_DEV_MODE=true` are **not** set in production | ☐ |
| 1.7 | 🟡 `STRIPE_SECRET_KEY` uses `sk_live_…` (not `sk_test_…`) in production | ☐ |

**Verify with:**
```bash
agentsentinel-config-check
# All required variables should show ✅

git log --all --oneline --diff-filter=A -- .env supabase/.env
# Should return empty (these files should never have been committed)
```

---

## Section 2 — API Endpoint Security

| # | Check | Status |
|---|-------|--------|
| 2.1 | 🔴 `validate-license` is rate-limited: 20 req/min per IP | ☐ |
| 2.2 | 🔴 `validate-promo` is rate-limited: 10 req/min per IP | ☐ |
| 2.3 | 🔴 `admin-generate-promo` requires `Authorization: Bearer <ADMIN_API_SECRET>` | ☐ |
| 2.4 | 🔴 `admin-generate-promo` returns `401` when called without a valid token | ☐ |
| 2.5 | 🟡 `stripe-webhook` verifies the `Stripe-Signature` header before processing | ☐ |
| 2.6 | 🟡 `send-portal-otp` is rate-limited: 3 sends per email per 15 minutes | ☐ |
| 2.7 | 🟡 `customer-portal` is rate-limited: 5 verify failures per email per 15 minutes | ☐ |

**Verify rate limits:**
```bash
# Test validate-license rate limit (send 21 requests — 21st should 429)
for i in $(seq 1 21); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    https://YOUR_PROJECT.supabase.co/functions/v1/validate-license \
    -H "Content-Type: application/json" \
    -d '{"license_key": "test"}')
  echo "Request $i: HTTP $STATUS"
done
# Request 21+ should return 429

# Test admin endpoint auth (should return 401)
curl -X POST https://YOUR_PROJECT.supabase.co/functions/v1/admin-generate-promo \
  -H "Content-Type: application/json" \
  -d '{"code": "TEST", "type": "discount_percent", "value": 10}'
# Expected: HTTP 401
```

---

## Section 3 — Browser / Front-End Security

| # | Check | Status |
|---|-------|--------|
| 3.1 | 🔴 `SUPABASE_SERVICE_ROLE_KEY` is **never** embedded in HTML, JavaScript files, or CDN assets | ☐ |
| 3.2 | 🔴 `ADMIN_API_SECRET` is **never** embedded in HTML, JavaScript files, or CDN assets | ☐ |
| 3.3 | 🔴 License keys are **never** written to `localStorage` (sessionStorage or in-memory only) | ☐ |
| 3.4 | 🟡 `SUPABASE_SERVICE_ROLE_KEY` in the admin dashboard is stored in `sessionStorage` (clears on tab close) | ☐ |
| 3.5 | 🟡 The admin dashboard is not accessible from the public internet (firewall/IP allowlist/VPN only) | ☐ |

**Verify no keys in HTML:**
```bash
# Scan all HTML/JS files for service-role key patterns
grep -r "service_role\|eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" \
  index.html portal.html pricing-team.html success.html \
  python/agentsentinel/dashboard/static/
# Expected: no matches

# Scan for localStorage license key writes
grep -r "localStorage.*licen\|localStorage.*key" \
  python/agentsentinel/dashboard/static/ portal.html
# Expected: no matches
```

---

## Section 4 — Customer Privacy

| # | Check | Status |
|---|-------|--------|
| 4.1 | 🔴 `send-portal-otp` returns identical responses for existing and non-existing emails (email enumeration resistance) | ☐ |
| 4.2 | 🔴 OTP values are stored as bcrypt hashes (not plaintext) in `portal_otps` | ☐ |
| 4.3 | 🟡 OTPs expire after 10 minutes | ☐ |
| 4.4 | 🟡 License keys in server logs are masked to first 12 characters + `…` | ☐ |
| 4.5 | 🟡 Customer emails are not included in error responses from public endpoints | ☐ |

**Verify enumeration resistance:**
```bash
# Response for a real email should be identical in HTTP status and structure to a fake email
curl -s -X POST https://YOUR_PROJECT.supabase.co/functions/v1/send-portal-otp \
  -H "Content-Type: application/json" \
  -d '{"email": "this-does-not-exist-999@example.com"}'
# Expected: 200 OK (not 404)
```

---

## Section 5 — Webhook Integrity

| # | Check | Status |
|---|-------|--------|
| 5.1 | 🔴 `stripe-webhook` verifies `Stripe-Signature` header using `constructEvent()` | ☐ |
| 5.2 | 🔴 `webhook_events` table has a unique constraint on `stripe_event_id` (replay protection) | ☐ |
| 5.3 | 🟡 A replayed Stripe event is silently discarded (idempotent) — not processed twice | ☐ |

**Verify idempotency:**
```bash
# Get a recent webhook event ID from the admin dashboard
EVENT_ID="evt_xxxxxxxxxxxxxxxx"

# Check it's in webhook_events
supabase db execute --sql \
  "SELECT stripe_event_id, status FROM webhook_events WHERE stripe_event_id = '$EVENT_ID'"

# If you re-deliver the same event from Stripe, the license count should not increase
```

---

## Section 6 — Audit Trail

| # | Check | Status |
|---|-------|--------|
| 6.1 | 🟡 All admin-initiated license changes are logged to `admin_logs` | ☐ |
| 6.2 | 🟡 All promo code creates/updates/deletes are logged to `admin_logs` | ☐ |
| 6.3 | 🟡 Sensitive field values in `admin_logs` are SHA-256 hashed (not plaintext) | ☐ |

**Verify audit logging:**
```bash
# Perform a test admin action (e.g., create a test promo code)
# Then check the audit log:
supabase db execute --sql \
  "SELECT action, actor, created_at FROM admin_logs ORDER BY created_at DESC LIMIT 5"
# Should show the recent action
```

---

## Section 7 — License Key Security

| # | Check | Status |
|---|-------|--------|
| 7.1 | 🔴 `validate-license` checks `license_key` format prefix before hitting the database | ☐ |
| 7.2 | 🔴 HMAC signature verification in `validate-license` uses constant-time comparison | ☐ |
| 7.3 | 🟡 `AGENTSENTINEL_LICENSE_SIGNING_SECRET` and the Python SDK secret are identical (parity test) | ☐ |

**Verify HMAC parity:**
```bash
cd python && python -m pytest tests/test_licensing_parity.py -v
# All tests should pass
```

---

## Section 8 — Database Security

| # | Check | Status |
|---|-------|--------|
| 8.1 | 🟡 Supabase Row-Level Security (RLS) is enabled on all tables | ☐ |
| 8.2 | 🟡 Service-role key is only used server-side (Edge Functions, Python dashboard) | ☐ |
| 8.3 | 🟡 Anon key policies do not allow reads on sensitive columns (license keys, emails) | ☐ |
| 8.4 | 🟡 Database integrity check passes: `psql "$DATABASE_URL" -f scripts/db-integrity-check.sql` | ☐ |

---

## Final Sign-Off

Before going live, confirm:

```
[ ] All 🔴 CRITICAL items are ✅
[ ] All 🟡 IMPORTANT items are ✅ or have documented exceptions
[ ] agentsentinel-config-check passes with no MISSING variables
[ ] Python parity tests pass: cd python && python -m pytest tests/ -v
[ ] A test purchase flow has been completed end-to-end in Stripe test mode
[ ] The admin dashboard login has been tested with the production ADMIN_API_SECRET
[ ] Webhook delivery has been tested with a test Stripe event
```

---

## Related Documentation

- [DEPLOYMENT.md](DEPLOYMENT.md) — environment variable setup and secret generation
- [RUNBOOKS.md](RUNBOOKS.md) — how to rotate secrets safely
- [ADMIN_WORKFLOW.md](ADMIN_WORKFLOW.md) — admin dashboard setup
- [PRODUCTION_READINESS_AUDIT.md](PRODUCTION_READINESS_AUDIT.md) — full 9-phase audit results
