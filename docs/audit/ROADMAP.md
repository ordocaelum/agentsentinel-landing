# AgentSentinel — Production Readiness Roadmap

**Audit Date:** 2026-05-05  
**Based on:** 9-phase end-to-end audit of the `ordocaelum/agentsentinel-landing` repository

This roadmap is derived entirely from concrete findings during the audit. Every item references the specific files, migrations, and line numbers where the issue was identified. Items are grouped by priority tier and include acceptance criteria so that completion can be objectively verified.

---

## P0 — Blockers for Production

> **All P0 items have been resolved in prior merged PRs.**

No items remain at this priority level. All checks passed.

**Justification:**

The following previously P0-equivalent issues were identified and resolved before this audit was conducted:

1. **`admin-generate-promo` used stale 3-tier `VALID_TIERS`** — prevented admins from issuing promos for `starter`, `pro_team`, and `enterprise` customers. Fixed by importing `VALID_TIERS` from `supabase/functions/_shared/tiers.ts`.
2. **`validate-license` had no rate limiting** — the public endpoint was open to unlimited key enumeration. Fixed by adding `createRateLimiter({ max: 20, windowMs: 60_000 })` from `_shared/rate-limit.ts`.
3. **Stripe webhook had no idempotency guard** — replayed events created duplicate licenses. Fixed via `webhook_events` table with `INSERT … ON CONFLICT(stripe_event_id) DO NOTHING` (migration `012_webhook_events_idempotency.sql`).
4. **License keys stored in `localStorage`** — accessible to any JavaScript on the page. Fixed: portal now uses in-memory state only.
5. **OTP endpoint had no brute-force protection** — email enumeration possible. Fixed: 3 sends + 5 verifies per email per 15 min with `Retry-After` headers and enumeration-resistant responses.

---

## P1 — High Priority (Fix Within 2 Weeks)

These items do not block a launch but must be tracked as GitHub issues and resolved before the service is under significant traffic load. None are security vulnerabilities; all are operational robustness improvements.

---

### P1-1 — Explicit Fetch Timeouts in Edge Functions

| Field | Value |
|---|---|
| **Title** | Add `AbortController` timeouts to all outbound calls in Edge Functions |
| **Rationale** | Edge Functions making outbound calls (Supabase DB client, Resend email API) rely on Deno/Node default network timeouts, which can be many seconds. A slow downstream (e.g., Resend API under load, DB connection pool exhausted) will tie up an isolate indefinitely, causing request queue buildup and cascading latency across all Edge Function invocations. |
| **Affected Files** | `supabase/functions/stripe-webhook/index.ts` (Resend call, DB upserts); `supabase/functions/validate-license/index.ts` (DB lookup); `supabase/functions/customer-portal/index.ts` (DB lookup + token verify); `supabase/functions/send-portal-otp/index.ts` (Resend call) |
| **Acceptance Criteria** | 1. Every outbound `fetch()` call is wrapped with an `AbortController` signal set to ≤ 10 s. 2. Every Supabase client call has a 8 s timeout (set via the `global.fetch` timeout option or a wrapper). 3. When a timeout fires, the function returns an appropriate HTTP error (503 or 500) rather than hanging. 4. A unit test or integration test verifies that the timeout path returns the correct error code. |
| **Estimated Effort** | S (Small — approximately 1–2 hours per function, ~4–8 hours total) |
| **Suggested Owner** | Backend |

---

### P1-2 — Schedule DB Integrity Checks as Recurring Job

| Field | Value |
|---|---|
| **Title** | Schedule `scripts/db-integrity-check.sql` as a daily `pg_cron` job (or GitHub Actions workflow) |
| **Rationale** | `scripts/db-integrity-check.sql` contains SQL queries that detect data integrity violations: orphaned `promo_code_id` references, licenses in `active` status past their `expires_at`, and `promo_codes` with `used_count > max_uses`. These violations cannot occur under normal operation but could accumulate during incidents (failed webhooks, manual DB edits). Without a scheduled check, violations go undetected until a customer reports a problem. |
| **Affected Files** | `scripts/db-integrity-check.sql` (exists; needs scheduling) |
| **Acceptance Criteria** | 1. The integrity check queries run automatically on a daily schedule. 2. If any query returns one or more rows, an alert is sent to a configured Slack channel or email (ops oncall). 3. The schedule and alert destination are documented in `docs/operations/webhook-runbook.md`. 4. A README note in `scripts/` explains how to run the check manually during an incident. Option A (preferred): `SELECT cron.schedule('daily-integrity-check', '0 6 * * *', $$...$$)` via Supabase `pg_cron` extension. Option B: GitHub Actions scheduled workflow (`on: schedule: cron: '0 6 * * *'`) that runs a Deno script against `$SUPABASE_DB_URL`. |
| **Estimated Effort** | S (Small — 2–4 hours including documentation) |
| **Suggested Owner** | DevOps |

