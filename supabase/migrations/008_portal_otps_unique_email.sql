-- Migration: 008_portal_otps_unique_email.sql
-- Add a UNIQUE constraint on portal_otps.email to support atomic upsert in
-- the send-portal-otp Edge Function.
--
-- Background: the original schema created a plain (non-unique) index on email.
-- The fix for the concurrent OTP insert race condition (issue #7 in the Phase 1
-- security audit) replaces the delete+insert pattern with an atomic upsert,
-- which requires a UNIQUE index or constraint on the conflict column.
--
-- We also drop the now-redundant plain index to avoid duplicate index overhead.

-- 1. Remove any duplicate rows (keep the most-recent unexpired one per email,
--    or the most recent row if all are expired).  This must run before we can
--    add a unique constraint.
DELETE FROM portal_otps p1
USING portal_otps p2
WHERE p1.email = p2.email
  AND p1.created_at < p2.created_at;

-- 2. Drop the plain index (will be replaced by the unique index below).
DROP INDEX IF EXISTS idx_portal_otps_email;

-- 3. Add the unique constraint; this implicitly creates a unique index named
--    portal_otps_email_key.
ALTER TABLE portal_otps
  ADD CONSTRAINT portal_otps_email_key UNIQUE (email);
