# AgentSentinel — Hosting Guide

Options for deploying the AgentSentinel platform and admin dashboard.

---

## Table of Contents

1. [Current Architecture](#1-current-architecture)
2. [Option A: Python Self-Hosted Dashboard](#2-option-a-python-self-hosted-dashboard)
3. [Option B: Supabase Hosting / Static CDN](#3-option-b-supabase-hosting--static-cdn)
4. [Comparison Matrix](#4-comparison-matrix)
5. [Recommendation](#5-recommendation)
6. [Docker / Containerised Deployment](#6-docker--containerised-deployment)
7. [Environment Variables](#7-environment-variables)

---

## 1. Current Architecture

AgentSentinel has two distinct deployment layers:

```
┌─────────────────────────────────────────────────────────────────┐
│  Static Landing Site (GitHub Pages / any CDN)                    │
│  index.html, portal.html, pricing-team.html, success.html        │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS calls
┌──────────────────────────▼──────────────────────────────────────┐
│  Supabase (managed)                                              │
│  ● PostgreSQL database                                           │
│  ● Edge Functions (Deno): validate-license, stripe-webhook,      │
│    send-portal-otp, customer-portal, validate-promo,             │
│    admin-generate-promo, checkout-team, create-billing-session   │
│  ● Auth + RLS policies                                           │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Local HTTP
┌──────────────────────────▼──────────────────────────────────────┐
│  Python Admin Dashboard (self-hosted, port 8080)                 │
│  python/agentsentinel/dashboard/server.py                        │
│  Serves the admin SPA + proxies REST API calls to Supabase       │
└─────────────────────────────────────────────────────────────────┘
```

The **landing site** and **Supabase backend** are independent of each other. The **Python admin dashboard** is an optional operator tool that runs locally or on a private server.

---

## 2. Option A: Python Self-Hosted Dashboard

### What it is

A zero-dependency Python HTTP server (`python/agentsentinel/dashboard/server.py`) that:
- Serves the admin SPA (`static/admin/`)
- Provides dev-mode promo CRUD endpoints (`/api/promos*`) when `AGENTSENTINEL_DEV=1`
- Runs on `localhost:8080` by default

### Setup

```bash
pip install agentsentinel[dashboard]
agentsentinel-dashboard
# or
python -m agentsentinel.dashboard
```

Environment variables:

| Variable | Default | Description |
|---|---|---|
| `AGENTSENTINEL_DASHBOARD_PORT` | `8080` | HTTP port |
| `AGENTSENTINEL_DASHBOARD_HOST` | `localhost` | Bind address |
| `AGENTSENTINEL_DEV` | `` | Set `1` to enable dev-only endpoints |
| `AGENTSENTINEL_DASHBOARD_DEBUG` | `` | Set `1` for verbose logging |

### Pros

| | |
|---|---|
| ✅ **No external dependency** | Runs anywhere Python 3.9+ is available |
| ✅ **Zero cost** | No additional hosting fee |
| ✅ **Private by default** | Binds to `localhost` — not exposed to the internet unless explicitly configured |
| ✅ **Offline capable** | Works without internet access (reads from local Supabase API key) |
| ✅ **Simple deployment** | One command: `agentsentinel-dashboard` |

### Cons

| | |
|---|---|
| ❌ **Single machine** | No built-in HA or load balancing |
| ❌ **No TLS** | HTTP only by default; add a reverse proxy (nginx/Caddy) for HTTPS |
| ❌ **Manual process management** | Need systemd / pm2 / Docker to keep it running |
| ❌ **Port management** | Must ensure port 8080 is available and firewall allows inbound |

### Production hardening for self-hosted

If running the dashboard on a remote server (not just `localhost`):

1. **TLS termination:** Put nginx or Caddy in front:
   ```nginx
   server {
     listen 443 ssl;
     server_name admin.example.com;
     location / {
       proxy_pass http://127.0.0.1:8080;
     }
   }
   ```

2. **IP allowlist:** Restrict access to known IP ranges.

3. **Bind to localhost:** Never bind `0.0.0.0` without a TLS reverse proxy in front.

4. **Systemd service:**
   ```ini
   [Unit]
   Description=AgentSentinel Admin Dashboard

   [Service]
   ExecStart=/usr/local/bin/agentsentinel-dashboard
   Restart=always
   Environment=AGENTSENTINEL_DASHBOARD_PORT=8080
   EnvironmentFile=/etc/agentsentinel/.env

   [Install]
   WantedBy=multi-user.target
   ```

---

## 3. Option B: Supabase Hosting / Static CDN

### What it is

The admin SPA (`python/agentsentinel/dashboard/static/admin/`) is plain HTML/CSS/JS with no build step required. It can be served from any static hosting provider.

Options:
- **Supabase Storage** — serve from `storage.supabase.co` bucket with public access
- **Cloudflare Pages** — deploy from GitHub, edge-cached globally
- **Vercel / Netlify** — deploy from GitHub, zero-config
- **AWS S3 + CloudFront** — enterprise CDN

### Setup (Cloudflare Pages example)

1. Connect repository to Cloudflare Pages.
2. Set build output directory to `python/agentsentinel/dashboard/static/admin/`.
3. No build command needed (static files).
4. Set custom domain (e.g., `admin.agentsentinel.net`).
5. Enable Cloudflare Access to restrict access by email/SSO.

### Pros

| | |
|---|---|
| ✅ **Global CDN** | <50ms load time worldwide |
| ✅ **Zero ops** | No server to manage |
| ✅ **Built-in HTTPS** | TLS handled by the CDN |
| ✅ **High availability** | CDN SLA typically 99.99%+ |
| ✅ **Cloudflare Access** | Zero-trust access control without VPN |

### Cons

| | |
|---|---|
| ❌ **External dependency** | Requires CDN account + DNS configuration |
| ❌ **Cost** | Cloudflare Pages free tier covers most use; commercial plans from $20/mo |
| ❌ **Dev-mode endpoints unavailable** | The Python `/api/promos*` dev endpoints are not available; use Supabase REST directly |
| ❌ **Loses Python server features** | If future features add server-side processing to the dashboard, they'd need migration |

---

## 4. Comparison Matrix

| Factor | Python Self-Hosted | Static CDN (Cloudflare Pages) |
|---|---|---|
| **Cost** | Free | Free tier / ~$20/mo |
| **Latency** | ~5ms (local) / ~20ms (remote) | <50ms global |
| **Availability** | Manual HA required | 99.99%+ CDN SLA |
| **TLS** | Manual (reverse proxy) | Automatic |
| **Access Control** | Firewall / IP allowlist | Cloudflare Access / SSO |
| **Dev endpoints** | ✅ Available | ❌ Not available |
| **Ops complexity** | Low (one command) | Very low (zero-ops) |
| **Scalability** | Single instance | Global edge |
| **Offline** | ✅ Yes | ❌ Requires internet |
| **Setup time** | ~2 minutes | ~15 minutes |

---

## 5. Recommendation

> **For an admin-only internal tool used by 1–5 operators: use the Python self-hosted dashboard running locally or on a bastion host behind a VPN.**

Reasoning:
- The admin dashboard accesses a Supabase service-role key. Keeping it off the public internet is a security feature, not a limitation.
- The Python server is zero-dependency, zero-cost, and operational in 2 minutes.
- The dev-mode promo endpoints are useful for local testing.

> **For a team distributed across multiple offices / remote-first team: use Cloudflare Pages + Cloudflare Access.**

Reasoning:
- Zero-trust access control (email allowlist or SSO) without VPN.
- Global edge means fast load times regardless of location.
- Zero server maintenance.

> **The customer-facing landing site** (`index.html`, `portal.html`, etc.) is **already on GitHub Pages / CDN** and requires no change.

---

## 6. Docker / Containerised Deployment

For running the Python dashboard in a containerised environment:

```dockerfile
# Dockerfile (place in repo root)
FROM python:3.12-slim

WORKDIR /app
COPY python/ ./python/
RUN pip install --no-cache-dir "./python[dashboard]"

EXPOSE 8080
ENV AGENTSENTINEL_DASHBOARD_HOST=0.0.0.0
ENV AGENTSENTINEL_DASHBOARD_PORT=8080

CMD ["agentsentinel-dashboard"]
```

```bash
# Build and run
docker build -t agentsentinel-dashboard .
docker run -p 8080:8080 \
  --env-file .env \
  agentsentinel-dashboard
```

**Important:** Never expose port 8080 directly to the internet. Put a TLS reverse proxy (nginx / Caddy / Traefik) in front.

---

## 7. Environment Variables

All required environment variables are documented in:
- [`.env.example`](../.env.example) — root variables (Python SDK + dashboard)
- [`supabase/.env.example`](../supabase/.env.example) — Supabase Edge Function secrets

Auto-generate secrets with:
```bash
./scripts/generate-secrets.sh
```

See [setup.md](setup.md) for full environment variable reference.