---

### P1-3 — Alerting for Failed Stripe Webhook Events

| Field | Value |
|---|---|
| **Title** | Set up automated alert when `webhook_events.status = 'failed'` rows accumulate |
| **Rationale** | When `stripe-webhook` fails to process an event (exception thrown), the row is marked `status='failed'` in `webhook_events`. Stripe will retry for up to 3 days. Without monitoring, the operations team may not notice failed events until Stripe exhausts its retry budget, at which point the license activation is permanently lost and the customer never receives their key. The runbook in `docs/operations/webhook-runbook.md` describes manual recovery but assumes the operator is notified. |
| **Affected Files** | `supabase/functions/stripe-webhook/index.ts`; `supabase/migrations/012_webhook_events_idempotency.sql`; `docs/operations/webhook-runbook.md` |
| **Acceptance Criteria** | 1. A monitoring job (Supabase Database Webhook, `pg_cron`, or GitHub Actions) checks for `webhook_events WHERE status='failed' AND updated_at > NOW() - INTERVAL '1 hour'` at least every 30 minutes. 2. If count > 0, an alert is sent to the designated Slack channel or PagerDuty. 3. The alert message includes the count, the most recent `stripe_event_id`, and a link to the webhook-runbook recovery steps. 4. Alert configuration is documented in `docs/operations/webhook-runbook.md`. |
| **Estimated Effort** | S (Small — 2–4 hours) |
| **Suggested Owner** | DevOps |

---

## P2 — Medium Priority (Fix Within 1 Month)

These improvements increase operational quality and developer experience but do not affect correctness or security.

---

### P2-1 — Document and Activate `pg_cron` for GDPR Data Retention

| Field | Value |
|---|---|
| **Title** | Document and activate the GDPR data retention schedule from migration `007` |
| **Rationale** | Migration `007_data_retention_and_gdpr.sql` defines a data retention policy (e.g., deleting expired `portal_otps`, old `license_validations`, and anonymizing PII after N days) but does not install a `pg_cron` schedule to execute it. The policy is therefore aspirational rather than operational. In GDPR-covered jurisdictions, data minimisation obligations require that the policy actually runs. |
| **Affected Files** | `supabase/migrations/007_data_retention_and_gdpr.sql`; `docs/` (new file: `docs/operations/gdpr-retention-runbook.md`) |
| **Acceptance Criteria** | 1. A new migration (e.g., `013_gdpr_cron_schedule.sql`) installs the `pg_cron` schedule: `SELECT cron.schedule('gdpr-retention', '0 3 * * *', $$<retention SQL>$$)`. 2. A `docs/operations/gdpr-retention-runbook.md` document describes the retention periods, how to change them, how to verify the job has run (query `cron.job_run_details`), and how to handle a failed run. 3. The schedule is tested in staging before deploying to production. |
| **Estimated Effort** | S (Small — 2–4 hours for migration; 2 hours for docs) |
| **Suggested Owner** | Backend + Docs |

---

### P2-2 — Performance Test Harness

| Field | Value |
|---|---|
| **Title** | Add k6 (or locust) load tests targeting `validate-license` and `validate-promo` SLAs |
| **Rationale** | The audit target SLAs are: `validate-license` < 150 ms p95, `validate-promo` < 200 ms p95, admin dashboard load < 2 s. No automated performance tests exist; these numbers have never been measured. Adding a test harness makes SLA verification reproducible and enables regression detection when code changes affect query performance. |
| **Affected Files** | New: `scripts/perf/validate-license.js` (k6 script); `scripts/perf/validate-promo.js`; `.github/workflows/perf-check.yml` (optional CI job on a schedule); `docs/TEST_RESULTS.md` (update Phase 7.4) |
| **Acceptance Criteria** | 1. k6 scripts exist for `validate-license` and `validate-promo`. 2. Scripts can be run with `k6 run scripts/perf/validate-license.js --env BASE_URL=<url>`. 3. Scripts assert p95 latency thresholds (< 150 ms and < 200 ms respectively). 4. A CI/CD job (optional) runs the scripts weekly against the staging environment and fails if thresholds are exceeded. 5. Results are reported in `docs/audit/TEST_RESULTS.md` Phase 7.4. |
| **Estimated Effort** | L (Large — 8–16 hours including CI setup and staging environment setup) |
| **Suggested Owner** | QA / DevOps |

