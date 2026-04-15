-- ============================================
-- AgentSentinel Database Schema
-- ============================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- CUSTOMERS TABLE
-- ============================================
CREATE TABLE customers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email TEXT UNIQUE NOT NULL,
  name TEXT,
  stripe_customer_id TEXT UNIQUE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for email lookups
CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_customers_stripe_id ON customers(stripe_customer_id);

-- ============================================
-- LICENSES TABLE
-- ============================================
CREATE TABLE licenses (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  customer_id UUID REFERENCES customers(id) ON DELETE CASCADE,
  license_key TEXT UNIQUE NOT NULL,
  tier TEXT NOT NULL CHECK (tier IN ('free', 'pro', 'team', 'enterprise')),
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'expired', 'cancelled')),
  stripe_subscription_id TEXT,
  stripe_price_id TEXT,
  agents_limit INTEGER NOT NULL DEFAULT 1,
  events_limit INTEGER NOT NULL DEFAULT 1000,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  expires_at TIMESTAMP WITH TIME ZONE,
  cancelled_at TIMESTAMP WITH TIME ZONE
);

-- Index for license key lookups (used by SDK validation)
CREATE INDEX idx_licenses_key ON licenses(license_key);
CREATE INDEX idx_licenses_customer ON licenses(customer_id);
CREATE INDEX idx_licenses_status ON licenses(status);

-- ============================================
-- WEBHOOK EVENTS TABLE (Audit/Debug)
-- ============================================
CREATE TABLE webhook_events (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  stripe_event_id TEXT UNIQUE NOT NULL,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  processed BOOLEAN DEFAULT FALSE,
  error_message TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  processed_at TIMESTAMP WITH TIME ZONE
);

-- Index for event lookups
CREATE INDEX idx_webhook_events_stripe_id ON webhook_events(stripe_event_id);
CREATE INDEX idx_webhook_events_type ON webhook_events(event_type);

-- ============================================
-- LICENSE VALIDATION LOGS (for analytics)
-- ============================================
CREATE TABLE license_validations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  license_id UUID REFERENCES licenses(id),
  license_key TEXT NOT NULL,
  is_valid BOOLEAN NOT NULL,
  validation_source TEXT, -- 'sdk', 'dashboard', 'api'
  ip_address TEXT,
  user_agent TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for validation analytics
CREATE INDEX idx_validations_license ON license_validations(license_id);
CREATE INDEX idx_validations_created ON license_validations(created_at);

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

-- Function to generate license keys
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
    WHEN 'pro' THEN 'as_pro_'
    WHEN 'team' THEN 'as_team_'
    WHEN 'enterprise' THEN 'as_enterprise_'
    ELSE 'as_free_'
  END;

  RETURN tier_prefix || random_part;
END;
$$ LANGUAGE plpgsql;

-- Function to get tier limits
CREATE OR REPLACE FUNCTION get_tier_limits(tier_name TEXT)
RETURNS TABLE(agents_limit INTEGER, events_limit INTEGER) AS $$
BEGIN
  RETURN QUERY SELECT
    CASE tier_name
      WHEN 'free' THEN 1
      WHEN 'pro' THEN 5
      WHEN 'team' THEN 20
      WHEN 'enterprise' THEN 999999
      ELSE 1
    END AS agents_limit,
    CASE tier_name
      WHEN 'free' THEN 1000
      WHEN 'pro' THEN 50000
      WHEN 'team' THEN 500000
      WHEN 'enterprise' THEN 999999999
      ELSE 1000
    END AS events_limit;
END;
$$ LANGUAGE plpgsql;

-- Updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to customers table
CREATE TRIGGER customers_updated_at
  BEFORE UPDATE ON customers
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- ============================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================

-- Enable RLS on all tables
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE licenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE license_validations ENABLE ROW LEVEL SECURITY;

-- Service role can do everything (for Edge Functions)
CREATE POLICY "Service role full access on customers" ON customers
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on licenses" ON licenses
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on webhook_events" ON webhook_events
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on license_validations" ON license_validations
  FOR ALL USING (auth.role() = 'service_role');
