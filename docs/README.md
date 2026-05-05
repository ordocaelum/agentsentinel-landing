# AgentSentinel Documentation

> **TL;DR:** Everything you need to run, integrate, and operate AgentSentinel — pick your role below and start there.

---

## Start Here — Pick Your Role

| Role | Start with | Then read |
|------|-----------|-----------|
| **New Admin** — setting up the dashboard for the first time | [ADMIN_WORKFLOW.md](ADMIN_WORKFLOW.md) | [DEPLOYMENT.md](DEPLOYMENT.md) → [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md) |
| **Developer** — integrating the SDK into your project | [SDK_INTEGRATION.md](SDK_INTEGRATION.md) | [CUSTOMER_JOURNEY.md](CUSTOMER_JOURNEY.md) |
| **Customer Support** — helping customers with portal or license issues | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | [ADMIN_WORKFLOW.md](ADMIN_WORKFLOW.md) |
| **DevOps / On-call Engineer** — running the system in production | [DEPLOYMENT.md](DEPLOYMENT.md) | [RUNBOOKS.md](RUNBOOKS.md) → [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md) |

---

## All Documentation

### 📋 [ADMIN_WORKFLOW.md](ADMIN_WORKFLOW.md)
**Complete Admin Dashboard Guide**

Step-by-step setup for new admins, a tour of all 8 admin pages, promo code creation workflows with concrete examples, license management, and how to read the audit log. *Start here if you're an admin.*

---

### 🛒 [CUSTOMER_JOURNEY.md](CUSTOMER_JOURNEY.md)
**End-to-End Customer Flow**

Mermaid diagram and data flow from anonymous visitor → pricing → Stripe checkout → success → portal → SDK. Shows where promo codes are applied, how OTP login works, and how license keys are delivered and stored securely.

---

### ⚡ [SDK_INTEGRATION.md](SDK_INTEGRATION.md)
**Developer SDK Integration Guide**

5-minute quickstart for Python and TypeScript SDKs, required environment variables, license key formats, rate limits, offline HMAC verification, and error codes. *Start here if you're a developer.*

---

### 🚀 [DEPLOYMENT.md](DEPLOYMENT.md)
**Hosting & Deployment Guide**

Current architecture overview, step-by-step deploy for the Python admin dashboard and Supabase Edge Functions, self-hosted vs CDN comparison, complete environment variable checklist, and secret generation instructions.

---

### 🔧 [RUNBOOKS.md](RUNBOOKS.md)
**Operational Runbooks**

Concrete step-by-step procedures for on-call engineers: failed Stripe webhooks, stuck/invalid licenses, OTP brute-force investigation, rate limit breaches, secret rotation, and database integrity checks.

---

### 🐛 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
**Common Issues & Fixes**

Quick lookup for common errors: `401 Unauthorized`, `License invalid`, `Promo not applying`, `Portal shows wrong data`, `Webhook not processed`. Includes diagnostic SQL and recovery commands.

---

### 🔒 [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md)
**Production Sign-Off Checklist**

Single-page checklist for going to production: all secrets in env, API endpoints rate-limited, service-role key never in HTML, license keys never in localStorage, email enumeration resistance, OTP rate limits, audit logging.

---

## Supplementary References

| File | What it covers |
|------|---------------|
| [setup.md](setup.md) | Canonical environment variable reference and secret rotation runbook |
| [license-key-format.md](license-key-format.md) | HMAC payload specification, key format details |
| [PROMO_CODE_GUIDE.md](PROMO_CODE_GUIDE.md) | Detailed promo code API reference |
| [HOSTING_GUIDE.md](HOSTING_GUIDE.md) | Self-hosted vs static CDN comparison matrix |
| [OPERATIONAL_RUNBOOKS.md](OPERATIONAL_RUNBOOKS.md) | Extended operational procedures |
| [PRODUCTION_READINESS_AUDIT.md](PRODUCTION_READINESS_AUDIT.md) | Full 9-phase production readiness audit |

---

## Quick Links

- **Admin Dashboard:** `http://localhost:8080/admin` (after `agentsentinel-dashboard`)
- **Customer Portal:** [agentsentinel.net/portal](https://agentsentinel.net/portal)
- **PyPI Package:** [agentsentinel-core](https://pypi.org/project/agentsentinel-core/)
- **npm Package:** [@agentsentinel/sdk](https://www.npmjs.com/package/@agentsentinel/sdk)
- **GitHub Issues:** [github.com/ordocaelum/agentsentinel-landing/issues](https://github.com/ordocaelum/agentsentinel-landing/issues)
