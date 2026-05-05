# AgentSentinel — Issues Log

**Audit Date:** 2026-05-05  
**Auditor:** Copilot Coding Agent

This log records every finding from the 9-phase audit. Findings resolved in prior PRs are marked as such. Findings fixed in this PR are marked **"Fixed in this PR"**.

---

## 🔴 Critical Issues (0 open)

*No critical issues are open at the time of this audit.*

### Previously Critical — Resolved in Prior PRs

| ID | Severity | File | Description | Resolution |
|---|---|---|---|---|
| C-1 | ~~Critical~~ → Fixed | `supabase/functions/admin-generate-promo/index.ts` | Used local 3-tier `VALID_TIERS` set (`free`, `pro`, `team`) instead of the canonical 6-tier set. Prevented creating tier-restricted promos for `starter`, `pro_team`, `enterprise`. | Fixed: now imports from `_shared/tiers.ts` |
| C-2 | ~~Critical~~ → Fixed | `supabase/functions/validate-license/index.ts` | No rate limiting on the public endpoint — susceptible to abuse/enumeration. | Fixed: sliding-window 20/min/IP via `_shared/rate-limit.ts` |
| C-3 | ~~Critical~~ → Fixed | `supabase/functions/stripe-webhook/index.ts` | No idempotency guard — replayed Stripe events created duplicate licenses. | Fixed: `webhook_events` table + `INSERT … ON CONFLICT(stripe_event_id) DO NOTHING` |

---

## 🟠 Major Issues (0 open)

*All previously major issues are resolved.*

### Previously Major — Resolved in Prior PRs

| ID | Severity | File | Description | Resolution |
|---|---|---|---|---|
| J-1 | ~~Major~~ → Fixed | `portal.html` | License key was stored in `localStorage` — persists across browser sessions and accessible to any JS on the page. | Fixed: portal now uses in-memory state only; `sessionStorage` for session token |
| J-2 | ~~Major~~ → Fixed | `supabase/functions/send-portal-otp/index.ts` | No brute-force protection on OTP endpoint — attacker could enumerate valid email addresses by probing. | Fixed: 3 sends + 5 verifies per email per 15 min; identical HTTP responses for existing vs. non-existing email |

---

## 🟡 Minor Issues (3 — **Fixed in this PR**)

### M-1 — Webhook Status Badge Used Deprecated Boolean Column

| Field | Value |
|---|---|
| **ID** | M-1 |
| **Severity** | Minor |
| **File** | `python/agentsentinel/dashboard/static/admin/js/pages/webhooks.js:129` |
| **Description** | Badge rendering used `e.processed` (a deprecated boolean column) instead of `e.status` (the string column `pending`/`processed`/`failed` added in migration `012_webhook_events_idempotency.sql`). Failed and pending events always displayed a "processed" badge, making it impossible to distinguish event states in the admin UI. |
| **Recommended Fix** | Change badge logic to `e.status === 'processed'` / `e.status === 'failed'` / `e.status === 'pending'` |
| **Effort** | XS |
| **Status** | ✅ **Fixed in this PR** |

### M-2 — Metrics API Used Deprecated `processed` Column

| Field | Value |
|---|---|
| **ID** | M-2 |
| **Severity** | Minor |
| **File** | `python/agentsentinel/dashboard/static/admin/js/api.js:421` |
| **Description** | `metricsAPI.getOverview()` selected the deprecated `processed` boolean column in its Supabase query and filtered with `w.processed === true` / `w.processed === false`. After migration 012, this column still exists but is no longer kept in sync — the authoritative field is `status`. KPI webhook counts shown in the metrics overview were therefore stale/incorrect. |
| **Recommended Fix** | Change `.select("status")` and filter by `w.status === 'processed'` / `w.status === 'failed'` |
| **Effort** | XS |
| **Status** | ✅ **Fixed in this PR** |

### M-3 — Overview Tier Breakdown Missing `starter` and `pro_team`

| Field | Value |
|---|---|
| **ID** | M-3 |
| **Severity** | Minor |
| **Files** | `python/agentsentinel/dashboard/static/admin/js/api.js:438`; `python/agentsentinel/dashboard/static/admin/js/pages/overview.js:116` |
| **Description** | The `licenses_by_tier` computation in `api.js` only accumulated counts for 4 tiers: `free`, `pro`, `team`, `enterprise`. The `overview.js` tier-breakdown bar chart rendered 6 tier columns but `starter` and `pro_team` always displayed `—` (zero). This masked real license counts for those tiers. |
| **Recommended Fix** | Add `starter` and `pro_team` to the tier accumulation map in `api.js`; assign distinct bar colours in `overview.js` |
| **Effort** | XS |
| **Status** | ✅ **Fixed in this PR** |

---

## 🔵 P1 — Important Before High Traffic (3 open)

