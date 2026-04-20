-- Migration: 007_license_validations_hash.sql
-- Add a license_key_hash column to license_validations so that license keys
-- are not stored in plaintext.  The hash is SHA-256 of the raw license key
-- (hex-encoded), matching the hash produced by the validate-license Edge
-- Function.
--
-- Transition strategy (backward-compatible):
--   Phase 1 (this migration): add license_key_hash; continue writing plaintext
--     license_key as well during the transition window.
--   Phase 2 (2 releases later): remove the plaintext license_key column and
--     update any analytics queries to use license_key_hash.

-- 1. Add the hash column (nullable during transition).
ALTER TABLE license_validations
  ADD COLUMN IF NOT EXISTS license_key_hash TEXT;

-- 2. Back-fill hash values for existing rows using pgcrypto.
--    encode(digest(license_key, 'sha256'), 'hex') produces the same hex string
--    that the Edge Function writes via crypto.subtle.digest("SHA-256", ...).
UPDATE license_validations
SET license_key_hash = encode(digest(license_key, 'sha256'), 'hex')
WHERE license_key_hash IS NULL
  AND license_key IS NOT NULL;

-- 3. Add an index on the hash column to support fast lookups.
CREATE INDEX IF NOT EXISTS idx_validations_license_key_hash
  ON license_validations (license_key_hash);

-- 4. Leave license_key in place for this release cycle.
--    A future migration will drop it once all clients are writing license_key_hash.
COMMENT ON COLUMN license_validations.license_key IS
  'DEPRECATED: plaintext key kept for 2 release cycles. Migrate queries to license_key_hash.';
