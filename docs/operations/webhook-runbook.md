# Webhook Operations Runbook

This document describes how to operate, monitor, and recover the Stripe webhook pipeline for AgentSentinel.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Inspecting the `webhook_events` Table](#inspecting-the-webhook_events-table)
3. [Replaying a Failed Webhook](#replaying-a-failed-webhook)
4. [Recovery from Stuck `pending` Rows](#recovery-from-stuck-pending-rows)
5. [Deduplication Behaviour](#deduplication-behaviour)
6. [Alerting and Monitoring](#alerting-and-monitoring)

---

## Architecture Overview

Stripe delivers events to:

```
POST https://<supabase-project>.supabase.co/functions/v1/stripe-webhook
```

The Edge Function processes events in this order:

1. **Signature verification** — Stripe-Signature header checked against `STRIPE_WEBHOOK_SECRET`.  Unsigned requests are rejected with HTTP 400.
2. **Idempotency INSERT** — `INSERT INTO webhook_events … ON CONFLICT (stripe_event_id) DO NOTHING`.  If 0 rows are affected the event already exists and a `{ deduplicated: true }` response is returned immediately without re-processing.
3. **Event processing** — Business logic runs (license creation, cancellation, etc.).
4. **Status update** — Row is updated to `status='processed'` on success, or `status='failed'` with `error_message` on failure.

### Status lifecycle

| Status       | Meaning                                                  |
|--------------|----------------------------------------------------------|
| `pending`    | Inserted; processing not yet complete.                   |
| `processed`  | Successfully processed.                                  |
| `failed`     | Processing threw an exception; Stripe will retry.        |
| `deduplicated` | Second delivery of an already-processed event_id.     |

---

## Inspecting the `webhook_events` Table

### Recent events

```sql
SELECT
  stripe_event_id,
  event_type,
  status,
  error_message,
  created_at,
  processed_at
FROM webhook_events
ORDER BY created_at DESC
LIMIT 50;
```

### Failed events (Stripe is currently retrying)

```sql
SELECT *
FROM webhook_events
WHERE status = 'failed'
ORDER BY created_at DESC;
```

### Stuck pending rows (processing started but never completed)

```sql
SELECT *
FROM webhook_events
WHERE status = 'pending'
  AND created_at < NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;
```

### Deduplication rate (how often Stripe is retrying)

```sql
SELECT
  DATE_TRUNC('day', created_at) AS day,
  COUNT(*) FILTER (WHERE status = 'processed')   AS processed,
  COUNT(*) FILTER (WHERE status = 'failed')      AS failed,
  COUNT(*) FILTER (WHERE status = 'pending')     AS pending,
  COUNT(*) FILTER (WHERE status = 'deduplicated') AS deduplicated
FROM webhook_events
GROUP BY 1
ORDER BY 1 DESC
LIMIT 7;
```

---

## Replaying a Failed Webhook

### Option A — Stripe Dashboard (recommended)

1. Go to [Stripe Dashboard → Developers → Webhooks](https://dashboard.stripe.com/webhooks).
2. Select the AgentSentinel endpoint.
3. Find the failed event and click **Resend**.

Because the Edge Function uses `ON CONFLICT DO NOTHING` on the existing `stripe_event_id`, a Stripe resend of the **same** event_id will be deduplicated — the handler returns `{ deduplicated: true }` without re-processing.

**To force a full re-process:** Delete the row from `webhook_events` first (see below), then resend from Stripe.

### Option B — Manual row deletion + Stripe resend

```sql
-- Remove the stuck/failed row so the next delivery is treated as new.
DELETE FROM webhook_events
WHERE stripe_event_id = 'evt_XXXXXXXXXXXX';
```

Then resend the event from the Stripe Dashboard.

### Option C — Stripe CLI (local / staging)

```bash
# Forward Stripe events to a local or staging function
stripe listen --forward-to https://<project>.supabase.co/functions/v1/stripe-webhook

# Resend a specific event
stripe events resend evt_XXXXXXXXXXXX
```

---

## Recovery from Stuck `pending` Rows

A row stays `pending` if the Edge Function crashed mid-processing (e.g. a timeout or an unhandled exception that skipped the error-update path).

### Identify stuck rows

```sql
SELECT stripe_event_id, event_type, created_at
FROM webhook_events
WHERE status = 'pending'
  AND created_at < NOW() - INTERVAL '30 minutes';
```

### Decision tree

| Situation                                          | Action                                                                |
|----------------------------------------------------|-----------------------------------------------------------------------|
| Stripe already retried and row is still `pending`  | Delete the row and let Stripe's next retry claim it fresh.            |
| Stripe retry window has expired                    | Manually resend from Stripe Dashboard + delete the stuck row first.   |
| The corresponding license/customer row was created | Mark the stuck row as `processed` manually (see below).               |

### Mark a stuck row as manually processed

```sql
UPDATE webhook_events
SET status = 'processed',
    processed_at = NOW(),
    error_message = 'Manually resolved by ops — see incident #NNN'
WHERE stripe_event_id = 'evt_XXXXXXXXXXXX'
  AND status = 'pending';
```

---

## Deduplication Behaviour

The `stripe_event_id` column has a `UNIQUE` constraint.  The Edge Function uses:

```sql
INSERT INTO webhook_events (stripe_event_id, …) ON CONFLICT (stripe_event_id) DO NOTHING
```

and inspects the returned `count`:

- **`count = 1`** — new event, proceed to process.
- **`count = 0`** — duplicate; return `{ deduplicated: true }` with HTTP 200.

This guarantees that no business logic (license creation, promo increment, etc.) runs more than once per `event_id`, even if Stripe delivers the event multiple times.

> **Note:** To force a re-process (e.g. to recover from a bug), delete the row from `webhook_events` first, then resend the event from Stripe.

---

## Alerting and Monitoring

### Recommended alerts

| Condition                                          | Severity | Action                                                  |
|----------------------------------------------------|----------|---------------------------------------------------------|
| `status = 'failed'` rows older than 1 hour         | High     | Page on-call; check Edge Function logs; resend.         |
| `status = 'pending'` rows older than 30 minutes    | Medium   | Check if Stripe is still retrying; may need manual fix. |
| Deduplication rate > 20% in a 24h window           | Low      | Investigate Stripe retry behaviour; may indicate flaky endpoint. |

### View Edge Function logs

```bash
# Real-time logs
supabase functions logs stripe-webhook --tail

# Last 100 lines
supabase functions logs stripe-webhook --limit 100
```

### Useful log patterns

```
📩 Received Stripe event:          — new event received
⏭ Deduplicated Stripe event …      — already-processed replay
✅ Checkout complete for …          — license created successfully
❌ License suspended for …          — payment failure handled
Webhook processing error: …         — processing threw; Stripe will retry
Failed to mark webhook as failed:   — DB update failed after processing error
```