---

### P2-3 — Bundle Admin SPA Assets

| Field | Value |
|---|---|
| **Title** | Bundle the admin dashboard JavaScript with Vite or esbuild to reduce HTTP requests |
| **Rationale** | The admin SPA at `python/agentsentinel/dashboard/static/admin/js/` loads approximately 15–20 separate JavaScript files over HTTP. In production (likely HTTP/1.1 from `server.py` or a reverse proxy without HTTP/2 push), each file requires a separate TCP connection or wait on the connection pool. This results in a waterfall of requests that can exceed the 2 s load-time target on modest connections. Bundling would reduce the load to 2–3 requests (main bundle + CSS + HTML). |
| **Affected Files** | `python/agentsentinel/dashboard/static/admin/js/` (all JS files); new: `python/agentsentinel/dashboard/package.json`, `vite.config.js`; `python/agentsentinel/dashboard/server.py` (serve `dist/` instead of `static/admin/js/`) |
| **Acceptance Criteria** | 1. `npm run build` in `python/agentsentinel/dashboard/` produces a `dist/` directory with a single bundled JS file and source map. 2. `server.py` serves the bundled assets from `dist/` in production mode. 3. All 8 admin pages still render and function correctly after bundling. 4. Chrome DevTools Network waterfall shows ≤ 3 JS/CSS requests for the initial load. 5. `dist/` is added to `.gitignore`. |
| **Estimated Effort** | L (Large — 8–16 hours including testing all 8 admin pages) |
| **Suggested Owner** | Frontend |

---

### P2-4 — Supabase Realtime Subscriptions for Admin Dashboard

| Field | Value |
|---|---|
| **Title** | Replace polling refresh with Supabase Realtime subscriptions in the admin dashboard |
| **Rationale** | The admin dashboard currently refreshes data by polling on a fixed interval (e.g., every 30 s). This means new webhook events and license activations are not visible for up to 30 s after they occur. Supabase Realtime provides PostgreSQL change notifications over WebSocket, allowing instant updates when rows are inserted or updated in `webhook_events`, `licenses`, or `license_validations`. This improves operator awareness during active Stripe checkout sessions. |
| **Affected Files** | `python/agentsentinel/dashboard/static/admin/js/pages/webhooks.js`; `python/agentsentinel/dashboard/static/admin/js/pages/licenses.js`; `python/agentsentinel/dashboard/static/admin/js/pages/overview.js` |
| **Acceptance Criteria** | 1. `webhooks.js` subscribes to `webhook_events` INSERT/UPDATE events via `supabase.channel('webhook-events').on('postgres_changes', ...)`. 2. New webhook events appear in the event log within 2 s of being inserted (Realtime latency). 3. The subscription is torn down (`supabase.removeChannel()`) when the page is unloaded. 4. Polling fallback remains in place in case Realtime is unavailable. 5. Changes are documented in `ADMIN_DASHBOARD.md`. |
| **Estimated Effort** | M (Medium — 4–8 hours) |
| **Suggested Owner** | Frontend |

---

## P3 — Nice-to-Have (Backlog)

These items improve the platform's long-term maintainability and observability but are not required for a successful production launch.

---

### P3-1 — Hosted Status Page

| Field | Value |
|---|---|
| **Title** | Create a public status page for `validate-license`, `validate-promo`, and customer portal uptime |
| **Rationale** | Customers and SDK users have no visibility into system health. When `validate-license` is down, SDK validation silently fails (or returns from cache). A public status page (Statuspage.io, Instatus, or a custom Supabase-backed page) would reduce support ticket volume during incidents by allowing customers to self-diagnose. |
| **Affected Files** | New: `status.html` or external Statuspage.io configuration; `supabase/functions/` (health check EF) |
| **Acceptance Criteria** | 1. A public URL (e.g., `status.agentsentinel.net`) displays the current health of `validate-license`, `validate-promo`, and customer portal. 2. Uptime percentage and incident history for the last 90 days are shown. 3. An automated health-check probe hits each endpoint every 60 s and updates the status page. |
| **Estimated Effort** | M (Medium — 4–8 hours for Statuspage.io setup; L for custom implementation) |
| **Suggested Owner** | DevOps |

