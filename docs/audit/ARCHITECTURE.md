# AgentSentinel — System Architecture

**Audit Date:** 2026-05-05  
**Scope:** End-to-end flow from anonymous visitor through license activation to SDK runtime validation

---

## 1. End-to-End Architecture Diagram

```mermaid
flowchart TD
    subgraph Visitor["🌐 Customer Journey"]
        V["Visitor\nindex.html"]
        PR["Pricing\npricing-team.html"]
        SC["Stripe Checkout\n(checkout-team EF)"]
        SX["success.html\n(post-payment)"]
        OTP["OTP Login\n(send-portal-otp EF)"]
        PORT["Customer Portal\nportal.html\n(customer-portal EF)"]
        SDK_USE["Developer's App\nPython SDK"]
    end

    subgraph Promo["💳 Promo Code Flow"]
        PCH["Enter promo code\n(pricing page)"]
        VP["validate-promo EF\n10 req/min/IP"]
        COUP["Stripe Coupon\napplied to session"]
    end

    subgraph Backend["⚡ Supabase Edge Functions"]
        CTEF["checkout-team\n(create Stripe session)"]
        SPEF["send-portal-otp\n3 sends + 5 verifies / 15 min / email"]
        CPEF["customer-portal\n(OTP verify + license fetch)"]
        CBEF["create-billing-session\n(Stripe portal link)"]
        SWEF["stripe-webhook\n(event processing)"]
        AGPEF["admin-generate-promo\nBearer ADMIN_API_SECRET"]
        VLEF["validate-license\n20 req/min/IP"]
        VPEF2["validate-promo\n10 req/min/IP"]
    end

    subgraph DB["🗄️ PostgreSQL (Supabase)"]
        CUST[("customers")]
        LIC[("licenses")]
        PROMO[("promo_codes")]
        WE[("webhook_events\nstatus: pending|processed|failed")]
        AL[("admin_logs")]
        LV[("license_validations\nkey hash only — never plaintext")]
        POTPS[("portal_otps")]
        DM[("dashboard_metrics")]
    end

    subgraph Admin["🛡️ Admin Dashboard SPA"]
        ASPA["admin/index.html\nAdminApp page router"]
        OV["overview.js\n(KPIs + tier breakdown)"]
        LPAGE["licenses.js\n(search, revoke, export)"]
        PPAGE["promos.js\n(CRUD + usage stats)"]
        UPAGE["users.js\n(customer list)"]
        MPAGE["metrics.js\n(charts)"]
        WPAGE["webhooks.js\n(event log)"]
        SPAGE["system.js\n(config, migrations)"]
        APAGE["audit.js\n(admin_logs viewer)"]
    end

    subgraph Stripe["💳 Stripe"]
        SCK["Stripe Checkout\n(hosted page)"]
        SWH["Stripe Webhooks\n(signed events)"]
        SBIL["Stripe Billing Portal"]
    end

    subgraph External["📧 External Services"]
        RESEND["Resend Email API\n(license delivery + OTP)"]
    end

    %% Customer flow
    V --> PR
    PR --> PCH --> VPEF2 --> COUP
    PR --> CTEF --> SCK
    COUP --> SCK
    SCK -->|redirect| SX
    SX --> OTP --> SPEF --> POTPS
    SPEF --> RESEND
    SX --> PORT --> CPEF --> LIC
    CPEF --> CUST
    PORT --> CBEF --> SBIL
    PORT --> SDK_USE

    %% SDK validation
    SDK_USE --> VLEF --> LIC
    VLEF --> LV

    %% Stripe webhook loop
    SCK -->|event| SWH --> SWEF
    SWEF -->|idempotency check| WE
    SWEF --> CUST
    SWEF --> LIC
    SWEF --> PROMO
    SWEF --> RESEND

    %% Admin
    ASPA --> OV & LPAGE & PPAGE & UPAGE & MPAGE & WPAGE & SPAGE & APAGE
    LPAGE & UPAGE & MPAGE & WPAGE & APAGE & OV -->|Supabase REST| DB
    PPAGE --> AGPEF --> PROMO
    SPAGE -->|Supabase REST| DB

    style Visitor fill:#0f172a,color:#e2e8f0
    style Promo fill:#1e293b,color:#e2e8f0
    style Backend fill:#1e3a5f,color:#e2e8f0
    style DB fill:#14532d,color:#e2e8f0
    style Admin fill:#3b1f5e,color:#e2e8f0
    style Stripe fill:#1a1a2e,color:#e2e8f0
    style External fill:#2d1f14,color:#e2e8f0
```

---

## 2. Component Responsibilities

### 2.1 Customer-Facing HTML Pages

| File | Responsibility | Key Integrations |
|---|---|---|
| `index.html` | Marketing landing page, hero CTA | Links to `pricing-team.html` |
| `pricing-team.html` | Plan comparison, promo code entry, Stripe checkout initiation | `validate-promo` EF, `checkout-team` EF |
| `success.html` | Post-payment confirmation, portal redirect prompt | Session parameter parsing |
| `portal.html` | Customer self-service: license key display, billing management | `send-portal-otp` EF, `customer-portal` EF, `create-billing-session` EF |

### 2.2 Admin Dashboard SPA

The admin SPA lives at `python/agentsentinel/dashboard/static/admin/`. It is a single-page application with a client-side page router.

