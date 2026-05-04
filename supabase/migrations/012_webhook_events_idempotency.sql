-- ============================================================
-- Phase 6.1: Webhook Idempotency — extend webhook_events table
-- ============================================================
-- Adds status lifecycle tracking and a metadata JSONB column to the
-- existing webhook_events table so the stripe-webhook Edge Function can
-- implement proper INSERT … ON CONFLICT deduplication.
--
-- Status values: pending | processed | failed
--   pending   — event inserted but not yet fully processed
--   processed — business logic completed successfully
--   failed    — processing threw an exception; Stripe will retry
--
-- Note: deduplicated events are detected by INSERT … ON CONFLICT returning
-- count=0 and are returned to Stripe immediately without inserting a new row,
-- so there is no 'deduplicated' status stored in this table.
-- ============================================================

-- Add status column (safe to re-run with the IF NOT EXISTS guard on the index).
ALTER TABLE webhook_events
  ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'processed', 'failed'));

-- Add metadata column for storing extracted IDs (license_id, customer_id, etc.)
ALTER TABLE webhook_events
  ADD COLUMN IF NOT EXISTS metadata JSONB;

-- Index on status so the admin dashboard can filter by status efficiently.
CREATE INDEX IF NOT EXISTS idx_webhook_events_status
  ON webhook_events(status);

-- Index on created_at DESC so recent-event queries don't need a seq-scan.
CREATE INDEX IF NOT EXISTS idx_webhook_events_received_at
  ON webhook_events(created_at DESC);

-- Back-fill status for rows that were already processed before this migration.
UPDATE webhook_events
   SET status = 'processed'
 WHERE processed = TRUE
   AND status = 'pending';

-- Back-fill status for rows that have an error message (failed).
UPDATE webhook_events
   SET status = 'failed'
 WHERE processed = FALSE
   AND error_message IS NOT NULL
   AND status = 'pending';