---

### P3-2 — OpenTelemetry Distributed Tracing

| Field | Value |
|---|---|
| **Title** | Add OpenTelemetry span propagation across Edge Functions to correlate Stripe event IDs with license IDs |
| **Rationale** | Currently, when debugging a customer issue ("my license wasn't activated"), the operator must manually correlate: Stripe event ID → `webhook_events` row → `licenses` row → `license_validations` rows. This requires multiple manual DB queries. OpenTelemetry trace context propagation would allow a single trace ID to link all of these, making incident response significantly faster. |
| **Affected Files** | `supabase/functions/stripe-webhook/index.ts`; `supabase/functions/validate-license/index.ts`; `supabase/functions/customer-portal/index.ts` |
| **Acceptance Criteria** | 1. Each Edge Function emits OpenTelemetry spans with appropriate attributes (`stripe.event_id`, `license.id`, `customer.email` masked). 2. Spans are exported to a configured collector (e.g., Honeycomb, Grafana Tempo). 3. A trace search by `stripe.event_id` returns the full activation flow in the observability tool. |
| **Estimated Effort** | L (Large — 16–24 hours including instrumentation and observability tool setup) |
| **Suggested Owner** | Backend |

---

### P3-3 — Admin Role-Based Access Control

| Field | Value |
|---|---|
| **Title** | Implement per-user admin accounts with role-based access control |
| **Rationale** | All admins currently share a single `ADMIN_API_SECRET`. This means: (a) audit logs show a generic actor rather than a named user, (b) a compromised secret must be rotated for all admins, and (c) read-only admin access (e.g., for support staff) cannot be granted without also granting full write access. Multi-admin RBAC would address all three. |
| **Affected Files** | New DB table: `admin_users` (id, email, role, hashed_key); `supabase/functions/admin-generate-promo/index.ts` (per-user auth); `python/agentsentinel/dashboard/static/admin/js/auth.js` (per-user login flow); `supabase/migrations/` (new migration) |
| **Acceptance Criteria** | 1. Each admin user has a unique API key stored as bcrypt hash. 2. `admin_logs.actor` records the specific admin user, not a generic identifier. 3. Roles include at minimum `readonly` (can view all data, cannot modify) and `admin` (full access). 4. Key rotation for one user does not affect other users. 5. Existing single-secret flow continues to work as a migration path. |
| **Estimated Effort** | L (Large — 24–40 hours including DB migration, Edge Function changes, and SPA auth flow changes) |
| **Suggested Owner** | Backend + Frontend |

---

## Summary Table

| ID | Priority | Title | Effort | Owner | Status |
|---|---|---|---|---|---|
| — | **P0** | **All P0 items resolved** | — | — | ✅ Complete |
| P1-1 | P1 | Add `AbortController` fetch timeouts to Edge Functions | S | Backend | 🔴 Open |
| P1-2 | P1 | Schedule `db-integrity-check.sql` as daily cron job | S | DevOps | 🔴 Open |
| P1-3 | P1 | Alert on `webhook_events.status='failed'` rows | S | DevOps | 🔴 Open |
| P2-1 | P2 | Document and activate GDPR retention `pg_cron` schedule | S | Backend + Docs | 🟡 Open |
| P2-2 | P2 | Add k6 performance test harness for SLA verification | L | QA | 🟡 Open |
| P2-3 | P2 | Bundle admin SPA assets with Vite/esbuild | L | Frontend | 🟡 Open |
| P2-4 | P2 | Replace polling with Supabase Realtime in admin dashboard | M | Frontend | 🟡 Open |
| P3-1 | P3 | Public status page for uptime visibility | M | DevOps | 🟢 Backlog |
| P3-2 | P3 | OpenTelemetry distributed tracing | L | Backend | 🟢 Backlog |
| P3-3 | P3 | Admin per-user RBAC and individual API keys | L | Backend + Frontend | 🟢 Backlog |

---

*This roadmap was generated from the findings of the 9-phase production-readiness audit conducted on 2026-05-05. All items are based on concrete code review findings with specific file references. The roadmap should be reviewed and reprioritized as the team gathers production traffic data.*
