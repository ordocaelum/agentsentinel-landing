# Customer Dashboard — Mission Control Lite

> **Audience:** AgentSentinel customers and developers deploying the customer-facing dashboard.

---

## Overview

**Mission Control Lite** is the customer-facing monitoring layer of AgentSentinel.
It gives every paying customer a live, zero-setup dashboard URL the moment their
Stripe checkout completes — no Supabase credentials, no manual environment setup.

### Customer journey

```
Stripe checkout.session.completed
        │
        ├─ Existing: create customer + license rows
        ├─ NEW: create customer_dashboards row (auto-provisioned)
        ├─ NEW: insert synthetic "dashboard_created" event
        └─ Email: "Your dashboard is ready" + Launch Dashboard CTA
                  URL: https://dash.agentsentinel.net/d/{customer_id}/{dashboard_token}
                        └─ valid for 30 days without login
```

---

## URL format

```
https://dash.agentsentinel.net/d/{customer_id}/{dashboard_token}
```

| Segment | Description |
|---|---|
| `customer_id` | UUID of the `customers` row |
| `dashboard_token` | Unguessable UUID stored in `customer_dashboards.dashboard_token` |

The token replaces password authentication for the 30-day grace period.
After that, customers sign in via `agentsentinel.net/portal`.

Query-param form (for onboarding wizard via email link):
```
https://agentsentinel.net/dashboard/onboarding.html?token={license_key}
```

---

## Frontend pages

| Page | Purpose |
|---|---|
| `dashboard/onboarding.html` | 3-step wizard: language pick → install/configure → test & launch |
| `dashboard/main.html` | Live monitoring: stats cards, event stream, budget bars |

### JavaScript modules

| File | Purpose |
|---|---|
| `dashboard/static/customer/customer-api.js` | Calls Edge Functions; auth via `license_key` query param |
| `dashboard/static/customer/onboarding.js` | Wizard state machine; auto-generates SDK setup code |
| `dashboard/static/customer/live-dashboard.js` | Polls stats + events every 3–5 s; renders event table |

---

## Backend: Edge Functions

All new functions live in `supabase/functions/`.
Auth: all customer-facing functions accept the license key in the URL path or request body — **no separate JWT required**.

### POST `/functions/v1/customer-events`

Receives batched tool-decision events from the SDK.

**Rate limit:** 1 000 requests / minute per license key (HTTP 429 on overflow, `Retry-After: 60`).

**Request body** (single event or batch):
```json
{
  "events": [
    {
      "license_key": "asv1_...",
      "agent_id":    "my-agent-42",
      "tool_name":   "search_web",
      "status":      "allowed",
      "cost":        0.005,
      "timestamp":   "2026-05-05T16:00:00Z",
      "metadata":    { "query": "..." }
    }
  ]
}
```

`status` must be one of: `allowed` | `blocked` | `pending` | `expired`.

**Response:**
```json
{ "ok": true, "stored": 1 }
```

---

### GET `/functions/v1/customer-dashboard/{license_key}`

Returns dashboard configuration (used by onboarding wizard to prefill code blocks).

**Response:**
```json
{
  "agent_id":         "uuid",
  "status":           "active",
  "tier":             "pro",
  "created_at":       "2026-05-05T...",
  "live_url":         "https://dash.agentsentinel.net/d/...",
  "webhook_url":      "https://xxx.supabase.co/functions/v1/customer-events",
  "dashboard_token":  "uuid",
  "dashboard_status": "active"
}
```

---

### GET `/functions/v1/customer-events-list/{license_key}`

Returns paginated `agent_events` rows.

**Query params:** `limit` (1–100, default 20), `offset` (default 0), `order` (`desc` | `asc`).

**Response:**
```json
{ "events": [...], "total": 42, "limit": 20, "offset": 0 }
```

---

### GET `/functions/v1/customer-stats/{license_key}`

Returns aggregate statistics for the live dashboard.

**Response:**
```json
{
  "total_spend":       0.1234,
  "daily_budget":      null,
  "hourly_budget":     null,
  "approvals_pending": 0,
  "event_count":       15,
  "agent_status":      "running",
  "tier":              "pro",
  "license_status":    "active",
  "uptime_since":      "2026-05-05T...",
  "events_limit":      100000,
  "agents_limit":      10
}
```

---

## Database: new tables

Migration: `supabase/migrations/013_customer_dashboards.sql`

