-- ============================================
-- Migration 007: Data Retention & GDPR
-- ============================================
-- Adds soft-delete support, TTL columns, and a suspended license status.
--
-- Retention policy (enforced via scheduled job or pg_cron):
--   webhook_events:      soft-delete after 90 days
--   license_validations: soft-delete after 365 days
--   license_validations ip_address: zeroed out after 30 days (GDPR / PII)
--
-- To configure the automated cleanup, create a pg_cron job:
--   SELECT cron.schedule('retention-cleanup', '0 3 * * *', $$
--     -- Soft-delete old webhook events (90-day retention)
--     UPDATE webhook_events SET deleted_at = NOW()
--       WHERE created_at < NOW() - INTERVAL '90 days' AND deleted_at IS NULL;
--     -- Soft-delete old validation records (365-day retention)
--     UPDATE license_validations SET deleted_at = NOW()
--       WHERE created_at < NOW() - INTERVAL '365 days' AND deleted_at IS NULL;
--     -- Erase IP addresses older than 30 days (GDPR PII erasure)
--     UPDATE license_validations SET ip_address = NULL
--       WHERE created_at < NOW() - INTERVAL '30 days' AND ip_address IS NOT NULL;
--   $$);

-- ── webhook_events: add soft-delete column ─────────────────────────────────
ALTER TABLE webhook_events
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX IF NOT EXISTS idx_webhook_events_deleted ON webhook_events(deleted_at)
  WHERE deleted_at IS NOT NULL;

-- ── license_validations: add soft-delete + GDPR TTL columns ───────────────
ALTER TABLE license_validations
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE;

-- expires_at marks the point at which PII (ip_address) must be erased; it is
-- set to 30 days from row creation by a default expression so every new row
-- gets a TTL automatically.
ALTER TABLE license_validations
  ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITH TIME ZONE
    DEFAULT (NOW() + INTERVAL '30 days');

CREATE INDEX IF NOT EXISTS idx_validations_deleted ON license_validations(deleted_at)
  WHERE deleted_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_validations_expires ON license_validations(expires_at)
  WHERE expires_at IS NOT NULL;

-- ── licenses: add 'suspended' to the status check constraint ──────────────
-- Drop the old constraint first, then recreate it with the additional value.
ALTER TABLE licenses DROP CONSTRAINT IF EXISTS licenses_status_check;
ALTER TABLE licenses
  ADD CONSTRAINT licenses_status_check
    CHECK (status IN ('active', 'suspended', 'revoked', 'expired', 'cancelled'));
