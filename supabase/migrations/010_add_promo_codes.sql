-- ============================================
-- Promo Codes System
-- ============================================

-- Enable UUID extension (already enabled, but safe to repeat)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- PROMO CODES TABLE
-- ============================================
CREATE TABLE promo_codes (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT UNIQUE NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('discount_percent', 'discount_fixed', 'trial_extension', 'unlimited_trial')),
  value INTEGER NOT NULL, -- percent (0-100), amount in cents, or days
  description TEXT,
  tier TEXT, -- null = all tiers, 'pro' = pro tier only, etc.
  active BOOLEAN DEFAULT true,
  expires_at TIMESTAMP WITH TIME ZONE,
  max_uses INTEGER, -- null = unlimited
  used_count INTEGER DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  created_by TEXT,

  CONSTRAINT valid_uses CHECK (max_uses IS NULL OR used_count <= max_uses)
);

CREATE INDEX idx_promo_code ON promo_codes(code);
CREATE INDEX idx_promo_active ON promo_codes(active);

-- ============================================
-- UPDATE LICENSES TABLE
-- ============================================
ALTER TABLE licenses ADD COLUMN IF NOT EXISTS promo_code_id UUID REFERENCES promo_codes(id) ON DELETE SET NULL;
ALTER TABLE licenses ADD COLUMN IF NOT EXISTS discount_type TEXT; -- 'percent' or 'fixed' or 'trial'
ALTER TABLE licenses ADD COLUMN IF NOT EXISTS discount_value INTEGER DEFAULT 0;
ALTER TABLE licenses ADD COLUMN IF NOT EXISTS promo_applied_at TIMESTAMP WITH TIME ZONE;

-- ============================================
-- ROW LEVEL SECURITY
-- ============================================
ALTER TABLE promo_codes ENABLE ROW LEVEL SECURITY;

-- Service role can do everything
CREATE POLICY "Service role full access on promo_codes" ON promo_codes
  FOR ALL USING (auth.role() = 'service_role');
