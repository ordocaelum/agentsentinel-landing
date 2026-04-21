# AgentSentinel Admin Dashboard — Comprehensive Guide

> **Audience:** Developers, DevOps engineers, and system administrators responsible for operating the AgentSentinel admin dashboard and backend infrastructure.

---

## Table of Contents

1. [Admin Dashboard](#1-admin-dashboard)
   - [Overview](#11-overview)
   - [Architecture](#12-architecture)
   - [Pages and Components](#13-pages-and-components)
   - [Authentication Model](#14-authentication-model)
   - [API Client](#15-api-client)
   - [Promo Code Generation Workflow](#16-promo-code-generation-workflow)
2. [Supabase Backend](#2-supabase-backend)
   - [Database Schema Overview](#21-database-schema-overview)
   - [Migration History](#22-migration-history)
   - [Edge Functions Reference](#23-edge-functions-reference)
   - [Authentication and Security](#24-authentication-and-security)
   - [Stripe Integration and Webhook Handling](#25-stripe-integration-and-webhook-handling)
   - [License Validation System](#26-license-validation-system)
3. [Launch Instructions](#3-launch-instructions)
   - [Prerequisites](#31-prerequisites)
   - [Local Development Setup](#32-local-development-setup)
   - [Supabase CLI Configuration](#33-supabase-cli-configuration)
   - [Database Migrations](#34-database-migrations)
   - [Environment Variables and Secrets](#35-environment-variables-and-secrets)
   - [Edge Function Deployment](#36-edge-function-deployment)
   - [Stripe Webhook Configuration](#37-stripe-webhook-configuration)
   - [Testing and Verification](#38-testing-and-verification)
4. [System Architecture](#4-system-architecture)
   - [Data Flow Architecture](#41-data-flow-architecture)
   - [Component Interactions](#42-component-interactions)
   - [Request / Response Patterns](#43-request--response-patterns)
   - [Security Model](#44-security-model)
   - [Error Handling and Recovery](#45-error-handling-and-recovery)

---

## 1. Admin Dashboard

### 1.1 Overview

The AgentSentinel Admin Dashboard is a **browser-based Single-Page Application (SPA)** that provides full operational visibility and control over the AgentSentinel backend. It is served by the Python `agentsentinel.dashboard.server` module and accessed at the `/admin` path.

Key capabilities at a glance:

| Capability | Description |
|---|---|
| Real-time KPIs | Active licenses, users, revenue, webhook health |
| License Management | View, revoke, and search all issued license keys |
| Promo Code Engine | Generate and manage promotional codes with usage caps |
| User Management | Browse customer records linked to Stripe |
| Analytics | Validation trends and per-tier breakdowns |
| Webhook Monitor | Inspect and replay Stripe webhook events |
| System Health | Live connectivity checks against every backend table |
| Audit Log | Immutable record of all admin-initiated changes |

The dashboard communicates exclusively with the **Supabase REST API** (`/rest/v1/`) and the **Supabase Edge Functions** (`/functions/v1/`) using the project's service-role key, which is stored in `sessionStorage` and cleared when the browser tab closes.

---

### 1.2 Architecture

```
browser (admin SPA)
       │
       │  HTTP (Supabase REST API / Edge Functions)
       ▼
 Supabase project
  ├── REST API (/rest/v1/*)     ← direct table reads/writes (service-role key)
  └── Edge Functions (/functions/v1/*)
        ├── admin-generate-promo  ← promo creation (requires ADMIN_API_SECRET)
        ├── validate-license
        ├── stripe-webhook
        ├── checkout-team
        ├── create-billing-session
        ├── customer-portal
        ├── send-portal-otp
        └── validate-promo
```

**SPA module tree:**

```
static/admin/
├── index.html              ← SPA shell (setup screen + app shell)
├── css/
│   └── admin.css           ← Dark-theme design system
└── js/
    ├── app.js              ← Router / boot controller (AdminApp class)
    ├── api.js              ← Supabase REST API client (CRUD helpers)
    ├── components/
    │   ├── notifications.js ← Toast notification system
    │   └── modal.js         ← Confirm / prompt dialog
    ├── utils/
    │   ├── auth.js          ← Config persistence & credential verification
    │   ├── format.js        ← Currency, date, badge formatters
    │   └── validation.js    ← Form input validators
    └── pages/
        ├── overview.js      ← KPI dashboard & system health
        ├── licenses.js      ← License management table
        ├── promos.js        ← Promo code CRUD
        ├── users.js         ← Customer records browser
        ├── metrics.js       ← Analytics charts
        ├── webhooks.js      ← Stripe webhook event viewer
        ├── system.js        ← System configuration
        └── audit.js         ← Admin audit log
```

**Routing** is hash-based (`#overview`, `#licenses`, etc.). The `AdminApp` class lazy-loads each page module on demand using dynamic `import()`:

```javascript
const PAGES = {
  overview: () => import('./pages/overview.js'),
  licenses: () => import('./pages/licenses.js'),
  promos:   () => import('./pages/promos.js'),
  users:    () => import('./pages/users.js'),
  metrics:  () => import('./pages/metrics.js'),
  webhooks: () => import('./pages/webhooks.js'),
  system:   () => import('./pages/system.js'),
  audit:    () => import('./pages/audit.js'),
};
```

---

### 1.3 Pages and Components

#### Overview (`#overview`)

Renders real-time KPIs sourced from `dashboard_metrics` and live counts from `licenses`, `promo_codes`, and `webhook_events`. Displays:

- 8 KPI cards (active licenses, users, today's revenue, monthly revenue, promo codes used, failed webhooks, etc.)
- System status panel with connectivity checks against each backend table
- License tier breakdown bar chart (free / pro / team / enterprise)
- Recent activity feed

#### Licenses (`#licenses`)

Full management UI for the `licenses` table:

- Paginated, searchable, filterable table
- Per-row actions: view details, revoke, copy license key
- Status badges (active / revoked / expired / cancelled)
- Tier badges with colour coding

#### Promos (`#promos`)

CRUD interface for the `promo_codes` table backed by the `admin-generate-promo` Edge Function:

- Create form with type, value, tier restriction, expiry, usage cap
- Active/inactive toggle
- Usage counter display
- Inline delete with confirmation

#### Users (`#users`)

Read-only browser over the `customers` table:

- Search by email or Stripe customer ID
- Linked license count per customer
- Quick link to Stripe dashboard per customer

#### Metrics (`#metrics`)

Trend charts built from `license_validations` and `dashboard_metrics`:

- Validation volume over time
- Revenue trends
- Per-tier distribution

#### Webhooks (`#webhooks`)

Inspection view for the `webhook_events` table:

- Filter by event type and processed status
- Expand raw Stripe payload
- Replay / reprocess button (triggers re-send to relevant Edge Function)

#### System (`#system`)

Read-only system configuration and environment status panel.

#### Audit (`#audit`)

Immutable log view over the `admin_logs` table. Displays who performed which action on which entity, with before/after diffs.

---

### 1.4 Authentication Model

The dashboard uses a **two-credential setup screen** that is shown on first visit (when no config exists in `localStorage`/`sessionStorage`).

| Field | Storage | Purpose |
|---|---|---|
| Supabase Project URL | `localStorage` | Base URL for all REST API calls |
| Service-Role Key | `sessionStorage` | Authenticates all REST API calls; cleared on tab close |
| Admin API Secret | `sessionStorage` | Bearer token for `admin-generate-promo` Edge Function |

Credential verification is performed by attempting a minimal `GET /rest/v1/promo_codes?limit=1` request with the supplied key. The dashboard only advances to the main app shell if the request succeeds (HTTP 200).

```
┌─────────────────────────────────────────┐
│           Setup Screen                  │
│  • Supabase URL (localStorage)          │
│  • Service-Role Key (sessionStorage)    │
│  • Admin API Secret (sessionStorage)    │
│                                         │
│  [🚀 Connect & Enter Dashboard]         │
└──────────────────┬──────────────────────┘
                   │ verifyAdminAccess() → GET /rest/v1/promo_codes
                   │ success
                   ▼
┌─────────────────────────────────────────┐
│           Admin App Shell               │
│  Sidebar ← hash-based router → Pages   │
└─────────────────────────────────────────┘
```

> **Security note:** The service-role key is stored in `sessionStorage` only — it is never persisted to disk and is cleared automatically when the browser tab closes. It is never sent anywhere except directly to your own Supabase project URL.

---

### 1.5 API Client

`js/api.js` is a thin wrapper around `fetch` that provides typed CRUD helpers against the Supabase REST API. All requests are authenticated with the service-role key.

```javascript
// Read licenses with filter
const licenses = await get('licenses', 'status=eq.active&order=created_at.desc&limit=50');

// Create promo code (via Edge Function, not direct insert)
const promo = await promoAPI.create({ code, type, value, ... });

// Revoke license
await patch('licenses', licenseId, { status: 'revoked' });
```

Named API namespaces:

| Export | Tables / endpoints |
|---|---|
| `metricsAPI` | `dashboard_metrics` |
| `licensesAPI` | `licenses` + `customers` (join) |
| `promoAPI` | `admin-generate-promo` Edge Function + `promo_codes` table |
| `usersAPI` | `customers` |
| `webhooksAPI` | `webhook_events` |
| `auditAPI` | `admin_logs` |

---

### 1.6 Promo Code Generation Workflow

Promo codes are created via the `admin-generate-promo` Edge Function — not by writing directly to the `promo_codes` table — to enforce server-side validation and audit logging.

**Step-by-step flow:**

```
Admin fills promo form in browser
          │
          │ POST /functions/v1/admin-generate-promo
          │ Authorization: Bearer <ADMIN_API_SECRET>
          │ Body: { code, type, value, tier?, max_uses?, expires_at?, description? }
          ▼
admin-generate-promo Edge Function
  1. Verify Bearer token === ADMIN_API_SECRET
  2. Validate body: code (3-64 chars, alphanumeric/dash/underscore),
                   type (discount_percent|discount_fixed|trial_extension|unlimited_trial),
                   value (non-negative integer; ≤100 for discount_percent),
                   expires_at (future ISO 8601 if provided)
  3. INSERT INTO promo_codes ...
  4. Return 201 with the created row
          │
          ▼
Browser receives created promo code → refreshes promo table
```

**Promo code types:**

| Type | `value` meaning | Example |
|---|---|---|
| `discount_percent` | Percentage off (0-100) | `LAUNCH20` -> 20% off |
| `discount_fixed` | Amount off in cents | `SAVE500` → $5.00 off |
| `trial_extension` | Extra trial days | `EXTRA14` → +14 days |
| `unlimited_trial` | Removes trial limits | `VIPACCESS` |

---

## 2. Supabase Backend

### 2.1 Database Schema Overview

The database consists of **10 core tables** across logical groups:

#### Core Business Tables

| Table | Purpose |
|---|---|
| `customers` | Customer records linked to Stripe (`stripe_customer_id`) |
| `licenses` | License keys, tier, status, usage limits, Stripe subscription reference |
| `promo_codes` | Promotional codes with type, value, expiry, usage tracking |
| `portal_otps` | Single-use OTP hashes for customer portal authentication |

#### Audit and Analytics Tables

| Table | Purpose |
|---|---|
| `webhook_events` | Immutable log of every incoming Stripe webhook event |
| `license_validations` | Analytics record of every SDK license validation call (stores SHA-256 key hash, never plaintext) |
| `admin_logs` | Immutable audit trail of all admin dashboard actions |
| `dashboard_metrics` | Cached KPI values (`active_licenses`, `revenue_today`, etc.) |

#### Key Schema Details

**`licenses` table columns:**

```sql
id UUID PRIMARY KEY
customer_id UUID → customers(id)
license_key TEXT UNIQUE           -- e.g. asv1_... or as_pro_...
tier TEXT                         -- 'free' | 'pro' | 'team' | 'enterprise'
status TEXT                       -- 'active' | 'revoked' | 'expired' | 'cancelled'
stripe_subscription_id TEXT
stripe_price_id TEXT
agents_limit INTEGER DEFAULT 1
events_limit INTEGER DEFAULT 1000
expires_at TIMESTAMP WITH TIME ZONE
cancelled_at TIMESTAMP WITH TIME ZONE
promo_code_id UUID → promo_codes(id)
discount_type TEXT                -- 'percent' | 'fixed' | 'trial'
discount_value INTEGER DEFAULT 0
promo_applied_at TIMESTAMP WITH TIME ZONE
```

**`promo_codes` table columns:**

```sql
id UUID PRIMARY KEY
code TEXT UNIQUE                  -- uppercase, alphanumeric/dash/underscore
type TEXT                         -- 'discount_percent' | 'discount_fixed' | 'trial_extension' | 'unlimited_trial'
value INTEGER                     -- percent, cents, or days depending on type
description TEXT
tier TEXT                         -- NULL = all tiers
active BOOLEAN DEFAULT true
expires_at TIMESTAMP WITH TIME ZONE
max_uses INTEGER                  -- NULL = unlimited
used_count INTEGER DEFAULT 0
created_by TEXT
```

---

### 2.2 Migration History

All migrations are located in `supabase/migrations/` and applied in order.

| # | File | What it does |
|---|---|---|
| 001 | `001_initial_schema.sql` | Core tables: `customers`, `licenses`, `webhook_events`, `license_validations`. Indexes, RLS policies, helper functions |
| 002 | `002_update_keygen.sql` | Updates license key generation logic |
| 003 | `003_pro_team_seats.sql` | Adds per-seat support for Pro Team tier (seat count column) |
| 004 | `004_fix_tier_constraint.sql` | Fixes tier CHECK constraint to include all valid tier values |
| 005 | `005_portal_otps.sql` | Creates `portal_otps` table for two-step email OTP authentication flow |
| 006 | `006_licenses_updated_at.sql` | Adds `updated_at` trigger to `licenses` table |
| 007 | `007_data_retention_and_gdpr.sql` | Data retention policies and GDPR-related cleanup functions |
| 007a | `007a_license_validations_hash.sql` | Adds `license_key_hash` column to `license_validations`; replaces plaintext key storage |
| 008 | `008_portal_otps_unique_email.sql` | Adds unique constraint on `portal_otps.email` to prevent duplicate OTP rows |
| 009 | `009_upsert_customer_fn.sql` | Adds `upsert_customer()` PostgreSQL function used by the webhook handler |
| 010 | `010_add_promo_codes.sql` | Creates `promo_codes` table; adds promo columns to `licenses` |
| 011 | `011_admin_tables.sql` | Creates `admin_logs` and `dashboard_metrics` tables with seeded metric keys |

**Applying all migrations:**

```bash
supabase db push
```

---

### 2.3 Edge Functions Reference

All Edge Functions run on Deno and are located in `supabase/functions/`. Shared code lives in `supabase/functions/_shared/`.

#### `stripe-webhook`

**Trigger:** Stripe webhook POST events  
**Path:** `POST /functions/v1/stripe-webhook`  
**Auth:** Stripe signature verification (`STRIPE_WEBHOOK_SECRET`)

Handles:

| Stripe Event | Action |
|---|---|
| `checkout.session.completed` | Upserts customer, generates HMAC-signed license key, sends license email via Resend |
| `customer.subscription.deleted` | Sets license `status = 'cancelled'` |
| `invoice.payment_failed` | Logs failure to `webhook_events` |

Each event is logged to `webhook_events` with full payload for auditability and replay.

#### `validate-license`

**Path:** `POST /functions/v1/validate-license`  
**Auth:** None (public endpoint)  
**Rate limit:** 20 requests/minute per IP (in-memory sliding window)

```json
// Request
{ "license_key": "asv1_..." }

// Response (valid)
{
  "valid": true,
  "tier": "pro",
  "limits": { "max_agents": 5, "max_events_per_month": 50000 },
  "features": {
    "dashboard_enabled": true,
    "integrations_enabled": true,
    "multi_agent_enabled": false,
    "policy_editor": "basic"
  }
}

// Response (invalid)
{ "valid": false, "error": "Invalid license key" }
```

Accepted key formats:
- `asv1_<payload>_<signature>` — HMAC-signed (current format)
- `as_<tier>_<random>` — legacy format (still supported)

Every validation attempt is logged to `license_validations` using the SHA-256 hash of the key (never plaintext).

#### `admin-generate-promo`

**Path:** `POST /functions/v1/admin-generate-promo`  
**Auth:** `Authorization: Bearer <ADMIN_API_SECRET>` (shared secret)

Creates a new row in `promo_codes`. See [Section 1.6](#16-promo-code-generation-workflow) for the full validation and flow details.

#### `checkout-team`

**Path:** `POST /functions/v1/checkout-team`  
**Auth:** None (public endpoint, called from browser)

Creates a Stripe Checkout Session for the Pro Team per-seat subscription.

```json
// Request
{ "seats": 5 }

// Response
{ "checkoutUrl": "https://checkout.stripe.com/c/pay/cs_live_..." }
```

The session includes:
- Base price (`STRIPE_PRICE_PRO_TEAM_BASE`) × 1
- Per-seat price (`STRIPE_PRICE_PRO_TEAM_SEAT`) × `seats`

#### `create-billing-session`

**Path:** `POST /functions/v1/create-billing-session`  
**Auth:** HMAC-signed `portal_token`

Creates a Stripe Customer Portal session URL for an existing subscriber to manage their billing, update payment methods, and cancel/modify subscriptions.

#### `customer-portal`

**Path:** `POST /functions/v1/customer-portal`  
**Auth:** Email + OTP (two-step verification via `portal_otps` table)

Returns customer billing and license data after verifying a valid OTP.

#### `send-portal-otp`

**Path:** `POST /functions/v1/send-portal-otp`

Generates a 6-digit OTP, stores its SHA-256 hash in `portal_otps`, and sends the code to the customer's email via Resend. Automatically cleans up expired OTP rows before inserting.

#### `validate-promo`

**Path:** `POST /functions/v1/validate-promo`

Validates a promo code before checkout. Checks: existence, `active` flag, expiry, and usage cap.

---

### 2.4 Authentication and Security

#### Row Level Security (RLS)

Every table has RLS enabled. The default deny-all policy means no unauthenticated client can read or write data. Only the **service-role key** (used exclusively by Edge Functions and the admin dashboard) bypasses RLS.

```sql
-- Pattern used on every table
ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on <table>" ON <table>
  FOR ALL USING (auth.role() = 'service_role');
```

#### License Key Signing

License keys use two formats:

1. **Legacy** (`as_<tier>_<random>`) — validated by prefix match against `VALID_TIERS`
2. **HMAC-signed** (`asv1_<payload>_<sig>`) — generated and verified using `AGENTSENTINEL_LICENSE_SIGNING_SECRET`

The signing secret must match between:
- The `stripe-webhook` Edge Function (generates keys on checkout)
- The Python and TypeScript SDKs (verify keys offline/online)
- The `validate-license` Edge Function (server-side verification)

#### Admin API Secret

The `admin-generate-promo` function is protected by a shared secret (`ADMIN_API_SECRET`) passed as a Bearer token. This secret is stored as a Supabase Edge Function secret and entered manually in the admin dashboard setup screen (stored in `sessionStorage`).

Generate a strong secret:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

#### OTP-based Portal Authentication

The customer portal uses a two-step flow to avoid storing passwords:

1. Customer submits email → `send-portal-otp` generates and emails a 6-digit code (hash stored in `portal_otps`, TTL = 10 minutes)
2. Customer submits email + code → `customer-portal` hashes the code, compares with stored hash, deletes the row (single-use), returns portal data

---

### 2.5 Stripe Integration and Webhook Handling

#### Supported Stripe Events

| Event | Handler | Effect |
|---|---|---|
| `checkout.session.completed` | `stripe-webhook` | Create customer + license, send email |
| `customer.subscription.deleted` | `stripe-webhook` | Cancel license |
| `invoice.payment_failed` | `stripe-webhook` | Log failure |

#### Webhook Security

Every incoming Stripe webhook is verified using `stripe.webhooks.constructEvent()` with the `STRIPE_WEBHOOK_SECRET`. Requests with invalid signatures are rejected with HTTP 400.

#### License Generation on Checkout

When `checkout.session.completed` fires:

```
stripe-webhook receives event
  │
  ├── Verify Stripe signature
  ├── Log raw event to webhook_events (idempotency check on stripe_event_id)
  ├── Extract customer email, subscription ID, price ID
  ├── Map price ID → tier using PRICE_TO_TIER map
  ├── Upsert customer record (upsert_customer() PostgreSQL function)
  ├── Generate HMAC-signed license key (asv1_...)
  ├── Insert license row
  └── Send license key email via Resend API
```

#### Pro Team Seat Count

For Pro Team subscriptions, the seat count is extracted from the subscription item matching `STRIPE_PRICE_PRO_TEAM_SEAT`. The `agents_limit` on the license is set accordingly.

---

### 2.6 License Validation System

The `validate-license` Edge Function is called by the Python and TypeScript SDKs on startup and periodically during runtime.

**Validation checks (in order):**

1. Key format check — must match `asv1_*` or `as_<tier>_*`
2. Database lookup — key must exist in `licenses` table
3. Status check — must be `'active'`
4. Expiry check — `expires_at` must be in the future (if set)
5. Tier integrity check — tier must be in `VALID_TIERS` set

**Audit logging:**

Every validation attempt (success or failure) is logged to `license_validations`:

```sql
license_key_hash TEXT   -- SHA-256 of the license key (never plaintext)
license_id UUID         -- NULL if key not found
is_valid BOOLEAN
validation_source TEXT  -- 'api', 'sdk', etc.
ip_address TEXT
user_agent TEXT
```

---

## 3. Launch Instructions

### 3.1 Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.9 | For running the dashboard server |
| Node.js | ≥ 18 | Required by Supabase CLI |
| Supabase CLI | Latest | `npm install -g supabase` |
| Stripe account | — | For webhook configuration |
| Resend account | — | For transactional email |

---

### 3.2 Local Development Setup

#### 1. Clone and install

```bash
git clone <repo-url>
cd agentsentinel-landing
pip install -e python/
```

#### 2. Start the Python dashboard server

```bash
python -m agentsentinel.dashboard.server
# Dashboard available at: http://localhost:8000
# Admin SPA available at: http://localhost:8000/admin
```

The server is zero-dependency (uses Python's built-in `http.server` module) and serves:
- The local monitoring dashboard at `/`
- The admin SPA at `/admin`
- All REST API endpoints under `/api/`

#### 3. Open the Admin SPA

Navigate to `http://localhost:8000/admin`. You will see the setup screen on first visit.

Enter:
- **Supabase URL:** Your project URL, e.g. `https://your-project-ref.supabase.co`
- **Service-Role Key:** Found in Supabase Dashboard -> Project Settings -> API
- **Admin API Secret:** The value you set with `supabase secrets set ADMIN_API_SECRET=...`

Click **🚀 Connect & Enter Dashboard**.

---

### 3.3 Supabase CLI Configuration

#### Install

```bash
npm install -g supabase
```

#### Login

```bash
supabase login
```

#### Link to your project

```bash
supabase link --project-ref YOUR_PROJECT_REF
```

Find your project reference in the Supabase Dashboard URL: `https://supabase.com/dashboard/project/<YOUR_PROJECT_REF>`.

---

### 3.4 Database Migrations

Apply all 11 migrations to your Supabase project:

```bash
cd supabase
supabase db push
```

Verify the migration state:

```bash
supabase migration list
```

All 11 migrations should show as applied. If any are missing, re-run `supabase db push`.

**Manual verification (run in Supabase SQL editor):**

```sql
-- Check all tables exist
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- Expected tables:
-- admin_logs, customers, dashboard_metrics, licenses,
-- license_validations, portal_otps, promo_codes, webhook_events
```

---

### 3.5 Environment Variables and Secrets

Copy `.env.example` to `.env` for local reference (never commit `.env`):

```bash
cp supabase/.env.example supabase/.env
```

Set all secrets in Supabase (used by Edge Functions):

```bash
# Stripe
supabase secrets set STRIPE_SECRET_KEY=sk_live_xxx
supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_xxx

# Stripe Price IDs (copy from Stripe Dashboard → Products)
supabase secrets set STRIPE_PRICE_STARTER=price_xxxxx
supabase secrets set STRIPE_PRICE_PRO=price_xxxxx
supabase secrets set STRIPE_PRICE_PRO_TEAM=price_xxxxx
supabase secrets set STRIPE_PRICE_ENTERPRISE=price_xxxxx
supabase secrets set STRIPE_PRICE_PRO_TEAM_BASE=price_xxxxx
supabase secrets set STRIPE_PRICE_PRO_TEAM_SEAT=price_xxxxx

# Email
supabase secrets set RESEND_API_KEY=re_xxx

# License signing (must match Python/TypeScript SDK config)
supabase secrets set AGENTSENTINEL_LICENSE_SIGNING_SECRET=your_signing_secret

# Admin dashboard protection
supabase secrets set ADMIN_API_SECRET=your_strong_admin_secret

# Site URL (for Stripe redirect)
supabase secrets set SITE_BASE_URL=https://your-domain.com
```

**Generate strong secrets:**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Verify all secrets are set:

```bash
supabase secrets list
```

---

### 3.6 Edge Function Deployment

Deploy all 8 Edge Functions:

```bash
supabase functions deploy stripe-webhook
supabase functions deploy validate-license
supabase functions deploy checkout-team
supabase functions deploy admin-generate-promo
supabase functions deploy create-billing-session
supabase functions deploy customer-portal
supabase functions deploy send-portal-otp
supabase functions deploy validate-promo
```

Or deploy all at once:

```bash
supabase functions deploy
```

Verify deployment:

```bash
supabase functions list
```

All 8 functions should show a `ACTIVE` status.

---

### 3.7 Stripe Webhook Configuration

#### 1. Get your webhook URL

```
https://YOUR_PROJECT_REF.supabase.co/functions/v1/stripe-webhook
```

#### 2. Register in Stripe Dashboard

1. Go to **Stripe Dashboard → Developers → Webhooks**
2. Click **Add endpoint**
3. Enter your webhook URL
4. Select these events:
   - `checkout.session.completed`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
5. Click **Add endpoint**

#### 3. Copy the signing secret

After creating the endpoint, Stripe shows a **Signing secret** (starts with `whsec_`). Set it immediately:

```bash
supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_xxx
```

#### 4. Test the webhook

Use Stripe CLI to send a test event:

```bash
stripe listen --forward-to https://YOUR_PROJECT_REF.supabase.co/functions/v1/stripe-webhook
stripe trigger checkout.session.completed
```

Check the result in Supabase:

```sql
SELECT stripe_event_id, event_type, processed, error_message, created_at
FROM webhook_events
ORDER BY created_at DESC
LIMIT 5;
```

---

### 3.8 Testing and Verification

#### Pre-flight Checklist

- [ ] `supabase db push` completed with all 11 migrations applied
- [ ] All secrets set (`supabase secrets list` shows no empty values)
- [ ] All 8 Edge Functions deployed and active
- [ ] Stripe webhook endpoint registered with correct signing secret
- [ ] Python dashboard server running (`python -m agentsentinel.dashboard.server`)
- [ ] Admin SPA accessible at `http://localhost:8000/admin`
- [ ] Setup screen accepts credentials and enters dashboard
- [ ] Admin API Secret entered in setup screen

#### Verify Database Connectivity

```sql
-- 1. Confirm promo_codes table exists
SELECT EXISTS(
  SELECT 1 FROM information_schema.tables WHERE table_name = 'promo_codes'
) AS table_exists;

-- 2. Check RLS policies
SELECT tablename, policy_name, permissive, roles, qual
FROM pg_policies
WHERE tablename IN ('licenses', 'promo_codes', 'admin_logs', 'webhook_events')
ORDER BY tablename, policy_name;

-- 3. Check metric seed data
SELECT metric_key, metric_value FROM dashboard_metrics ORDER BY metric_key;
```

#### Test License Validation

```bash
curl -X POST https://YOUR_PROJECT_REF.supabase.co/functions/v1/validate-license \
  -H "Content-Type: application/json" \
  -d '{"license_key": "as_pro_test_key_here"}'
```

Expected response:
```json
{ "valid": false, "error": "Invalid license key" }
```
(Returns 404 because the key doesn't exist — this confirms the function is running correctly.)

#### Test Promo Code Creation

```bash
curl -X POST https://YOUR_PROJECT_REF.supabase.co/functions/v1/admin-generate-promo \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ADMIN_API_SECRET" \
  -d '{
    "code": "TESTCODE",
    "type": "discount_percent",
    "value": 10,
    "description": "10% off test code"
  }'
```

Expected: HTTP 201 with the created promo code object.

#### Troubleshooting Guide

| Symptom | Likely Cause | Fix |
|---|---|---|
| `401 Unauthorized` from `admin-generate-promo` | Wrong or missing `ADMIN_API_SECRET` | Re-run `supabase secrets set ADMIN_API_SECRET=...` and refresh the value in the setup screen |
| `404` on any Edge Function | Function not deployed | Run `supabase functions deploy <function-name>` |
| CORS error in browser console | Request origin not allowed | Use the Python dashboard server (`/admin`) so requests go through the server origin |
| `409 Conflict` on promo creation | Code already exists | Choose a different code name |
| `500` from any Edge Function | Missing secret in function environment | Run `supabase secrets list` and verify all required secrets are present |
| Stripe webhook showing as failed | Wrong signing secret | Copy the `whsec_` secret from Stripe webhook endpoint settings and re-run `supabase secrets set STRIPE_WEBHOOK_SECRET=...` |
| Setup screen fails credential check | Service-role key incorrect or wrong project URL | Verify both values in Supabase Dashboard → Project Settings → API |
| `license_validations` not populated | Migration 007a not applied | Run `supabase db push` to apply any missing migrations |

---

## 4. System Architecture

### 4.1 Data Flow Architecture

```
                        ┌──────────────────────────────────────┐
                        │         CUSTOMER FLOWS               │
                        └──────────────────────────────────────┘

  Browser (pricing page)
        │
        │ POST /functions/v1/checkout-team { seats }
        ▼
  checkout-team Edge Function
        │ Creates Stripe Checkout Session
        │ Returns { checkoutUrl }
        ▼
  Stripe Checkout (hosted page)
        │ Customer completes payment
        │ Stripe fires checkout.session.completed
        ▼
  stripe-webhook Edge Function
        │ 1. Verify Stripe signature
        │ 2. Log to webhook_events
        │ 3. Upsert customer record
        │ 4. Generate asv1_ license key (HMAC-SHA256)
        │ 5. Insert license row
        │ 6. Email license key via Resend
        ▼
  Customer receives email with license key

  Customer uses SDK
        │ AgentGuard(license_key=...)
        │ POST /functions/v1/validate-license { license_key }
        ▼
  validate-license Edge Function
        │ Rate limit check (20 req/min/IP)
        │ Format check
        │ DB lookup
        │ Status + expiry check
        │ Log to license_validations (key hash only)
        ▼
  SDK receives { valid, tier, limits, features }


                        ┌──────────────────────────────────────┐
                        │         ADMIN FLOWS                  │
                        └──────────────────────────────────────┘

  Admin Browser (admin SPA)
        │
        ├── GET /rest/v1/licenses          (via service-role key)
        ├── GET /rest/v1/promo_codes
        ├── GET /rest/v1/customers
        ├── GET /rest/v1/webhook_events
        ├── GET /rest/v1/admin_logs
        ├── GET /rest/v1/dashboard_metrics
        │
        └── POST /functions/v1/admin-generate-promo
               Authorization: Bearer <ADMIN_API_SECRET>
               │
               ▼
         admin-generate-promo Edge Function
               │ Auth check
               │ Input validation
               │ INSERT promo_codes
               ▼
         201 Created → promo table refreshes in browser
```

---

### 4.2 Component Interactions

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Repository Layout                             │
│                                                                      │
│  python/agentsentinel/                                               │
│  ├── guard.py            ← AgentGuard (main SDK entry point)         │
│  ├── licensing.py        ← License verification (calls validate-     │
│  │                         license or verifies HMAC offline)         │
│  ├── audit.py            ← Audit event collection                    │
│  ├── cost_tracker.py     ← Token/cost tracking                       │
│  ├── pii.py              ← PII detection and masking                 │
│  ├── policy.py           ← Policy enforcement engine                 │
│  └── dashboard/                                                      │
│      ├── server.py       ← Local monitoring dashboard (HTTP server)  │
│      ├── license_api.py  ← Calls validate-license Edge Function      │
│      └── static/admin/   ← Admin SPA (HTML + vanilla JS)            │
│                                                                      │
│  supabase/                                                           │
│  ├── migrations/         ← 11 ordered SQL migration files            │
│  └── functions/                                                      │
│      ├── _shared/        ← tiers.ts (VALID_TIERS, TIER_LIMITS)       │
│      ├── stripe-webhook/ ← Checkout, cancellation, payment failure   │
│      ├── validate-license/                                           │
│      ├── admin-generate-promo/                                       │
│      ├── checkout-team/                                              │
│      ├── create-billing-session/                                     │
│      ├── customer-portal/                                            │
│      ├── send-portal-otp/                                            │
│      └── validate-promo/                                             │
│                                                                      │
│  typescript/                                                         │
│  └── src/                ← TypeScript SDK with framework integrations │
│      ├── langchain/                                                  │
│      ├── crewai/                                                     │
│      ├── llamaindex/                                                 │
│      ├── openai/                                                     │
│      └── anthropic/                                                  │
└──────────────────────────────────────────────────────────────────────┘
```

---

### 4.3 Request / Response Patterns

#### Supabase REST API (admin dashboard reads/writes)

All requests use the service-role key for authentication:

```
GET  /rest/v1/{table}?{filters}
POST /rest/v1/{table}                         Body: JSON row object
PATCH /rest/v1/{table}?id=eq.{id}            Body: partial update object
DELETE /rest/v1/{table}?id=eq.{id}
```

Common response headers:
- `Content-Range: 0-49/150` — pagination metadata
- `Prefer: count=exact` — request total count in `Content-Range`

#### Edge Function invocations

```
POST /functions/v1/{function-name}
Content-Type: application/json
Authorization: Bearer {key}           ← service-role key OR custom secret
```

All Edge Functions return JSON responses with appropriate HTTP status codes and include CORS headers (`Access-Control-Allow-Origin`).

---

### 4.4 Security Model

| Layer | Mechanism |
|---|---|
| **Database** | Row Level Security (RLS) — deny all by default; service-role bypass only |
| **License keys** | HMAC-SHA256 signatures using `AGENTSENTINEL_LICENSE_SIGNING_SECRET` |
| **Admin API** | Shared secret (`ADMIN_API_SECRET`) as Bearer token |
| **Customer portal** | Time-limited email OTP (6 digits, 10-minute TTL, single-use) |
| **Stripe webhooks** | Signature verification using `STRIPE_WEBHOOK_SECRET` |
| **Audit keys** | License keys stored as SHA-256 hashes in `license_validations` — never plaintext |
| **Browser secrets** | Service-role key in `sessionStorage` only — never `localStorage`, cleared on tab close |
| **Rate limiting** | 20 req/min/IP on `validate-license` (in-memory sliding window) |
| **Input validation** | All Edge Functions validate type, length, and format before any DB operation |
| **Request size limits** | `admin-generate-promo`: 8 KB max; `validate-license`: 1 MB max |

---

### 4.5 Error Handling and Recovery

#### Edge Function Error Taxonomy

| HTTP Code | Meaning | Recovery |
|---|---|---|
| `400 Bad Request` | Invalid input (missing fields, wrong types) | Fix the request body |
| `401 Unauthorized` | Missing or wrong `ADMIN_API_SECRET` | Verify and re-enter the admin secret |
| `403 Forbidden` | License revoked, expired, or cancelled | Check license status in admin dashboard |
| `404 Not Found` | License key or resource does not exist | Verify the key or resource ID |
| `405 Method Not Allowed` | Wrong HTTP method | Use POST for all Edge Function endpoints |
| `409 Conflict` | Duplicate promo code (UNIQUE constraint) | Choose a different code name |
| `413 Payload Too Large` | Request body exceeds size limit | Reduce request body size |
| `429 Too Many Requests` | Rate limit exceeded | Retry after 60 seconds |
| `500 Internal Server Error` | DB error or missing environment secret | Check `supabase secrets list`; check Edge Function logs |

#### Idempotency

The `stripe-webhook` function uses `stripe_event_id` as a UNIQUE key in `webhook_events`. If Stripe retries an event, the insert will fail with `23505` (duplicate key), which is caught and treated as already-processed — preventing double license issuance.

#### Edge Function Logs

View real-time logs for any function:

```bash
supabase functions logs stripe-webhook --tail
supabase functions logs validate-license --tail
supabase functions logs admin-generate-promo --tail
```

#### Database Recovery

If a webhook fires but the license was not created (e.g., a transient DB error), check `webhook_events`:

```sql
SELECT stripe_event_id, event_type, processed, error_message, created_at
FROM webhook_events
WHERE processed = FALSE
ORDER BY created_at DESC;
```

Rows with `processed = FALSE` and a non-null `error_message` indicate failed events that need investigation. Re-deploy the Edge Function and use Stripe's **Retry** button in the webhook endpoint dashboard to replay the event.
