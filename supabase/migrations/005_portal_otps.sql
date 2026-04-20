-- Migration: 005_portal_otps.sql
-- Creates the portal_otps table for the two-step email OTP authentication
-- flow added to the customer portal in Phase 2.1 of the security roadmap.
--
-- Flow:
--   1. Browser POSTs { email } to send-portal-otp edge function.
--   2. Edge function looks up the customer (existence check only),
--      generates a 6-digit OTP, hashes it, and inserts a row here.
--   3. Browser receives "OTP sent" and prompts the user to enter the code.
--   4. Browser POSTs { email, otp } to customer-portal edge function.
--   5. customer-portal hashes the supplied OTP, compares it to the stored
--      hash, checks expires_at, then deletes the row (single-use) before
--      returning portal data.
--
-- Cleanup:
--   Rows with expires_at < NOW() are never served but remain in the table
--   until explicitly cleaned up.  A lightweight approach is to delete expired
--   rows in the send-portal-otp function before inserting a new one for the
--   same email.  No separate cron job is required.

CREATE TABLE IF NOT EXISTS portal_otps (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email       TEXT NOT NULL,
  otp_hash    TEXT NOT NULL,
  expires_at  TIMESTAMP WITH TIME ZONE NOT NULL,
  created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index to support the lookup by email in both send and verify steps.
CREATE INDEX IF NOT EXISTS idx_portal_otps_email ON portal_otps(email);

-- Index to make the expired-row cleanup query efficient.
CREATE INDEX IF NOT EXISTS idx_portal_otps_expires ON portal_otps(expires_at);

-- RLS: only the service role (Edge Functions) may read or write OTP rows.
ALTER TABLE portal_otps ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on portal_otps" ON portal_otps
  FOR ALL USING (auth.role() = 'service_role');
