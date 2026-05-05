# AgentSentinel Admin Workflow Guide

> **TL;DR:** Everything a new admin needs to go from zero → running promo codes and managing licenses. You can create your first promo code in under 10 minutes by following this guide.

---

## Table of Contents

1. [First-Time Admin Setup](#1-first-time-admin-setup)
2. [Dashboard Tour — All 8 Pages](#2-dashboard-tour--all-8-pages)
   - [Overview](#21-overview)
   - [Licenses](#22-licenses)
   - [Promos](#23-promos)
   - [Users](#24-users)
   - [Metrics](#25-metrics)
   - [Webhooks](#26-webhooks)
   - [System](#27-system)
   - [Audit Log](#28-audit-log)
3. [Promo Code Workflow](#3-promo-code-workflow)
   - [Create a Promo Code](#31-create-a-promo-code)
   - [Promo Type Examples](#32-promo-type-examples)
   - [Edit, Deactivate, Delete](#33-edit-deactivate-delete)
   - [Monitor Promo Usage](#34-monitor-promo-usage)
4. [License Management](#4-license-management)
   - [View and Search Licenses](#41-view-and-search-licenses)
   - [Revoke a License](#42-revoke-a-license)
   - [Extend a License](#43-extend-a-license)
   - [View Validations](#44-view-validations)
5. [Audit Log](#5-audit-log)
6. [Troubleshooting Admin Issues](#6-troubleshooting-admin-issues)

---

## 1. First-Time Admin Setup

### Step 1 — Get your `ADMIN_API_SECRET`

The `ADMIN_API_SECRET` is a shared secret that protects the admin-only API endpoints (like creating promo codes). You need to generate it once and store it in two places: your local `.env` file and Supabase Edge Function secrets.

**Generate a strong secret:**

```bash
openssl rand -hex 32
```

This outputs 64 hex characters. Copy the output — you'll use it in the next steps.

**Example output:**
```
a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1
```

> **Security:** Keep this value private. Anyone with this secret can create/modify promo codes. Never paste it in Slack, GitHub issues, or log files.

---

### Step 2 — Add the secret to your `.env` file

Open (or create) `.env` in the repository root:

```bash
# In the repository root
cp .env.example .env
$EDITOR .env
```

Set the value:

```env
ADMIN_API_SECRET=a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1
```

You also need these variables for the dashboard to connect to Supabase:

```env
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
AGENTSENTINEL_LICENSE_SIGNING_SECRET=<another openssl rand -hex 32>
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for all required variables.

---

### Step 3 — Push the secret to Supabase Edge Functions

The `admin-generate-promo` Edge Function reads `ADMIN_API_SECRET` from Supabase secrets. Push it:

```bash
supabase secrets set ADMIN_API_SECRET=a3f8b2c1...
```

Push all secrets at once from your `supabase/.env` file:

```bash
supabase secrets set --env-file supabase/.env
```

---

### Step 4 — Start the admin dashboard

```bash
# Install the Python package (if not already installed)
pip install -e python/

# Start in dev mode (bypasses licence gate for local development)
AGENTSENTINEL_DEV=1 agentsentinel-dashboard
```

Or use the one-command script:

```bash
bash scripts/run-admin-dashboard.sh
```

Open **http://localhost:8080/admin** in your browser.

---

### Step 5 — Log in to the dashboard

The first time you open the dashboard, you'll see a **setup screen** asking for:

| Field | Where to find it |
|-------|-----------------|
| **Supabase URL** | `SUPABASE_URL` in your `.env` |
| **Supabase Service Role Key** | `SUPABASE_SERVICE_ROLE_KEY` in your `.env` |
| **Admin API Secret** | `ADMIN_API_SECRET` in your `.env` |

Fill these in and click **Save & Connect**.

> **Security note:** These credentials are stored in `sessionStorage` — they are cleared when you close the browser tab. You will need to re-enter them each session unless the dashboard auto-fills from cookies.

---

### Step 6 — Verify the connection

After logging in, you should see the **Overview** page with KPI cards showing license counts, revenue, and webhook status. If you see "Error loading data", check [Troubleshooting](#6-troubleshooting-admin-issues).

---

## 2. Dashboard Tour — All 8 Pages

### 2.1 Overview

**What it does:** Landing page of the dashboard. Shows live KPIs at a glance.

**KPI cards:**
- **Active Licenses** — total licenses with `status = 'active'`
- **Total Users** — total rows in `customers` table
- **Monthly Revenue** — sum of charges for this calendar month (from Stripe data in Supabase)
- **Webhooks Processed** — `webhook_events` with `status = 'processed'`
- **Webhooks Failed** — `webhook_events` with `status = 'failed'` (should be 0 in a healthy system)
- **Pending Webhooks** — `webhook_events` with `status = 'pending'` (normally 0)

**Common tasks:**
- Quick health check every morning — all KPIs should be non-zero for an active system
- If "Webhooks Failed" > 0, go to the Webhooks page and investigate

**Troubleshooting:**
- All zeros? The Supabase connection may have failed — click the settings icon and re-enter credentials
- "Webhooks Failed" > 0? See [RUNBOOKS.md — Failed Webhooks](RUNBOOKS.md#failed-webhooks)

---

### 2.2 Licenses

**What it does:** View, search, filter, and manage all issued license keys.

**What you see:**
- License key (partially masked)
- Customer email and name
- Tier (`starter`, `pro`, `pro_team`, `enterprise`)
- Status (`active`, `expired`, `cancelled`, `revoked`, `past_due`)
- Expiry date
- Applied promo code (if any)
- Creation date

**Common tasks:**
- **Search by email:** Type in the search box to filter by customer email
- **Filter by status:** Use the Status dropdown to see only active/expired/revoked licenses
- **Filter by tier:** Use the Tier dropdown
- **Revoke a license:** Click the "Revoke" button in the license row
- **View license details:** Click a row to see full details including validation history

**Troubleshooting:**
- License shows `active` but customer says it's not working → check `expires_at` date and tier
- License shows wrong tier → this can happen if the Stripe webhook didn't fire; manually update via SQL (see [RUNBOOKS.md](RUNBOOKS.md#stuck-license))

---

### 2.3 Promos

**What it does:** Create and manage promotional codes.

**What you see:**
- Code name (e.g., `LAUNCH50`)
- Type (`discount_percent`, `discount_fixed`, `trial_extension`, `unlimited_trial`)
- Value (percent, cents, days, or N/A)
- Usage: `used_count / max_uses`
- Status (active/inactive)
- Expiry date
- Tier restriction (if any)

**Common tasks:**
- **Create a promo code:** Click **+ New Promo** (see [Section 3](#3-promo-code-workflow) for full workflow)
- **Edit a promo:** Click the edit (pencil) icon in the row
- **Deactivate a promo:** Toggle the Active switch off — stops new redemptions
- **Delete a promo:** Click the delete (trash) icon — only do this before any redemptions

**Troubleshooting:**
- "Create" button doesn't work? → verify `ADMIN_API_SECRET` is set correctly in Settings
- Promo shows wrong usage count? → run `scripts/db-integrity-check.sql` to check for inconsistencies

---

### 2.4 Users

**What it does:** Browse all customer records linked to Stripe.

**What you see:**
- Customer email and name
- Stripe Customer ID
- Number of licenses
- Account creation date
- Last login date (portal)

**Common tasks:**
- **Look up a customer:** Search by email or name
- **View a customer's licenses:** Click the customer row to expand their license list
- **Find customers with promo codes:** Filter by promo or use SQL (see [RUNBOOKS.md](RUNBOOKS.md#promo-monitoring))

**Troubleshooting:**
- Customer not appearing? → they may not have completed checkout; check Stripe dashboard
- Customer has multiple records? → can happen if Stripe `stripe_customer_id` changed; check for duplicate emails in the `customers` table

---

### 2.5 Metrics

**What it does:** Analytics for license validations and tier distributions.

**What you see:**
- Validation requests over time (line chart)
- Valid vs invalid validation rate
- Tier breakdown (pie/bar chart)
- Top validation IPs (for rate limit monitoring)
- Validation failure reasons

**Common tasks:**
- **Monitor for brute-force attacks:** Look for a sudden spike in "invalid" validations from a single IP
- **Check tier adoption:** See which plans are most popular
- **Track growth:** License validation volume is a proxy for SDK usage

**Troubleshooting:**
- Chart shows no data? → `license_validations` table may be empty if no validations have been recorded yet
- Spike in invalid validations → check the top IPs and consider rate limit tightening

---

### 2.6 Webhooks

**What it does:** Monitor Stripe webhook events and their processing status.

**What you see:**
- Recent webhook events (last 100 by default)
- Event type (e.g., `checkout.session.completed`)
- Processing status (`pending`, `processed`, `failed`)
- Error message (if failed)
- Stripe event ID (for looking up in Stripe Dashboard)
- Timestamp

**Common tasks:**
- **Find failed webhooks:** Filter by `status = failed`
- **Re-deliver a failed webhook:** Click "Resend" (links to Stripe Dashboard for the event)
- **Check for duplicate events:** If you see the same `stripe_event_id` processed twice, there's a bug — should be prevented by idempotency logic

**Troubleshooting:**
- All webhooks failing? → check `STRIPE_WEBHOOK_SECRET` in Supabase secrets
- Stuck in `pending`? → the Edge Function may have timed out; check `supabase functions logs stripe-webhook`

---

### 2.7 System

**What it does:** Live connectivity check of all backend tables and Edge Functions.

**What you see:**
- Green ✅ / Red ❌ status for each table (licenses, customers, promo_codes, etc.)
- Supabase project URL and connection status
- Edge Function deployment status
- Last checked timestamp

**Common tasks:**
- **Check after deployment:** Verify all systems are green before announcing a release
- **Diagnose intermittent issues:** Red indicators here point to Supabase connectivity problems

**Troubleshooting:**
- All red? → Supabase may be having an outage; check [status.supabase.com](https://status.supabase.com)
- One table red? → that specific table may have an RLS policy blocking access, or the table doesn't exist (check migration history)

---

### 2.8 Audit Log

**What it does:** Immutable log of all admin-initiated changes.

**What you see:**
- Action type (e.g., `license.revoke`, `promo.create`, `promo.update`)
- Actor (admin identifier or IP)
- Before and after values (sensitive fields are SHA-256 hashed)
- Timestamp
- IP address

**Common tasks:**
- **Review recent changes:** See all admin actions in the last 24 hours
- **Investigate a suspicious change:** Search by action type or actor
- **Compliance audit:** Export for audit trail requirements

> The audit log is append-only — rows are never updated or deleted by the application. If you need to investigate a specific event, filter by `action` and `created_at`.

---

## 3. Promo Code Workflow

### 3.1 Create a Promo Code

**From the dashboard:**

1. Go to the **Promos** page
2. Click **+ New Promo**
3. Fill in the form:

| Field | Required | Description |
|-------|----------|-------------|
| **Code** | ✅ | 3–20 chars, uppercase letters/numbers/dash/underscore. Example: `LAUNCH50` |
| **Type** | ✅ | One of 4 types (see below) |
| **Value** | ✅ | Integer — meaning depends on type |
| **Tier** | ❌ | Leave blank for all tiers, or pick one to restrict |
| **Expires At** | ❌ | ISO date when code stops working. Leave blank = never expires |
| **Max Uses** | ❌ | Integer limit on redemptions. Leave blank = unlimited |
| **Description** | ❌ | Internal note — not shown to customers |

4. Click **Create**

The code is immediately active and ready for customers to use at checkout.

**From the command line (API):**

```bash
curl -X POST \
  https://YOUR_PROJECT.supabase.co/functions/v1/admin-generate-promo \
  -H "Authorization: Bearer $ADMIN_API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "LAUNCH50",
    "type": "discount_percent",
    "value": 50,
    "description": "Launch promo — 50% off",
    "expires_at": "2026-12-31T23:59:59Z",
    "max_uses": 100
  }'
```

---

### 3.2 Promo Type Examples

There are 4 promo types. Here is a concrete example for each:

#### Type 1: `discount_percent` — Percentage discount at checkout

Give customers a percentage off the plan price. The discount is applied as a Stripe coupon.

```json
{
  "code": "SUMMER20",
  "type": "discount_percent",
  "value": 20,
  "description": "20% off summer sale — all tiers",
  "expires_at": "2026-09-01T00:00:00Z"
}
```

- `value: 20` = 20% off
- Customer sees the discounted price in Stripe Checkout
- Works for any tier (no `tier` restriction set)

---

#### Type 2: `discount_fixed` — Fixed dollar amount off

Give customers a fixed dollar amount off. **Important: `value` is in cents.**

```json
{
  "code": "PRO20",
  "type": "discount_fixed",
  "value": 2000,
  "tier": "pro",
  "description": "$20 off the Pro plan for newsletter subscribers",
  "max_uses": 50
}
```

- `value: 2000` = $20.00 (2000 cents)
- Only works on the `pro` tier (will fail for `starter` or `enterprise`)
- Limited to 50 redemptions

---

#### Type 3: `trial_extension` — Extended free trial

Extend the customer's trial period by N days. No payment required for the extension period.

```json
{
  "code": "TRIAL30",
  "type": "trial_extension",
  "value": 30,
  "tier": "starter",
  "description": "30-day extended trial for conference attendees"
}
```

- `value: 30` = 30 extra days added to the trial
- Restricted to `starter` tier only
- No expiry date set — code is valid until deactivated

---

#### Type 4: `unlimited_trial` — Unlimited access, no payment

Grant unlimited trial access with no payment required. Use sparingly for partners and evaluators.

```json
{
  "code": "PARTNER2026",
  "type": "unlimited_trial",
  "value": 0,
  "description": "Unlimited trial for approved partners",
  "max_uses": 10
}
```

- `value` is ignored for this type (use `0`)
- License is created with `status = active` and no `expires_at`
- Limited to 10 uses — hand out codes carefully

---

### 3.3 Edit, Deactivate, Delete

#### Edit a promo

1. Go to Promos page
2. Click the pencil icon on the promo row
3. Update any fields (you can't change the `code` string itself after creation)
4. Click **Save**

You can edit:
- Description
- Expiry date (extend or set/remove)
- Max uses (increase or remove limit)
- Active status
- Tier restriction

#### Deactivate a promo (stop new redemptions, keep history)

**Via dashboard:** Click the Active toggle on the promo row — it will go grey.

**Via API:**
```bash
curl -X PATCH \
  "https://YOUR_PROJECT.supabase.co/rest/v1/promo_codes?code=eq.LAUNCH50" \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"active": false}'
```

> **Recommended:** Deactivate instead of delete. Deactivating preserves the audit trail and prevents future redemptions without breaking references to the code from existing licenses.

#### Delete a promo (removes the code entirely)

**Via dashboard:** Click the trash icon on the promo row.

**Via API:**
```bash
curl -X DELETE \
  "https://YOUR_PROJECT.supabase.co/rest/v1/promo_codes?code=eq.TEST_CODE" \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY"
```

> ⚠️ **Warning:** Deleting a promo code does not revoke any licenses that used it. Existing licenses will have a dangling `promo_code_id` reference. Run `scripts/db-integrity-check.sql` after deletion to verify.

---

### 3.4 Monitor Promo Usage

#### In the dashboard

The Promos page shows the `used_count / max_uses` column for every code. Keep an eye on:
- Codes approaching their `max_uses` limit — create a follow-up code in advance
- Codes expiring in < 7 days — decide whether to extend or let them expire
- Unusually high redemption rates — may indicate a leaked code

#### Via SQL

```sql
-- All active codes with usage and expiry status
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

#### Investigate a suspected leaked code

```sql
-- All licenses redeemed with code X in the last 24 hours
SELECT
    l.id, l.tier, l.status, l.created_at,
    c.email, c.stripe_customer_id
FROM licenses l
JOIN customers c ON l.customer_id = c.id
JOIN promo_codes p ON l.promo_code_id = p.id
WHERE p.code = 'SUSPECT_CODE'
  AND l.created_at > NOW() - INTERVAL '24 hours'
ORDER BY l.created_at DESC;
```

If you see suspicious redemptions, deactivate the code immediately and investigate each license.

---

## 4. License Management

### 4.1 View and Search Licenses

Go to the **Licenses** page.

**Search options:**
- Type a customer email, name, or license key prefix in the search box
- Use the **Status** dropdown: `all`, `active`, `expired`, `cancelled`, `revoked`, `past_due`
- Use the **Tier** dropdown: `all`, `starter`, `pro`, `pro_team`, `enterprise`

Each row shows:
- License key (first 12 chars, then `…` for security)
- Customer email
- Tier
- Status (colour-coded badge)
- Expiry date
- Applied promo code

---

### 4.2 Revoke a License

**Use case:** Fraud, chargeback, policy violation, or security incident.

**Via dashboard:**
1. Find the license on the Licenses page
2. Click **Revoke**
3. Confirm the dialog

**Effect:** `status` is set to `revoked`. The SDK immediately returns `{valid: false}` for this key — there is no cache to wait for.

**Via SQL (bulk revoke):**
```sql
-- Revoke a single license
UPDATE licenses
SET status = 'revoked', updated_at = NOW()
WHERE id = 'license-uuid-here';

-- Revoke all licenses for a customer
UPDATE licenses
SET status = 'revoked', updated_at = NOW()
WHERE customer_id = (SELECT id FROM customers WHERE email = 'bad-actor@example.com')
  AND status = 'active';
```

**Verify revocation:**
```bash
curl -X POST https://YOUR_PROJECT.supabase.co/functions/v1/validate-license \
  -H "Content-Type: application/json" \
  -d '{"license_key": "asv1_the_revoked_key"}'
# Expected: {"valid": false, "error": "License is revoked"}
```

---

### 4.3 Extend a License

**Use case:** Goodwill extension, support resolution, or promo grant.

**Via dashboard:**
1. Find the license on the Licenses page
2. Click the license to open the detail view
3. Edit the **Expiry Date** field
4. Click **Save**

**Via SQL:**
```sql
-- Extend by 30 days from now
UPDATE licenses
SET expires_at = NOW() + INTERVAL '30 days', updated_at = NOW()
WHERE id = 'license-uuid-here';

-- Extend by 30 days from current expiry (doesn't shorten if already extended)
UPDATE licenses
SET expires_at = GREATEST(expires_at, NOW()) + INTERVAL '30 days', updated_at = NOW()
WHERE id = 'license-uuid-here';
```

---

### 4.4 View Validations

The **Licenses** detail view shows recent validation events for a specific license key. This includes:
- Timestamp of each validation
- IP address
- Result (valid/invalid)
- Error reason (if invalid)

This is useful for debugging SDK integration issues.

---

## 5. Audit Log

The **Audit Log** page (accessible from the sidebar) shows all admin-initiated changes in reverse chronological order.

**What gets logged:**
- Every license revocation or status change
- Every promo code creation, update, or deletion
- Admin login events
- Manual license extensions

**Each log entry contains:**
- `action` — what happened (e.g., `license.revoke`)
- `actor` — who did it (admin identifier or IP)
- `before` / `after` — the values before and after the change
- `ip` — source IP address
- `created_at` — timestamp

**Reading the audit log:**

Look for `license.revoke` entries when a customer disputes a revocation. The `before` field shows the license status before the change, and `after` shows what it was set to.

> Sensitive fields (API keys, secrets, license keys) are shown as SHA-256 hashes in the audit log, not as plaintext.

---

## 6. Troubleshooting Admin Issues

### Dashboard shows "401 Unauthorized" or blank data

1. Click the **Settings** icon (gear) in the top right
2. Verify the Supabase URL format: `https://YOUR_PROJECT_REF.supabase.co`
3. Re-enter the **Supabase Service Role Key** (it starts with `eyJ`)
4. Re-enter the **Admin API Secret** (should be a 64-char hex string)
5. Click **Save & Connect**

**Quick test via curl:**
```bash
curl https://YOUR_PROJECT.supabase.co/rest/v1/licenses?limit=1 \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY"
```
If this returns `[]` or a license object, your credentials are correct.

---

### "Create promo" returns 401

The `ADMIN_API_SECRET` in the dashboard settings doesn't match the value in Supabase secrets.

1. Check what's in Supabase:
   ```bash
   supabase secrets list | grep ADMIN_API_SECRET
   ```
2. Compare with what's in your `.env`
3. If they differ, either update the Supabase secret or re-enter the correct value in the dashboard settings

---

### Dashboard not loading (blank white screen)

1. Open browser DevTools → Console tab
2. Look for JavaScript errors
3. Ensure you're accessing `http://localhost:8080/admin` (with `/admin` path)
4. Ensure the Python server is still running (check the terminal)

---

### "Promo code already exists" when creating

The code name must be unique. Either:
- Use a different code name
- Delete the existing code first (if it was created by mistake)
- The 409 response body includes the ID of the existing code if you want to look it up

---

For more detailed troubleshooting, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

For deployment setup, see [DEPLOYMENT.md](DEPLOYMENT.md).

For promo code API details, see [PROMO_CODE_GUIDE.md](PROMO_CODE_GUIDE.md).
