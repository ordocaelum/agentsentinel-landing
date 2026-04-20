-- Migration: 006_licenses_updated_at.sql
-- Adds an updated_at column to the licenses table and wires up the existing
-- update_updated_at trigger function (defined in 001_initial_schema.sql) so
-- that the column is automatically maintained on every UPDATE.

ALTER TABLE licenses
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Back-fill existing rows so the column is not NULL.
UPDATE licenses SET updated_at = created_at WHERE updated_at IS NULL;

-- Apply the trigger (drop first in case this migration is re-run).
DROP TRIGGER IF EXISTS licenses_updated_at ON licenses;

CREATE TRIGGER licenses_updated_at
  BEFORE UPDATE ON licenses
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();
