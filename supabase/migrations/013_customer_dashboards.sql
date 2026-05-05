-- AgentSentinel — Customer Dashboard tables
-- Migration 013: customer_dashboards + agent_events

-- ── customer_dashboards ──────────────────────────────────────────────────────
-- One row per purchased license.  dashboard_token is the unguessable
-- URL segment used for token-based authentication (embedded in the URL so
-- customers need no separate login).  webhook_secret is shared with the SDK
-- and sent as X-Webhook-Secret on every streamed event.

CREATE TABLE IF NOT EXISTS customer_dashboards (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  license_id       UUID REFERENCES licenses(id) ON DELETE CASCADE,
  customer_id      UUID REFERENCES customers(id) ON DELETE CASCADE,
  dashboard_token  UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
  webhook_secret   UUID NOT NULL DEFAULT gen_random_uuid(),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status           TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active', 'paused', 'deleted')),
  config           JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS customer_dashboards_license_id_idx
  ON customer_dashboards (license_id);
CREATE INDEX IF NOT EXISTS customer_dashboards_customer_id_idx
  ON customer_dashboards (customer_id);

-- ── agent_events ─────────────────────────────────────────────────────────────
-- Raw event stream from the SDK → Edge Function → DB.
-- status matches the EventPayload contract: allowed | blocked | pending | expired
-- plus the synthetic dashboard_created value written on first setup.

CREATE TABLE IF NOT EXISTS agent_events (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dashboard_id  UUID REFERENCES customer_dashboards(id) ON DELETE CASCADE,
  agent_id      TEXT,
  tool_name     TEXT,
  status        TEXT CHECK (
                  status IN ('allowed','blocked','pending','expired','dashboard_created')
                ),
  cost          DECIMAL(10,4),
  timestamp     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  metadata      JSONB
);

CREATE INDEX IF NOT EXISTS agent_events_dashboard_ts_idx
  ON agent_events (dashboard_id, timestamp DESC);

-- ── Row Level Security ───────────────────────────────────────────────────────
-- Service-role key bypasses RLS automatically.
-- Customers may only SELECT rows that belong to their dashboard_token.
-- No direct INSERT / UPDATE / DELETE from the public anon role.

ALTER TABLE customer_dashboards ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_events ENABLE ROW LEVEL SECURITY;

-- customer_dashboards: read by matching dashboard_token passed as a session variable
--   set_config('app.dashboard_token', '<token>', true)
-- (the Edge Functions set this before querying with the anon client)

DROP POLICY IF EXISTS customer_dashboards_read ON customer_dashboards;
CREATE POLICY customer_dashboards_read
  ON customer_dashboards
  FOR SELECT
  USING (dashboard_token::text = current_setting('app.dashboard_token', true));

-- agent_events: read by joining through customer_dashboards so the same token
-- restriction is enforced transitively.

DROP POLICY IF EXISTS agent_events_read ON agent_events;
CREATE POLICY agent_events_read
  ON agent_events
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM customer_dashboards cd
      WHERE cd.id = agent_events.dashboard_id
        AND cd.dashboard_token::text = current_setting('app.dashboard_token', true)
    )
  );