These items do not represent security vulnerabilities but should be tracked as GitHub issues and resolved before the service handles significant load.

### P1-1 — No Explicit Fetch Timeouts in Edge Functions

| Field | Value |
|---|---|
| **ID** | P1-1 |
| **Severity** | P1 |
| **Files** | `supabase/functions/validate-license/index.ts`, `supabase/functions/stripe-webhook/index.ts`, `supabase/functions/customer-portal/index.ts` |
| **Description** | Outbound Supabase DB and Resend API calls use default Deno/Node network timeouts. Under high load or a degraded downstream (e.g., Resend API slow), a single slow call can tie up an Edge Function isolate for tens of seconds, causing cascading latency. |
| **Recommended Fix** | Wrap each outbound fetch/DB call with `AbortController` and a 5–10 s timeout. Example: `const { signal } = new AbortController(); setTimeout(() => controller.abort(), 8000);` then pass `{ signal }` to fetch. |
| **Effort** | S |
| **Owner** | Backend |

### P1-2 — DB Integrity Check Not Scheduled as a Cron Job

| Field | Value |
|---|---|
| **ID** | P1-2 |
| **Severity** | P1 |
| **Files** | `scripts/db-integrity-check.sql` |
| **Description** | `scripts/db-integrity-check.sql` contains queries that detect orphaned promo FK references and active licenses past their expiry, but it is not scheduled. Without periodic execution, data integrity violations can accumulate silently. |
| **Recommended Fix** | Schedule the queries as a `pg_cron` job (daily is sufficient). Alternatively, add a GitHub Actions workflow that runs the check against the Supabase DB URL daily and sends a Slack alert on non-zero results. |
| **Effort** | S |
| **Owner** | DevOps |

### P1-3 — No Alerting for Failed Stripe Webhook Events

| Field | Value |
|---|---|
| **ID** | P1-3 |
| **Severity** | P1 |
| **Files** | `supabase/functions/stripe-webhook/index.ts`, `supabase/migrations/012_webhook_events_idempotency.sql` |
| **Description** | When a webhook event fails processing (status set to `'failed'` in `webhook_events`), there is no automated alert. Stripe will retry failed webhooks up to 3 days, but an operator needs to know when `status='failed'` rows appear so they can investigate before retries are exhausted. |
| **Recommended Fix** | Add a `pg_cron` job (or Supabase Database Webhook) that counts `webhook_events WHERE status='failed' AND created_at > NOW()-INTERVAL '1 hour'` and sends a Slack/PagerDuty alert if count > 0. See `docs/operations/webhook-runbook.md` for recovery steps. |
| **Effort** | S |
| **Owner** | DevOps |

---

## 🟢 P2 — Improvements (4 open)

| ID | Severity | File/Area | Description | Effort | Owner |
|---|---|---|---|---|---|
| P2-1 | P2 | `docs/` | `pg_cron` setup documentation for GDPR data retention policy (migration `007_data_retention_and_gdpr.sql` defines the policy but doesn't document how to activate it) | S | Docs |
| P2-2 | P2 | `scripts/` | Performance test harness (k6 or locust) targeting SLA: `validate-license` < 150 ms, `validate-promo` < 200 ms, admin dashboard load < 2 s | L | QA |
| P2-3 | P2 | `python/agentsentinel/dashboard/static/admin/` | Admin SPA assets are not bundled — loads ~15 separate JS files over HTTP/1.1. Use Vite or esbuild for a single bundled output to reduce load time. | L | Frontend |
| P2-4 | P2 | `python/agentsentinel/dashboard/static/admin/js/` | Admin dashboard uses polling for data refresh. Supabase Realtime subscriptions would eliminate the refresh delay for webhook events and license activations. | M | Frontend |

---

## 🟢 P3 — Nice-to-Have (3 open)

| ID | Description | Owner |
|---|---|---|
| P3-1 | Hosted status page (Statuspage.io or equivalent) surfacing uptime for `validate-license`, `validate-promo`, and portal OTP endpoints | DevOps |
| P3-2 | OpenTelemetry / distributed tracing for Edge Functions to correlate Stripe event IDs → license IDs across function boundaries | Backend |
| P3-3 | Admin role-based access control — currently all admins share a single `ADMIN_API_SECRET`; multi-admin RBAC would allow per-user audit trails | Backend |

---

## Summary Table

| Severity | Total | Open | Fixed Prior PRs | Fixed This PR |
|---|---|---|---|---|
| 🔴 Critical | 3 | 0 | 3 | 0 |
| 🟠 Major | 2 | 0 | 2 | 0 |
| 🟡 Minor | 3 | 0 | 0 | 3 |
| 🔵 P1 | 3 | 3 | 0 | 0 |
| 🟢 P2 | 4 | 4 | 0 | 0 |
| 🟢 P3 | 3 | 3 | 0 | 0 |
| **Total** | **18** | **10** | **5** | **3** |
