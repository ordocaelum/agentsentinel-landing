-- Migration: 012_license_validations_outcome.sql
-- Add a validation_outcome column to license_validations to capture structured
-- outcomes beyond the boolean is_valid flag.  This enables analytics queries
-- such as "how many requests were rate-limited?" or "how many had malformed
-- keys?", and fulfils the Phase 4 requirement to log rate-limited calls.
--
-- Outcome values used by the validate-license Edge Function:
--   'valid'         — license key is valid and active
--   'invalid'       — key found but not active (suspended, cancelled, etc.)
--   'not_found'     — key not present in the database
--   'expired'       — license has passed its expires_at date
--   'malformed'     — key does not match any recognised format prefix
--   'rate_limited'  — request was rejected by the rate limiter before DB lookup

ALTER TABLE license_validations
  ADD COLUMN IF NOT EXISTS validation_outcome TEXT
    CHECK (validation_outcome IN (
      'valid',
      'invalid',
      'not_found',
      'expired',
      'malformed',
      'rate_limited'
    ));

-- Index to support filtering/aggregating by outcome in analytics queries.
CREATE INDEX IF NOT EXISTS idx_validations_outcome
  ON license_validations (validation_outcome);

-- Back-fill existing rows from is_valid.
-- Rows that have is_valid = true become 'valid'; others remain NULL
-- (unknown historical outcome) to avoid masking real data.
UPDATE license_validations
SET validation_outcome = 'valid'
WHERE validation_outcome IS NULL
  AND is_valid = true;

COMMENT ON COLUMN license_validations.validation_outcome IS
  'Structured outcome of the validation attempt: valid | invalid | not_found | expired | malformed | rate_limited';
