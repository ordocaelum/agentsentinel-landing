# AgentSentinel Deployment Guide

> **TL;DR:** Deploy the Python admin dashboard in 2 minutes locally, or push Supabase Edge Functions in 5 minutes. This guide covers both, plus the full environment variable checklist.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Deploy the Python Admin Dashboard](#2-deploy-the-python-admin-dashboard)
   - [Local development](#21-local-development)
   - [Remote server (production)](#22-remote-server-production)
   - [Docker](#23-docker)
3. [Deploy Supabase Edge Functions](#3-deploy-supabase-edge-functions)
   - [Prerequisites](#31-prerequisites)
   - [Deploy all functions](#32-deploy-all-functions)
   - [Deploy a single function](#33-deploy-a-single-function)
   - [Push secrets](#34-push-secrets)
4. [Self-Hosted vs Supabase Hosting](#4-self-hosted-vs-supabase-hosting)
5. [Environment Variables Checklist](#5-environment-variables-checklist)
   - [Root `.env` variables](#51-root-env-variables)
   - [Supabase Edge Function secrets](#52-supabase-edge-function-secrets)
6. [Generate Secrets](#6-generate-secrets)
7. [Database Migrations](#7-database-migrations)
8. [Stripe Webhook Setup](#8-stripe-webhook-setup)
9. [Verify Your Deployment](#9-verify-your-deployment)

---

## 1. Architecture Overview

AgentSentinel has three deployment layers:

```
┌─────────────────────────────────────────────────────────────────┐
│  Static Landing Site                                             │
│  index.html, portal.html, pricing-team.html, success.html        │
│  Served by: GitHub Pages / Cloudflare Pages / any CDN           │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS API calls
┌──────────────────────────▼──────────────────────────────────────┐
│  Supabase (managed cloud service)                                │
│  ● PostgreSQL database                                           │
│  ● Edge Functions (Deno runtime):                                │
│      validate-license    — SDK license validation                │
│      stripe-webhook      — Stripe event handler                  │
│      send-portal-otp     — OTP email for portal login            │
│      customer-portal     — Portal data API                       │
│      validate-promo      — Promo code validation                 │
│      admin-generate-promo — Admin promo CRUD                     │
│      checkout-team       — Pro Team checkout session             │
│      create-billing-session — Customer billing portal            │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Local / private HTTP
┌──────────────────────────▼──────────────────────────────────────┐
│  Python Admin Dashboard (optional, self-hosted)                  │
│  python/agentsentinel/dashboard/server.py                        │
│  Default: http://localhost:8080/admin                            │
└─────────────────────────────────────────────────────────────────┘
```

**Key point:** The landing site and Supabase backend are independent. The Python admin dashboard is an operational tool that can run locally — it does not need to be internet-accessible.

---

## 2. Deploy the Python Admin Dashboard

### 2.1 Local Development

**Step 1 — Install:**
```bash
git clone https://github.com/ordocaelum/agentsentinel-landing.git
cd agentsentinel-landing
pip install -e python/
```

**Step 2 — Configure environment:**
```bash
cp .env.example .env
# Edit .env and fill in at minimum:
# ADMIN_API_SECRET=<64-char hex>
# SUPABASE_URL=https://your-project.supabase.co
# SUPABASE_SERVICE_ROLE_KEY=eyJ...
# AGENTSENTINEL_LICENSE_SIGNING_SECRET=<64-char hex>
```

**Step 3 — Start:**
```bash
AGENTSENTINEL_DEV=1 agentsentinel-dashboard
# Open http://localhost:8080/admin
```

Using the one-command script:
```bash
bash scripts/run-admin-dashboard.sh
```

**What `AGENTSENTINEL_DEV=1` does:**
- Bypasses the paid-licence gate so you can use the dashboard without a paid key
- Enables dev-only API endpoints (`/api/promos*`, `/api/debug/*`)
- **Never set this in production**

---

### 2.2 Remote Server (Production)

For a team that needs shared access to the admin dashboard.

**Recommended approach:** Run on a private server behind a VPN or IP allowlist.

**Step 1 — Set up the server:**
```bash
# On the server (Ubuntu/Debian example)
sudo apt install python3-pip python3-venv
git clone https://github.com/ordocaelum/agentsentinel-landing.git
cd agentsentinel-landing
python3 -m venv venv
source venv/bin/activate
pip install -e python/
```

**Step 2 — Create a systemd service:**
```ini
# /etc/systemd/system/agentsentinel-dashboard.service
[Unit]
Description=AgentSentinel Admin Dashboard
After=network.target

[Service]
User=agentsentinel
WorkingDirectory=/opt/agentsentinel-landing
ExecStart=/opt/agentsentinel-landing/venv/bin/agentsentinel-dashboard
Restart=always
EnvironmentFile=/etc/agentsentinel/.env
Environment=AGENTSENTINEL_DASHBOARD_HOST=127.0.0.1
Environment=AGENTSENTINEL_DASHBOARD_PORT=8080

[Install]
WantedBy=multi-user.target
```

**Step 3 — Set up nginx reverse proxy with TLS:**
```nginx
server {
    listen 443 ssl;
    server_name admin.yourcompany.com;

    ssl_certificate     /etc/letsencrypt/live/admin.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/admin.yourcompany.com/privkey.pem;

    # IP allowlist — restrict to known admin IPs
    allow 1.2.3.4;
    deny all;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Step 4 — Enable and start:**
```bash
sudo systemctl enable agentsentinel-dashboard
sudo systemctl start agentsentinel-dashboard
sudo systemctl status agentsentinel-dashboard
```

> ⚠️ **Never** bind to `0.0.0.0` without TLS and an IP allowlist. The dashboard holds your Supabase service-role key and `ADMIN_API_SECRET`.

---

### 2.3 Docker

```dockerfile
# Dockerfile (place in repo root)
FROM python:3.12-slim

WORKDIR /app
COPY python/ ./python/

RUN pip install --no-cache-dir "./python/"

EXPOSE 8080
ENV AGENTSENTINEL_DASHBOARD_HOST=0.0.0.0
ENV AGENTSENTINEL_DASHBOARD_PORT=8080

CMD ["agentsentinel-dashboard"]
```

```bash
# Build
docker build -t agentsentinel-dashboard .

# Run with environment file
docker run -p 8080:8080 \
  --env-file .env \
  agentsentinel-dashboard
```

> **Security:** Never expose port 8080 directly to the internet. Put a TLS reverse proxy (nginx/Caddy/Traefik) in front.

---

## 3. Deploy Supabase Edge Functions

### 3.1 Prerequisites

Install the Supabase CLI:
```bash
# macOS
brew install supabase/tap/supabase

# Linux / WSL
curl -sSf https://supabase.io/install.sh | sh

# Or via npm
npm install -g supabase
```

Install Deno (required for local function testing):
```bash
curl -fsSL https://deno.land/install.sh | sh
```

Login to Supabase:
```bash
supabase login
```

Link your project:
```bash
supabase link --project-ref YOUR_PROJECT_REF
# Your project ref is the part after https:// in your Supabase URL
# e.g. for https://abcdefghijklmnop.supabase.co, ref = abcdefghijklmnop
```

---

### 3.2 Deploy All Functions

```bash
# Deploy all Edge Functions in supabase/functions/
supabase functions deploy
```

This deploys all 8 functions:
- `validate-license`
- `stripe-webhook`
- `send-portal-otp`
- `customer-portal`
- `validate-promo`
- `admin-generate-promo`
- `checkout-team`
- `create-billing-session`

---

### 3.3 Deploy a Single Function

```bash
# Deploy just the stripe-webhook function
supabase functions deploy stripe-webhook

# Deploy just the promo functions
supabase functions deploy validate-promo
supabase functions deploy admin-generate-promo
```

---

### 3.4 Push Secrets

Edge Functions read secrets from Supabase — not from local `.env` files. You must push secrets explicitly.

**Push all secrets at once:**
```bash
supabase secrets set --env-file supabase/.env
```

**Push individual secrets:**
```bash
supabase secrets set ADMIN_API_SECRET=your_secret_here
supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_your_secret
supabase secrets set RESEND_API_KEY=re_your_key
```

**Verify secrets are set:**
```bash
supabase secrets list
```

You should see all required secrets listed (values are hidden).

> **Note:** Edge Functions pick up new secrets on the next cold-start, typically within 60 seconds of `supabase secrets set`.

---

## 4. Self-Hosted vs Supabase Hosting

This decision applies to the **admin dashboard** only. The landing site is already on a CDN.

| Factor | Python Self-Hosted | Static CDN (e.g. Cloudflare Pages) |
|--------|-------------------|-------------------------------------|
| **Setup time** | ~2 minutes | ~15 minutes |
| **Cost** | Free | Free tier / ~$20/month |
| **Latency** | ~5ms local / ~20ms remote | <50ms globally |
| **Availability** | Manual HA required | 99.99%+ CDN SLA |
| **TLS** | Manual (reverse proxy) | Automatic |
| **Access control** | Firewall / IP allowlist | Cloudflare Access / SSO |
| **Dev endpoints** (`/api/promos*`) | ✅ Available | ❌ Not available |
| **Offline operation** | ✅ Yes | ❌ Requires internet |
| **Ops complexity** | Low (one command) | Very low (zero-ops) |

**Recommendation:**

- **1–5 admin operators, same office/VPN:** Use Python self-hosted. Zero cost, 2-minute setup, keeps the service-role key off the public internet.

- **Distributed team, remote-first:** Use Cloudflare Pages + Cloudflare Access for zero-trust email/SSO access control. No server to manage.

The admin dashboard SPA (`python/agentsentinel/dashboard/static/admin/`) is plain HTML/CSS/JS — no build step — so it deploys to any static host.

---

## 5. Environment Variables Checklist

### 5.1 Root `.env` Variables

These are used by the Python admin dashboard and Python SDK. Reference: [`.env.example`](../.env.example).

| Variable | Required | How to generate | Description |
|----------|----------|----------------|-------------|
| `AGENTSENTINEL_LICENSE_SIGNING_SECRET` | ✅ | `openssl rand -hex 32` | HMAC secret for signing/verifying `asv1_` license keys. Must match Supabase secret. |
| `ADMIN_API_SECRET` | ✅ | `openssl rand -hex 32` | Bearer token for admin-only endpoints. Must match Supabase secret. |
| `SUPABASE_URL` | ✅ prod | Supabase dashboard → Settings → API | Your Supabase project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ prod | Supabase dashboard → Settings → API → service_role | Service-role JWT. **Never expose to browser.** |
| `SUPABASE_ANON_KEY` | ✅ prod | Supabase dashboard → Settings → API → anon public | Anon JWT. Safe to expose. |
| `STRIPE_PUBLISHABLE_KEY` | ✅ prod | [Stripe dashboard → API keys](https://dashboard.stripe.com/apikeys) | Front-end Stripe.js key (`pk_live_…`) |
| `STRIPE_SECRET_KEY` | ✅ prod | [Stripe dashboard → API keys](https://dashboard.stripe.com/apikeys) | Server-side Stripe key (`sk_live_…`) |
| `STRIPE_WEBHOOK_SECRET` | ✅ prod | [Stripe dashboard → Webhooks](https://dashboard.stripe.com/webhooks) | Webhook signature secret (`whsec_…`) |
| `AGENTSENTINEL_LICENSE_KEY` | ✅ SDK | [portal](https://agentsentinel.net/portal) | License key for SDK consumers |
| `AGENTSENTINEL_LICENSE_API` | ❌ | n/a | Override validation API URL |
| `AGENTSENTINEL_DEV` | ❌ dev | — | Set `1` for dev mode. **Never in prod.** |
| `AGENTSENTINEL_DEV_MODE` | ❌ dev | — | Set `true` to bypass licence gate. **Never in prod.** |
| `AGENTSENTINEL_DASHBOARD_PORT` | ❌ | — | Override dashboard port (default: 8080) |
| `AGENTSENTINEL_DASHBOARD_HOST` | ❌ | — | Override dashboard bind host (default: localhost) |
| `AGENTSENTINEL_DASHBOARD_DEBUG` | ❌ | — | Set `1` for verbose dashboard logging |

---

### 5.2 Supabase Edge Function Secrets

These are used by the Deno Edge Functions. Reference: [`supabase/.env.example`](../supabase/.env.example).

Push them with: `supabase secrets set --env-file supabase/.env`

| Variable | Required | How to get | Description |
|----------|----------|-----------|-------------|
| `AGENTSENTINEL_LICENSE_SIGNING_SECRET` | ✅ | `openssl rand -hex 32` | **Must match root `.env`.** HMAC signing secret. |
| `ADMIN_API_SECRET` | ✅ | `openssl rand -hex 32` | **Must match root `.env`.** Admin endpoint auth. |
| `SUPABASE_URL` | ✅ | Supabase dashboard | Project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Supabase dashboard | Service-role JWT. |
| `STRIPE_SECRET_KEY` | ✅ | Stripe dashboard | Server-side Stripe API key. |
| `STRIPE_WEBHOOK_SECRET` | ✅ | Stripe dashboard → Webhooks | Webhook signature secret. |
| `STRIPE_PRICE_STARTER` | ✅ | Stripe dashboard → Products | Price ID for Starter plan. |
| `STRIPE_PRICE_PRO` | ✅ | Stripe dashboard → Products | Price ID for Pro plan. |
| `STRIPE_PRICE_PRO_TEAM` | ✅ | Stripe dashboard → Products | Price ID for Pro Team plan. |
| `STRIPE_PRICE_ENTERPRISE` | ✅ | Stripe dashboard → Products | Price ID for Enterprise plan. |
| `STRIPE_PRICE_PRO_TEAM_BASE` | ✅ | Stripe dashboard → Products | Base price for Pro Team (per-seat checkout). |
| `STRIPE_PRICE_PRO_TEAM_SEAT` | ✅ | Stripe dashboard → Products | Per-seat price for Pro Team. |
| `RESEND_API_KEY` | ✅ | [resend.com/api-keys](https://resend.com/api-keys) | API key for transactional emails. |
| `SITE_BASE_URL` | ✅ | — | Your deployment URL (e.g. `https://agentsentinel.net`). Used for Stripe redirect URLs. |

---

## 6. Generate Secrets

Use `openssl` to generate strong random secrets:

```bash
# Generate AGENTSENTINEL_LICENSE_SIGNING_SECRET
openssl rand -hex 32
# Example: a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1

# Generate ADMIN_API_SECRET
openssl rand -hex 32
# Example: f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9
```

> **Note:** Run this command twice — you need two different secrets, one for each variable.

**Automated setup:** The `scripts/setup-env.sh` script generates these secrets automatically:

```bash
./scripts/setup-env.sh
# This generates .env and supabase/.env from the .example templates
# and fills in __GENERATE_HEX_32__ placeholders with real secrets
```

On Windows:
```powershell
.\scripts\setup-env.ps1
```

---

## 7. Database Migrations

Supabase manages the database schema through migration files in `supabase/migrations/`.

**Apply all migrations:**
```bash
supabase db push
```

**Check migration status:**
```bash
supabase db status
```

**Run a specific migration locally:**
```bash
supabase db execute --file supabase/migrations/010_add_promo_codes.sql
```

**Key migrations:**
| Migration | What it creates |
|-----------|----------------|
| `001_initial_schema.sql` | `customers`, `licenses` tables |
| `010_add_promo_codes.sql` | `promo_codes` table |
| `011_add_audit_logs.sql` | `admin_logs` table |
| `012_webhook_events_idempotency.sql` | `webhook_events` table with deduplication |

---

## 8. Stripe Webhook Setup

**Step 1 — Create a webhook endpoint in Stripe:**

1. Go to [Stripe Dashboard → Developers → Webhooks](https://dashboard.stripe.com/webhooks)
2. Click **"Add endpoint"**
3. Enter URL: `https://YOUR_PROJECT_REF.supabase.co/functions/v1/stripe-webhook`
4. Select events to listen for:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
   - `invoice.payment_succeeded`
5. Click **"Add endpoint"**

**Step 2 — Get the signing secret:**

After creating the endpoint, click on it and reveal the **Signing secret** (`whsec_…`). This is your `STRIPE_WEBHOOK_SECRET`.

**Step 3 — Update Supabase secrets:**
```bash
supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_your_secret_here
```

**Step 4 — Test locally with Stripe CLI:**
```bash
# Install Stripe CLI: https://stripe.com/docs/stripe-cli
stripe login
stripe listen --forward-to http://localhost:54321/functions/v1/stripe-webhook
```

---

## 9. Verify Your Deployment

After deploying, run these checks:

**Edge Functions responding:**
```bash
# validate-license should return {"valid": false, ...} for an invalid key
curl -X POST https://YOUR_PROJECT.supabase.co/functions/v1/validate-license \
  -H "Content-Type: application/json" \
  -d '{"license_key": "test_invalid_key"}'
# Expected: {"valid": false, "error": "Unrecognised license key format"}

# validate-promo should return {"valid": false, ...} for a nonexistent code
curl -X POST https://YOUR_PROJECT.supabase.co/functions/v1/validate-promo \
  -H "Content-Type: application/json" \
  -d '{"code": "NONEXISTENT"}'
# Expected: {"valid": false, "reason": "not_found"}
```

**Admin endpoint auth:**
```bash
# Without token — should return 401
curl -X POST https://YOUR_PROJECT.supabase.co/functions/v1/admin-generate-promo \
  -H "Content-Type: application/json" \
  -d '{"code": "TEST", "type": "discount_percent", "value": 10}'
# Expected: 401 Unauthorized

# With correct token — should return 201 or 409 (if code exists)
curl -X POST https://YOUR_PROJECT.supabase.co/functions/v1/admin-generate-promo \
  -H "Authorization: Bearer $ADMIN_API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"code": "DEPLOY_TEST", "type": "discount_percent", "value": 10}'
# Expected: 201 Created
```

**Run config check:**
```bash
agentsentinel-config-check
# All required variables should show ✅
```

**Admin dashboard:**
```bash
# Dashboard should return HTTP 200
curl -I http://localhost:8080/admin
# Expected: HTTP/1.0 200 OK
```

For more deployment troubleshooting, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
