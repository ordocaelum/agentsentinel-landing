-- =============================================================================
-- AgentSentinel — Database Integrity Checks
-- =============================================================================
-- Run this script against your Supabase database to verify referential integrity
-- and detect common data quality issues.
--
-- Usage (Supabase SQL editor or psql):
--   psql "postgresql://postgres:PASSWORD@db.YOUR_REF.supabase.co:5432/postgres" \
--        -f scripts/db-integrity-check.sql
--
-- All queries should return 0 rows/0 count for a healthy database.
-- Non-zero results indicate data integrity issues that require remediation.
-- =============================================================================

\echo ''
\echo '===== AgentSentinel Database Integrity Checks ====='
\echo ''

-- ─── CHECK 1: Orphaned promo_code_id references ──────────────────────────────
-- Licenses that reference a promo_code_id that no longer exists.
-- Expected: 0 rows
\echo '--- CHECK 1: Orphaned promo_code_id references ---'
\echo 'Expected: 0 rows'
SELECT
    l.id          AS license_id,
    l.license_key AS license_key_prefix,
    l.promo_code_id,
    l.created_at
FROM licenses l
WHERE l.promo_code_id IS NOT NULL
  AND l.promo_code_id NOT IN (SELECT id FROM promo_codes);

SELECT COUNT(*) AS orphaned_promo_refs
FROM licenses
WHERE promo_code_id IS NOT NULL
  AND promo_code_id NOT IN (SELECT id FROM promo_codes);

\echo ''

-- ─── CHECK 2: Active licenses past their expiration date ─────────────────────
-- Licenses marked active but whose expires_at is in the past.
-- Expected: 0 rows (these should be transitioned to 'expired' by the webhook or a cron job)
\echo '--- CHECK 2: Active licenses past expiration ---'
\echo 'Expected: 0 rows'
SELECT
    id,
    license_key,
    tier,
    expires_at,
    NOW() - expires_at AS overdue_by
FROM licenses
WHERE expires_at < NOW()
  AND status = 'active'
ORDER BY expires_at ASC;

SELECT COUNT(*) AS active_but_expired
FROM licenses
WHERE expires_at < NOW()
  AND status = 'active';

\echo ''

-- ─── CHECK 3: Licenses with invalid tier values ───────────────────────────────
-- Licenses whose tier is not in the canonical set.
-- Expected: 0 rows
\echo '--- CHECK 3: Licenses with invalid tier values ---'
\echo 'Expected: 0 rows'
SELECT id, license_key, tier, status, created_at
FROM licenses
WHERE tier NOT IN ('free', 'starter', 'pro', 'pro_team', 'team', 'enterprise')
ORDER BY created_at DESC;

SELECT COUNT(*) AS invalid_tier_count
FROM licenses
WHERE tier NOT IN ('free', 'starter', 'pro', 'pro_team', 'team', 'enterprise');

\echo ''

-- ─── CHECK 4: Promo codes with used_count > max_uses ─────────────────────────
-- Promo codes that have been redeemed more times than their limit allows.
-- Expected: 0 rows
\echo '--- CHECK 4: Over-redeemed promo codes ---'
\echo 'Expected: 0 rows'
SELECT
    id,
    code,
    type,
    max_uses,
    used_count,
    used_count - max_uses AS over_by
FROM promo_codes
WHERE max_uses IS NOT NULL
  AND used_count > max_uses
ORDER BY (used_count - max_uses) DESC;

SELECT COUNT(*) AS over_redeemed_promos
FROM promo_codes
WHERE max_uses IS NOT NULL
  AND used_count > max_uses;

\echo ''

-- ─── CHECK 5: Licenses without a corresponding customer ──────────────────────
-- Licenses that reference a customer_id that no longer exists.
-- Expected: 0 rows
\echo '--- CHECK 5: Licenses with missing customer records ---'
\echo 'Expected: 0 rows'
SELECT
    l.id          AS license_id,
    l.license_key,
    l.customer_id,
    l.created_at
FROM licenses l
WHERE l.customer_id IS NOT NULL
  AND l.customer_id NOT IN (SELECT id FROM customers);

SELECT COUNT(*) AS orphaned_customer_refs
FROM licenses
WHERE customer_id IS NOT NULL
  AND customer_id NOT IN (SELECT id FROM customers);

\echo ''

-- ─── CHECK 6: Webhook events stuck in 'pending' for more than 1 hour ─────────
-- Events that have been pending for an unusually long time may indicate
-- processing failures that were not properly recorded.
-- Expected: 0 rows (or investigate any that appear)
\echo '--- CHECK 6: Webhook events stuck in pending >1h ---'
\echo 'Expected: 0 rows (investigate any found)'
SELECT
    id,
    stripe_event_id,
    event_type,
    status,
    created_at,
    NOW() - created_at AS age
FROM webhook_events
WHERE status = 'pending'
  AND created_at < NOW() - INTERVAL '1 hour'
ORDER BY created_at ASC;

SELECT COUNT(*) AS stuck_pending_webhooks
FROM webhook_events
WHERE status = 'pending'
  AND created_at < NOW() - INTERVAL '1 hour';

\echo ''

-- ─── CHECK 7: Duplicate license keys ─────────────────────────────────────────
-- Each license key should be globally unique.
-- Expected: 0 rows
\echo '--- CHECK 7: Duplicate license keys ---'
\echo 'Expected: 0 rows'
SELECT
    license_key,
    COUNT(*) AS duplicate_count
FROM licenses
GROUP BY license_key
HAVING COUNT(*) > 1;

SELECT COUNT(*) AS duplicate_key_groups
FROM (
    SELECT license_key
    FROM licenses
    GROUP BY license_key
    HAVING COUNT(*) > 1
) sub;

\echo ''

-- ─── CHECK 8: Portal OTPs that are verified but not consumed ─────────────────
-- Verified OTPs should be marked used. Lingering verified OTPs could allow
-- replay attacks if the expiry window is still open.
-- Expected: 0 rows
\echo '--- CHECK 8: Stale verified OTPs (not consumed within 10 minutes) ---'
\echo 'Expected: 0 rows'
SELECT
    id,
    email,
    verified,
    created_at,
    expires_at
FROM portal_otps
WHERE verified = TRUE
  AND created_at < NOW() - INTERVAL '10 minutes'
  AND expires_at > NOW()
ORDER BY created_at ASC;

SELECT COUNT(*) AS stale_verified_otps
FROM portal_otps
WHERE verified = TRUE
  AND created_at < NOW() - INTERVAL '10 minutes'
  AND expires_at > NOW();

\echo ''

-- ─── SUMMARY ──────────────────────────────────────────────────────────────────
\echo '===== Summary ====='
\echo 'Review the counts above. All should be 0 for a healthy database.'
\echo 'Non-zero counts indicate data issues requiring remediation.'
\echo ''
\echo 'Remediation commands:'
\echo '  -- Fix active licenses past expiry:'
\echo '  UPDATE licenses SET status = ''expired'' WHERE expires_at < NOW() AND status = ''active'';'
\echo ''
\echo '  -- Reset over-redeemed promo used_count to max_uses:'
\echo '  UPDATE promo_codes SET used_count = max_uses WHERE max_uses IS NOT NULL AND used_count > max_uses;'
\echo ''
\echo '  -- Mark stuck pending webhooks as failed:'
\echo '  UPDATE webhook_events SET status = ''failed'', error_message = ''Stuck in pending — manually marked failed'''
\echo '  WHERE status = ''pending'' AND created_at < NOW() - INTERVAL ''1 hour'';'
\echo ''
