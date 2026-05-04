# AgentSentinel — Setup Guide

> **Canonical setup reference.**  All other setup instructions in this repo
> defer to this document.  If you find a conflict, this file wins.

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Prerequisites](#2-prerequisites)
3. [Mode Matrix — Which Variables Are Required?](#3-mode-matrix)
4. [Variable Reference](#4-variable-reference)
5. [Secret Rotation Runbook](#5-secret-rotation-runbook)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Quick Start

```bash
# 1. Clone and enter the repository
git clone https://github.com/ordocaelum/agentsentinel-landing
cd agentsentinel-landing

# 2. Generate .env files (auto-fills strong secrets for __GENERATE__ placeholders)
./scripts/setup-env.sh

# 3. Fill in the remaining manual entries printed by the script
#    (Stripe keys, Supabase URL, Resend API key, etc.)
$EDITOR .env
$EDITOR supabase/.env

# 4. Validate all required variables
agentsentinel-config-check          # or: python -m agentsentinel.config_check

# 5. Start the admin dashboard
agentsentinel-dashboard             # http://localhost:8080/admin

# 6. Push secrets to Supabase Edge Functions
supabase secrets set --env-file supabase/.env
```

> **Windows users:** replace step 2 with:
> ```powershell
> .\scripts\setup-env.ps1
> ```

---

## 2. Prerequisites

| Tool | Minimum version | Why |
|------|----------------|-----|
| Python | 3.9+ | Admin dashboard + config-check |
| openssl | any | Secret generation in setup-env.sh |
| Supabase CLI | 1.x | Deploying Edge Functions |
| Deno | 1.40+ | Running / testing Edge Functions locally |
| Stripe CLI | any | Forwarding webhooks in local dev |

Install the Python package (includes `agentsentinel-dashboard` and
`agentsentinel-config-check` console scripts):

```bash
pip install -e "python/[dev]"
```

---

## 3. Mode Matrix

The table below shows which environment variables are **required** (✓),
**optional** (○), or **not applicable** (–) for each deployment context.

| Variable | Local dev | CI | Supabase Edge Functions | Production |
|---|:---:|:---:|:---:|:---:|
| `AGENTSENTINEL_LICENSE_SIGNING_SECRET` | ✓ | ✓ | ✓ | ✓ |
| `ADMIN_API_SECRET` | ✓ | ✓ | ✓ | ✓ |
| `SUPABASE_URL` | ○ | ✓ | ✓ | ✓ |
| `SUPABASE_SERVICE_ROLE_KEY` | ○ | ✓ | ✓ | ✓ |
| `SUPABASE_ANON_KEY` | ○ | ✓ | ✓ | ✓ |
| `STRIPE_SECRET_KEY` | ○ | ✓ | ✓ | ✓ |
| `STRIPE_PUBLISHABLE_KEY` | ○ | ✓ | – | ✓ |
| `STRIPE_WEBHOOK_SECRET` | ○ | ✓ | ✓ | ✓ |
| `STRIPE_PRICE_STARTER` | ○ | ✓ | ✓ | ✓ |
| `STRIPE_PRICE_PRO` | ○ | ✓ | ✓ | ✓ |
| `STRIPE_PRICE_PRO_TEAM` | ○ | ✓ | ✓ | ✓ |
| `STRIPE_PRICE_ENTERPRISE` | ○ | ✓ | ✓ | ✓ |
| `STRIPE_PRICE_PRO_TEAM_BASE` | ○ | ✓ | ✓ | ✓ |
| `STRIPE_PRICE_PRO_TEAM_SEAT` | ○ | ✓ | ✓ | ✓ |
| `RESEND_API_KEY` | ○ | ✓ | ✓ | ✓ |
| `SITE_BASE_URL` | ○ | ✓ | ✓ | ✓ |
| `AGENTSENTINEL_DEV` | ○ | ○ | – | ✗ never |
| `AGENTSENTINEL_DEV_MODE` | ○ | ○ | – | ✗ never |
| `AGENTSENTINEL_DASHBOARD_DEBUG` | ○ | ○ | – | ✗ never |
| `AGENTSENTINEL_DASHBOARD_PORT` | ○ | – | – | – |
| `AGENTSENTINEL_DASHBOARD_HOST` | ○ | – | – | – |
| `AGENTSENTINEL_LICENSE_KEY` | ○ | ✓ | – | ✓ |
| `AGENTSENTINEL_LICENSE_API` | ○ | ○ | – | ○ |

**Key:**
- ✓ Required
- ○ Optional / recommended
- – Not applicable
- ✗ Must NOT be set

### Local dev quick-start (minimal .env)

For local dashboard development where you don't need Stripe or Supabase:

```env
AGENTSENTINEL_LICENSE_SIGNING_SECRET=<openssl rand -hex 32>
ADMIN_API_SECRET=<openssl rand -hex 32>
AGENTSENTINEL_DEV=1
```

Set `AGENTSENTINEL_DEV=1` to bypass the paid-licence gate.
**Never set this in production.**

---

## 4. Variable Reference

### `AGENTSENTINEL_LICENSE_SIGNING_SECRET`

- **Purpose:** HMAC-SHA256 signing secret used to generate and verify `asv1_`
  license keys and `portal_token` values.  Must be identical in the Python SDK,
  all Edge Functions, and the admin dashboard.
- **Required:** yes — dev + prod
- **Shape:** 64 hex characters (32 bytes)
- **Generate:** `openssl rand -hex 32`

### `ADMIN_API_SECRET`

- **Purpose:** Bearer token sent by the admin dashboard to protect
  admin-only Edge Function endpoints (e.g. `admin-generate-promo`).
- **Required:** yes — dev + prod
- **Shape:** 64 hex characters (32 bytes)
- **Generate:** `openssl rand -hex 32`

### `SUPABASE_URL`

- **Purpose:** Supabase project REST/realtime URL.  Consumed by every Edge
  Function that calls `createClient()`.
- **Required:** yes — prod + CI
- **Shape:** `https://<project-ref>.supabase.co`
- **Obtain:** Supabase dashboard → project Settings → API

### `SUPABASE_SERVICE_ROLE_KEY`

- **Purpose:** Supabase service-role JWT — bypasses Row-Level Security.
  **Never** expose this to the browser.
- **Required:** yes — prod + CI
- **Shape:** JWT (starts with `eyJ`)
- **Obtain:** Supabase dashboard → project Settings → API → service_role

### `SUPABASE_ANON_KEY`

- **Purpose:** Supabase anonymous JWT — safe to expose in front-end code.
- **Required:** yes — front-end + SDK
- **Shape:** JWT (starts with `eyJ`)
- **Obtain:** Supabase dashboard → project Settings → API → anon public

### `STRIPE_SECRET_KEY`

- **Purpose:** Stripe server-side API key used by Edge Functions.
- **Required:** yes — prod
- **Shape:** `sk_live_…` (live) or `sk_test_…` (test)
- **Obtain:** [Stripe dashboard → API keys](https://dashboard.stripe.com/apikeys)

### `STRIPE_PUBLISHABLE_KEY`

- **Purpose:** Stripe front-end key for Stripe.js checkout.
- **Required:** yes — prod front-end
- **Shape:** `pk_live_…` (live) or `pk_test_…` (test)
- **Obtain:** [Stripe dashboard → API keys](https://dashboard.stripe.com/apikeys)

### `STRIPE_WEBHOOK_SECRET`

- **Purpose:** Verifies the signature of incoming Stripe webhook payloads.
- **Required:** yes — prod (`stripe-webhook` Edge Function)
- **Shape:** `whsec_…`
- **Obtain:** [Stripe dashboard → Webhooks](https://dashboard.stripe.com/webhooks) → select endpoint → signing secret

### `STRIPE_PRICE_STARTER` / `STRIPE_PRICE_PRO` / `STRIPE_PRICE_PRO_TEAM` / `STRIPE_PRICE_ENTERPRISE`

- **Purpose:** Stripe Price IDs used by `stripe-webhook` to map purchase events
  to license tiers.
- **Required:** yes — prod
- **Shape:** `price_…`
- **Obtain:** [Stripe dashboard → Products](https://dashboard.stripe.com/products) → price ID for each tier

### `STRIPE_PRICE_PRO_TEAM_BASE` / `STRIPE_PRICE_PRO_TEAM_SEAT`

- **Purpose:** Pro Team checkout uses a base price + a per-seat price.
  Used by the `checkout-team` Edge Function.
- **Required:** yes — prod
- **Shape:** `price_…`
- **Obtain:** [Stripe dashboard → Products](https://dashboard.stripe.com/products) → Pro Team product

### `RESEND_API_KEY`

- **Purpose:** API key for [Resend](https://resend.com) — sends license delivery
  emails and OTP codes.
- **Required:** yes — prod (`stripe-webhook`, `send-portal-otp`)
- **Shape:** `re_…`
- **Obtain:** [resend.com/api-keys](https://resend.com/api-keys)

### `SITE_BASE_URL`

- **Purpose:** Base URL used to construct Stripe checkout redirect URLs
  (`success_url`, `cancel_url`).
- **Required:** yes — prod
- **Shape:** URL e.g. `https://agentsentinel.net`
- **Obtain:** set to your deployment URL

### `AGENTSENTINEL_DEV`

- **Purpose:** Set to `1` to enable dev-only endpoints in the admin dashboard
  (e.g. `/api/debug/static-status`) and bypass the paid-licence gate.
- **Required:** no — **never set in production**
- **Shape:** `1`

### `AGENTSENTINEL_DEV_MODE`

- **Purpose:** Set to `true` to bypass the paid-licence gate in the Python SDK.
- **Required:** no — **never set in production**
- **Shape:** `true`

### `AGENTSENTINEL_DASHBOARD_DEBUG`

- **Purpose:** Set to `1` for verbose debug logging in the dashboard HTTP server.
- **Required:** no
- **Shape:** `1`

### `AGENTSENTINEL_LICENSE_KEY`

- **Purpose:** License key used by the Python SDK to authenticate the calling
  application.
- **Required:** yes — prod SDK usage
- **Shape:** `asv1_…`, `as_pro_…`, `as_team_…`, `as_ent_…`, `as_starter_…`
- **Obtain:** issued after purchase at [agentsentinel.net/portal](https://agentsentinel.net/portal)

### `AGENTSENTINEL_LICENSE_API`

- **Purpose:** Override the license validation API endpoint (defaults to the
  production endpoint).  Useful for local Supabase testing.
- **Required:** no
- **Shape:** URL
- **Default:** `https://api.agentsentinel.net/v1/license/validate`

---

## 5. Secret Rotation Runbook

### Rotating `ADMIN_API_SECRET`

**Zero-downtime strategy:** deploy the new secret side-by-side with the old one,
then remove the old one once all dashboard sessions have been refreshed.

1. Generate a new secret:
   ```bash
   openssl rand -hex 32
   ```
2. Add the new value to Supabase secrets (Edge Functions pick up new secrets on
   next cold-start, typically within 60 seconds):
   ```bash
   supabase secrets set ADMIN_API_SECRET=<new-value>
   ```
3. Update `.env` and `supabase/.env` locally:
   ```bash
   ./scripts/setup-env.sh --regenerate ADMIN_API_SECRET
   ```
   Or use the script's regenerate flag to update just this key:
   ```bash
   ./scripts/setup-env.sh --regenerate ADMIN_API_SECRET
   ```
4. Update any CI/CD secrets (GitHub Actions, etc.) with the new value.
5. Log out of the admin dashboard and log back in — the new secret will be
   required for all subsequent requests.
6. Verify with `agentsentinel-config-check`.

### Rotating `AGENTSENTINEL_LICENSE_SIGNING_SECRET`

> **Warning:** This invalidates all existing `asv1_`-prefixed (HMAC-signed)
> license keys.  Online-validated keys (`as_pro_…`, etc.) are not affected.

1. Generate a new secret:
   ```bash
   openssl rand -hex 32
   ```
2. **Before** deploying the new secret, export the old secret so you can
   re-sign existing keys if needed:
   ```bash
   # Backup the old value
   OLD_SECRET=$(grep AGENTSENTINEL_LICENSE_SIGNING_SECRET supabase/.env | cut -d= -f2)
   ```
3. Deploy the new secret:
   ```bash
   supabase secrets set AGENTSENTINEL_LICENSE_SIGNING_SECRET=<new-value>
   ./scripts/setup-env.sh --regenerate AGENTSENTINEL_LICENSE_SIGNING_SECRET
   ```
4. Re-issue any `asv1_` keys for active customers (use the admin dashboard or
   the `agentsentinel-keygen` CLI).
5. Update the Python SDK configuration for any deployed applications.
6. Verify with `agentsentinel-config-check`.

---

## 6. Troubleshooting

### `agentsentinel-config-check` shows ✗ MISSING for all Supabase/Stripe vars

If you're running in local dev mode and only want to test the dashboard:

```bash
agentsentinel-config-check --mode dev
```

Dev mode only requires `AGENTSENTINEL_LICENSE_SIGNING_SECRET` and
`ADMIN_API_SECRET`.

### `__GENERATE_HEX_32__` still appears in `.env` after running setup-env.sh

Check that `openssl` is installed and available on your `PATH`:

```bash
openssl version
```

If it's missing, install it (`brew install openssl` / `apt install openssl`) and
re-run `./scripts/setup-env.sh --force`.

### Edge Functions can't read my secrets

Make sure you've pushed the secrets to Supabase:

```bash
supabase secrets set --env-file supabase/.env
```

Then re-deploy the affected functions:

```bash
supabase functions deploy <function-name>
```

### Dashboard returns 401 on admin endpoints

The admin dashboard sends `ADMIN_API_SECRET` as a Bearer token.  Verify:

1. The same value is set in both `.env` (Python dashboard) and Supabase secrets.
2. The sessionStorage entry `asAdminSecret` in your browser matches.
3. Run `agentsentinel-config-check` to confirm the value is present and ≥ 32 chars.
