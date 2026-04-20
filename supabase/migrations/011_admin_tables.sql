-- ============================================
-- Admin Dashboard Tables
-- ============================================

-- Enable UUID extension (already enabled, but safe to repeat)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- ADMIN LOGS TABLE (immutable audit trail)
-- ============================================
CREATE TABLE IF NOT EXISTS admin_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  admin_id TEXT NOT NULL,              -- email or user ID of the admin who acted
  action TEXT NOT NULL,                -- 'created', 'updated', 'deleted', 'suspended', etc.
  entity_type TEXT NOT NULL,           -- 'license', 'promo', 'user', 'system', etc.
  entity_id UUID,                      -- ID of the affected entity
  old_values JSONB,                    -- state before the change
  new_values JSONB,                    -- state after the change
  ip_address TEXT,
  user_agent TEXT,
  status TEXT DEFAULT 'success'
    CHECK (status IN ('success', 'failure')),
  error_message TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_logs_admin   ON admin_logs(admin_id);
CREATE INDEX IF NOT EXISTS idx_admin_logs_entity  ON admin_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_admin_logs_created ON admin_logs(created_at DESC);

-- ============================================
-- DASHBOARD METRICS TABLE (cached KPIs)
-- ============================================
CREATE TABLE IF NOT EXISTS dashboard_metrics (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  metric_key TEXT UNIQUE NOT NULL,     -- 'revenue_today', 'active_users', etc.
  metric_value NUMERIC,
  metadata JSONB,                      -- optional extra data (breakdown by tier, etc.)
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_metrics_key ON dashboard_metrics(metric_key);

-- ============================================
-- ROW LEVEL SECURITY
-- ============================================

ALTER TABLE admin_logs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE dashboard_metrics ENABLE ROW LEVEL SECURITY;

-- Service role has full access (used by Edge Functions)
CREATE POLICY "Service role full access on admin_logs" ON admin_logs
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on dashboard_metrics" ON dashboard_metrics
  FOR ALL USING (auth.role() = 'service_role');

-- ============================================
-- SEED INITIAL METRIC KEYS (optional defaults)
-- ============================================
INSERT INTO dashboard_metrics (metric_key, metric_value, metadata) VALUES
  ('active_licenses',   0, '{}'),
  ('active_users',      0, '{}'),
  ('revenue_today',     0, '{}'),
  ('revenue_this_month',0, '{}'),
  ('failed_webhooks',   0, '{}'),
  ('promo_codes_used',  0, '{}')
ON CONFLICT (metric_key) DO NOTHING;
