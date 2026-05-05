# AgentSentinel — Promo Code Guide

Admin workflow for creating and managing promotional codes.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Promo Code Types](#2-promo-code-types)
3. [Creating a Promo Code](#3-creating-a-promo-code)
4. [Promo Code Examples](#4-promo-code-examples)
5. [Tier Restrictions](#5-tier-restrictions)
6. [Expiry and Usage Limits](#6-expiry-and-usage-limits)
7. [Monitoring Promo Usage](#7-monitoring-promo-usage)
8. [Deactivating and Deleting Codes](#8-deactivating-and-deleting-codes)
9. [How Promos Apply at Checkout](#9-how-promos-apply-at-checkout)
10. [API Reference](#10-api-reference)

---

## 1. Overview

Promo codes allow you to offer discounts, free trials, and extended access periods to customers. Codes are managed through:

1. **Admin Dashboard** — the Promos page (`admin/js/pages/promos.js`) provides a UI for creating and managing codes.
2. **`admin-generate-promo` Edge Function** — the production API endpoint used by the dashboard.
3. **Supabase REST API** — direct CRUD for advanced operations.

**Database schema** (`supabase/migrations/010_add_promo_codes.sql`):

```sql
promo_codes (
  id          UUID PRIMARY KEY,
  code        TEXT UNIQUE NOT NULL,        -- e.g. "LAUNCH50"
  type        TEXT NOT NULL,              -- discount_percent | discount_fixed | trial_extension | unlimited_trial
  value       INTEGER NOT NULL DEFAULT 0, -- meaning depends on type
  description TEXT,
  tier        TEXT,                       -- null = all tiers; or a specific tier
  active      BOOLEAN DEFAULT TRUE,
  expires_at  TIMESTAMPTZ,
  max_uses    INTEGER,                    -- null = unlimited
  used_count  INTEGER DEFAULT 0,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  created_by  TEXT DEFAULT 'admin'
)
```

---

## 2. Promo Code Types

| Type | `value` field | Effect |
|---|---|---|
| `discount_percent` | `0`–`100` (percent) | Reduces price by a percentage at Stripe checkout |
| `discount_fixed` | Amount in **cents** (USD) | Reduces price by a fixed dollar amount at Stripe checkout |
| `trial_extension` | Number of **days** | Extends the free trial period by N days |
| `unlimited_trial` | `0` (ignored) | Grants unlimited trial access (no payment required) |

---

## 3. Creating a Promo Code

### Via the Admin Dashboard

1. Log in to the admin dashboard (`agentsentinel-dashboard` or Cloudflare Pages URL).
2. Navigate to the **Promos** page.
3. Click **+ New Promo**.
4. Fill in the form:
   - **Code** — uppercase letters, numbers, dash, underscore; 3–20 characters.
   - **Type** — select from the 4 types above.
   - **Value** — integer; meaning depends on type.
   - **Tier** (optional) — restrict to a specific tier.
   - **Expires At** (optional) — ISO 8601 date.
   - **Max Uses** (optional) — integer limit.
   - **Description** — internal note for admin reference.
5. Click **Create**.

### Via the API

```bash
curl -X POST \
  https://YOUR_PROJECT.supabase.co/functions/v1/admin-generate-promo \
  -H "Authorization: Bearer $ADMIN_API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "LAUNCH50",
    "type": "discount_percent",
    "value": 50,
    "description": "50% off launch promotion",
    "expires_at": "2026-12-31T23:59:59Z",
    "max_uses": 100
  }'
```

**Response (201 Created):**

```json
{
  "id": "a1b2c3d4-…",
  "code": "LAUNCH50",
  "type": "discount_percent",
  "value": 50,
  "active": true,
  "expires_at": "2026-12-31T23:59:59+00:00",
  "max_uses": 100,
  "used_count": 0,
  "created_at": "2026-05-05T10:00:00+00:00"
}
```

**Error — duplicate code (409 Conflict):**

```json
{
  "error": "Promo code \"LAUNCH50\" already exists",
  "id": "a1b2c3d4-…"
}
```

---

## 4. Promo Code Examples

### Example 1 — 50% off for all tiers (limited time)

```json
{
  "code": "LAUNCH50",
  "type": "discount_percent",
  "value": 50,
  "description": "50% off launch promotion — all tiers",
  "expires_at": "2026-12-31T23:59:59Z",
  "max_uses": null
}
```

Customer sees price halved at Stripe checkout.

---

### Example 2 — $20 off for Pro tier only

```json
{
  "code": "PRO20",
  "type": "discount_fixed",
  "value": 2000,
  "tier": "pro",
  "description": "$20 off the Pro plan",
  "max_uses": 50
}
```

**Note:** `value` is in **cents** — `2000` = $20.00.  
The code is rejected at checkout for non-Pro tiers.

---

### Example 3 — 30-day extended trial for Starter

```json
{
  "code": "TRIAL30",
  "type": "trial_extension",
  "value": 30,
  "tier": "starter",
  "description": "30-day extended trial for Starter plan",
  "expires_at": "2026-07-01T00:00:00Z"
}
```

Customer's `expires_at` on the license is extended by 30 days from the current expiry date. No payment required for the extension period.

---

### Example 4 — Unlimited trial (no payment)

```json
{
  "code": "PARTNER2026",
  "type": "unlimited_trial",
  "value": 0,
  "description": "Unlimited trial for partner program",
  "max_uses": 10
}
```

Customer gets a license with `status = active` and no `expires_at`. No Stripe payment collected. Use sparingly — typically for partners and evaluators.

---

## 5. Tier Restrictions

The `tier` field restricts a promo to customers purchasing a specific plan.

| `tier` value | Applies to |
|---|---|
| `null` (default) | All tiers |
| `free` | Free tier |
| `starter` | Starter plan |
| `pro` | Pro plan |
| `pro_team` | Pro Team plan |
| `team` | Team plan |
| `enterprise` | Enterprise plan |

When a customer applies a tier-restricted code at checkout for the wrong tier, `validate-promo` returns `{valid: false, reason: "tier_mismatch"}`.

---

## 6. Expiry and Usage Limits

### Expiry

- `expires_at: null` — the code never expires.
- `expires_at: "ISO 8601 string"` — code becomes invalid after this date/time (UTC).
- The code creation API rejects `expires_at` dates in the past.

### Usage limits

- `max_uses: null` — unlimited redemptions.
- `max_uses: N` — after `used_count` reaches `N`, the code returns `{valid: false, reason: "exhausted"}`.
- `used_count` is incremented atomically when a license is created via the Stripe webhook (using the `increment_promo_used_count` database function from migration 012).

### Checking limits

```bash
# Check a code's current usage
curl https://YOUR_PROJECT.supabase.co/rest/v1/promo_codes?select=code,max_uses,used_count&code=eq.LAUNCH50 \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY"
```

---

## 7. Monitoring Promo Usage

### Admin Dashboard — Promos Page

The Promos page shows:
- All active codes with `used_count / max_uses`
- Expiry status
- Per-code redemption history (linked licenses)

### Direct query

```sql
-- Top 10 most-used active promo codes
SELECT code, type, value, used_count, max_uses, expires_at
FROM promo_codes
WHERE active = TRUE
ORDER BY used_count DESC
LIMIT 10;

-- Licenses redeemed with a specific code
SELECT l.license_key, l.tier, l.status, l.created_at, l.discount_type, l.discount_value
FROM licenses l
JOIN promo_codes p ON l.promo_code_id = p.id
WHERE p.code = 'LAUNCH50'
ORDER BY l.created_at DESC;
```

### Integrity check

Run [`scripts/db-integrity-check.sql`](../scripts/db-integrity-check.sql) to verify:
- No licenses reference deleted promo codes.
- No codes have `used_count > max_uses`.

---

## 8. Deactivating and Deleting Codes

### Deactivate (stop accepting new redemptions, keep history)

```bash
# Via Supabase REST
curl -X PATCH \
  https://YOUR_PROJECT.supabase.co/rest/v1/promo_codes?code=eq.LAUNCH50 \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"active": false}'
```

Or via the admin dashboard Promos page → Edit → uncheck **Active**.

### Delete (removes the code — preserves existing license references)

Deleting a promo code does **not** revoke licenses that used it. The `promo_code_id` on those licenses will become a dangling reference, which is detected by `scripts/db-integrity-check.sql`.

**Recommendation:** Deactivate rather than delete. Delete only codes created in error before any redemptions.

```bash
curl -X DELETE \
  https://YOUR_PROJECT.supabase.co/rest/v1/promo_codes?code=eq.TEST_CODE \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY"
```

---

## 9. How Promos Apply at Checkout

The full promo-to-license flow:

```
Customer enters code → validate-promo (rate: 10/min)
    ↓ valid
Checkout page applies Stripe coupon to session
    ↓ payment completed
stripe-webhook receives checkout.session.completed
    ↓
Webhook extracts metadata.promo_code_id from session
    ↓
INSERT licenses (..., promo_code_id, discount_type, discount_value, promo_applied_at)
    ↓
increment_promo_used_count(promo_code_id) [atomic DB function]
    ↓
License delivered via email; portal shows applied promo
```

**Stripe coupon mapping:**

| Promo type | Stripe coupon | Applied to |
|---|---|---|
| `discount_percent` | `percent_off: value` | Subscription invoice |
| `discount_fixed` | `amount_off: value` | Subscription invoice |
| `trial_extension` | `trial_period_days: value` | Subscription trial |
| `unlimited_trial` | No Stripe payment | License created without payment |

---

## 10. API Reference

### `POST /functions/v1/admin-generate-promo`

**Authentication:** `Authorization: Bearer <ADMIN_API_SECRET>`

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | `string` | ✅ | 3–20 chars: `[A-Z0-9_-]` (normalised to uppercase) |
| `type` | `string` | ✅ | `discount_percent` / `discount_fixed` / `trial_extension` / `unlimited_trial` |
| `value` | `integer` | ✅ (except `unlimited_trial`) | Meaning depends on type |
| `tier` | `string\|null` | ❌ | Restrict to a specific tier |
| `expires_at` | `ISO 8601` | ❌ | Code expiry date (must be in the future) |
| `max_uses` | `integer\|null` | ❌ | Maximum redemptions (`null` = unlimited) |
| `description` | `string` | ❌ | Internal admin description |
| `active` | `boolean` | ❌ | Default `true` |
| `created_by` | `string` | ❌ | Admin identifier for audit trail |

**Responses:**

| Status | Meaning |
|---|---|
| `201 Created` | Promo code created; body is the new row |
| `400 Bad Request` | Validation error; body has `error` field |
| `401 Unauthorized` | Missing or invalid `ADMIN_API_SECRET` |
| `409 Conflict` | Code already exists; body has `error` + `id` of existing code |
| `500 Internal Server Error` | Database error |

### `POST /functions/v1/validate-promo`

**Authentication:** None (public endpoint)  
**Rate limit:** 10 requests/minute per IP

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | `string` | ✅ | Promo code to validate |
| `tier` | `string` | ❌ | Customer's selected tier (enables tier_mismatch check) |

**Response (valid):**

```json
{
  "valid": true,
  "id": "uuid",
  "type": "discount_percent",
  "value": 50,
  "description": "50% off launch promotion"
}
```

**Response (invalid):**

```json
{
  "valid": false,
  "reason": "not_found | inactive | expired | exhausted | tier_mismatch"
}
```
