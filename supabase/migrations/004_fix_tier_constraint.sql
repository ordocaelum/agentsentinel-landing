-- Migration: 004_fix_tier_constraint.sql
-- Fix the licenses.tier CHECK constraint to include the 'starter' and 'pro_team'
-- tier values that the application layer already uses.  The original schema
-- (001_initial_schema.sql) only allowed 'free', 'pro', 'team', and 'enterprise',
-- which means any attempt to insert a 'starter' or 'pro_team' license would
-- fail with a constraint violation.

-- 1. Drop the existing constraint
ALTER TABLE licenses
  DROP CONSTRAINT IF EXISTS licenses_tier_check;

-- 2. Re-add it with the full set of valid tier names
ALTER TABLE licenses
  ADD CONSTRAINT licenses_tier_check
  CHECK (tier IN ('free', 'starter', 'pro', 'pro_team', 'team', 'enterprise'));

-- 3. Update the SQL generate_license_key() helper to return the correct prefix
--    for the two new tiers.  This function is only used for legacy key
--    generation; new keys use the HMAC-signed asv1_ format from the application
--    layer.  The update is kept for completeness so that any direct SQL call
--    to this function returns a sensibly-prefixed key rather than 'as_free_*'.
CREATE OR REPLACE FUNCTION generate_license_key(tier_name TEXT)
RETURNS TEXT AS $$
DECLARE
  random_part TEXT;
  tier_prefix TEXT;
BEGIN
  -- Generate random alphanumeric string (16 chars)
  random_part := substr(md5(random()::text || clock_timestamp()::text), 1, 16);

  -- Set prefix based on tier
  tier_prefix := CASE tier_name
    WHEN 'starter'    THEN 'as_starter_'
    WHEN 'pro'        THEN 'as_pro_'
    WHEN 'pro_team'   THEN 'as_pro_team_'
    WHEN 'team'       THEN 'as_team_'
    WHEN 'enterprise' THEN 'as_enterprise_'
    ELSE 'as_free_'
  END;

  RETURN tier_prefix || random_part;
END;
$$ LANGUAGE plpgsql;

-- 4. Update the get_tier_limits() helper to handle the new tiers correctly.
--    pro_team mirrors the pro per-seat limits (agents and events are per-seat);
--    starter mirrors the free tier at the DB level (low caps, 1 agent).
CREATE OR REPLACE FUNCTION get_tier_limits(tier_name TEXT)
RETURNS TABLE(agents_limit INTEGER, events_limit INTEGER) AS $$
BEGIN
  RETURN QUERY SELECT
    CASE tier_name
      WHEN 'free'       THEN 1
      WHEN 'starter'    THEN 1
      WHEN 'pro'        THEN 5
      WHEN 'pro_team'   THEN 5
      WHEN 'team'       THEN 20
      WHEN 'enterprise' THEN 999999
      ELSE 1
    END AS agents_limit,
    CASE tier_name
      WHEN 'free'       THEN 1000
      WHEN 'starter'    THEN 1000
      WHEN 'pro'        THEN 50000
      WHEN 'pro_team'   THEN 50000
      WHEN 'team'       THEN 500000
      WHEN 'enterprise' THEN 999999999
      ELSE 1000
    END AS events_limit;
END;
$$ LANGUAGE plpgsql;