### `customer_dashboards`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | auto-generated |
| `license_id` | UUID FK → licenses | ON DELETE CASCADE |
| `customer_id` | UUID FK → customers | ON DELETE CASCADE |
| `dashboard_token` | UUID UNIQUE | embedded in URL; replaces auth for 30 days |
| `webhook_secret` | UUID | shared secret (reserved for future HMAC validation) |
| `created_at` | TIMESTAMPTZ | |
| `status` | TEXT | `active` \| `paused` \| `deleted` |
| `config` | JSONB | customer-specific settings (reserved) |

### `agent_events`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `dashboard_id` | UUID FK → customer_dashboards | ON DELETE CASCADE |
| `agent_id` | TEXT | agent identifier from SDK |
| `tool_name` | TEXT | tool that was invoked |
| `status` | TEXT | `allowed` \| `blocked` \| `pending` \| `expired` \| `dashboard_created` |
| `cost` | DECIMAL(10,4) | USD; nullable |
| `timestamp` | TIMESTAMPTZ | event time |
| `metadata` | JSONB | arbitrary extra data |

Index: `agent_events_dashboard_ts_idx ON agent_events (dashboard_id, timestamp DESC)`

### Row Level Security

- **Service-role key** bypasses RLS automatically (all Edge Functions use it).
- **Anon / public** read access is scoped to the `dashboard_token`:
  ```sql
  set_config('app.dashboard_token', '<token>', true)
  ```
  The customer-facing Edge Functions set this before querying with the anon client.

---

## SDK integration

### Python (`agentsentinel-core`)

New fields on `AgentPolicy`:

```python
from agentsentinel import AgentGuard, AgentPolicy

policy = AgentPolicy(
    daily_budget=10.0,
    webhook_url="https://xxx.supabase.co/functions/v1/customer-events",
    webhook_key="asv1_...",   # your license key
    stream_events=True,       # default True
    stream_batch_size=10,     # flush every N events
    stream_interval=5.0,      # or every N seconds
)
guard = AgentGuard(policy=policy, license_key="asv1_...")
```

Events are queued and flushed by a **daemon background thread** — tool execution
is never blocked.  The queue cap is 5 000 events; overflow is silently dropped.

### TypeScript (`@agentsentinel/sdk`)

New options on `AgentPolicyOptions`:

```typescript
import { AgentGuard, AgentPolicy } from "@agentsentinel/sdk";

const policy = new AgentPolicy({
  dailyBudget: 10.0,
  webhookUrl:  "https://xxx.supabase.co/functions/v1/customer-events",
  webhookKey:  "asv1_...",
  streamEvents:     true,
  streamBatchSize:  10,
  streamIntervalMs: 5000,
});
const guard = new AgentGuard({ policy });

// Call guard.destroy() when shutting down to flush remaining events.
process.on("SIGTERM", () => guard.destroy());
```

Events are batched and POSTed with `fetch` fire-and-forget (no `await`).

---

## Environment variables

### `supabase/.env.example`

```env
# Customer-facing dashboard base URL (used in purchase email + Edge Function)
CUSTOMER_DASHBOARD_BASE_URL=https://dash.agentsentinel.net
```

### `.env.example` (root)

```env
# Webhook URL for SDK event streaming
AGENTSENTINEL_WEBHOOK_URL=https://xxx.supabase.co/functions/v1/customer-events
```

---

## Deployment checklist

1. Run migration: `supabase db push` (applies `013_customer_dashboards.sql`)
2. Set secret: `supabase secrets set CUSTOMER_DASHBOARD_BASE_URL=https://dash.agentsentinel.net`
3. Deploy Edge Functions:
   ```
   supabase functions deploy customer-events
   supabase functions deploy customer-dashboard
   supabase functions deploy customer-events-list
   supabase functions deploy customer-stats
   supabase functions deploy stripe-webhook   # updated
   ```
4. Host `dashboard/onboarding.html` and `dashboard/main.html` at the base URL.
5. Update `window.__AS_SUPABASE_URL` in both HTML files to your Supabase project URL.

---

## Out of scope (v1)

- WebSocket real-time (polling only in v1)
- Approval queue UI (events marked `pending` are visible; Approve/Reject wiring is a v2 item)
- Custom alerts (Slack, email beyond purchase confirmation)
- Migration of admin dashboard
- Changes to OTP / portal auth flow