| Module | File | Responsibility |
|---|---|---|
| App router | `admin/index.html` + `app.js` | Page registry, lazy import, nav highlighting |
| Auth | `js/auth.js` | `sessionStorage` for service-role key + admin secret; URL in `localStorage` |
| API client | `js/api.js` | All Supabase REST calls; `_maskSensitive()` for audit logging |
| Overview | `js/pages/overview.js` | KPI cards, tier breakdown bar, recent activity |
| Licenses | `js/pages/licenses.js` | License search, status toggle, revocation, CSV export |
| Promos | `js/pages/promos.js` | Promo CRUD, usage chart, expiry management |
| Users | `js/pages/users.js` | Customer list, seat usage, merge/delete |
| Metrics | `js/pages/metrics.js` | Chart.js graphs for validations over time |
| Webhooks | `js/pages/webhooks.js` | Event log with `status` badge (`pending`/`processed`/`failed`) |
| System | `js/pages/system.js` | DB migration status, config display |
| Audit | `js/pages/audit.js` | `admin_logs` viewer with actor/IP/action |

**Auth strategy:** `agentsentinel-admin-key` (Supabase service-role key) and `agentsentinel-admin-secret` (admin API secret) stored in `sessionStorage` — cleared on tab close. Supabase URL stored in `localStorage` (non-sensitive). ✅

### 2.3 Python Server (`server.py`)

| Aspect | Implementation |
|---|---|
| Mode | Dev (HTTP, localhost) vs. Prod (configurable, HTTPS-terminated by reverse proxy) |
| CORS | `localhost` only in dev; configurable in prod |
| MIME types | Correct `.js` → `application/javascript`, `.css` → `text/css` |
| Static serving | Serves `static/admin/` with proper path traversal protection |

### 2.4 Supabase Edge Functions

| Function | Auth | Rate Limit | Purpose |
|---|---|---|---|
| `validate-license` | None (public) | 20/min/IP | Validates license key, returns tier + limits |
| `validate-promo` | None (public) | 10/min/IP | Validates promo code, returns discount value |
| `admin-generate-promo` | `Bearer ADMIN_API_SECRET` | None (admin-only) | Creates new promo code in DB |
| `stripe-webhook` | Stripe signature | None | Processes Stripe events, provisions licenses |
| `send-portal-otp` | None (public) | 3 sends + 5 verifies per email/15min | Sends OTP email via Resend |
| `customer-portal` | OTP token | Per-email | Verifies OTP, returns license key and customer data |
| `checkout-team` | None (public) | None | Creates Stripe checkout session |
| `create-billing-session` | OTP token | None | Creates Stripe billing portal session |

### 2.5 Database Tables

| Table | Purpose | Key Constraints |
|---|---|---|
| `customers` | Customer accounts | UNIQUE `email`; `upsert_customer()` function |
| `licenses` | License records | FK → `customers`, FK → `promo_codes` ON DELETE SET NULL |
| `promo_codes` | Promo code catalogue | UNIQUE `code`; CHECK `type IN (...)`, `used_count <= max_uses` |
| `webhook_events` | Stripe event log | UNIQUE `stripe_event_id`; `status` enum (pending/processed/failed) |
| `license_validations` | SDK validation audit | Stores SHA-256 hash of key only — never plaintext |
| `admin_logs` | Admin action audit | Actor, action, before/after JSON, masked sensitive fields |
| `portal_otps` | OTP state | UNIQUE `email`; expires_at TTL |
| `dashboard_metrics` | Cached KPI snapshots | Updated by webhook processor |

### 2.6 Python SDK (`python/agentsentinel/licensing.py`)

| Aspect | Implementation |
|---|---|
| Online validation | POST to `validate-license` EF; parses tier + limits |
| Offline validation | HMAC-SHA256 over alphabetically-sorted JSON payload |
| Key formats | `asv1_*` (HMAC-signed), `as_<tier>_*` (legacy) |
| Retry logic | Exponential backoff with jitter; falls back to cached result |
| Env vars | `AGENTSENTINEL_LICENSE_KEY`, `AGENTSENTINEL_API_URL` |

### 2.7 HMAC Signing Parity

Both the TypeScript Edge Function and the Python SDK sign license keys identically:

1. Build payload JSON with alphabetically-sorted keys: `exp`, `iat`, `nonce`, `tier`
2. Base64url-encode the JSON bytes
3. HMAC-SHA256 sign the base64url string using `LICENSE_SIGNING_KEY`
4. Key format: `asv1_<base64url_payload>.<hex_hmac>`

Python uses `sort_keys=True` in `json.dumps`; TypeScript uses a fixed replacer array `["exp","iat","nonce","tier"]`.

---

## 3. Data Flow: Promo Code → License Discount

```mermaid
sequenceDiagram
    participant B as Browser
    participant VP as validate-promo EF
    participant CTEF as checkout-team EF
    participant SC as Stripe Checkout
    participant SWH as stripe-webhook EF
    participant DB as PostgreSQL

    B->>VP: POST {code, tier}
    VP-->>B: {valid:true, id, type, value}
    B->>CTEF: POST {plan, promo_id}
    CTEF->>SC: createSession({coupon: stripe_coupon_id})
    SC-->>B: redirect to hosted checkout
    B->>SC: complete payment
    SC->>SWH: checkout.session.completed event
    SWH->>DB: INSERT webhook_events ON CONFLICT DO NOTHING
    SWH->>DB: upsert_customer()
    SWH->>DB: INSERT/UPDATE licenses (promo_code_id=...)
    SWH->>DB: UPDATE promo_codes SET used_count+1
```

---

## 4. Data Flow: SDK License Validation

```mermaid
sequenceDiagram
    participant SDK as Python SDK
    participant VL as validate-license EF
    participant DB as PostgreSQL

    SDK->>VL: POST {license_key}
    VL->>VL: Rate limit check (20/min/IP)
    VL->>DB: SELECT licenses WHERE license_key=?
    VL->>DB: INSERT license_validations (key_hash, outcome)
    VL-->>SDK: {valid, tier, limits, features}
    SDK->>SDK: Cache result for TTL period
    SDK->>SDK: HMAC offline verify (fallback)
```
