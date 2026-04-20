-- Migration: 009_upsert_customer_fn.sql
-- Provide an atomic "upsert customer while preserving stripe_customer_id"
-- function for the stripe-webhook Edge Function.
--
-- Background: the select-then-update/insert pattern in the Edge Function has a
-- TOCTOU (time-of-check/time-of-use) race condition: two concurrent webhook
-- events for the same email could both see no existing customer and both attempt
-- to INSERT, producing a unique-constraint error.  Using a single atomic
-- INSERT ... ON CONFLICT DO UPDATE eliminates that window.
--
-- Key invariant: stripe_customer_id is preserved on conflict using COALESCE so
-- that a customer who repurchases with a different Stripe account retains access
-- to their original billing portal (Phase 3.5 design requirement).

CREATE OR REPLACE FUNCTION upsert_customer_preserve_stripe_id(
  p_email             TEXT,
  p_name              TEXT,
  p_stripe_customer_id TEXT
)
RETURNS SETOF customers
LANGUAGE sql
AS $$
  INSERT INTO customers (email, name, stripe_customer_id)
  VALUES (p_email, p_name, p_stripe_customer_id)
  ON CONFLICT (email) DO UPDATE
    SET name              = EXCLUDED.name,
        -- Preserve the existing stripe_customer_id; only set it when the row
        -- was just created (i.e. customers.stripe_customer_id IS NULL).
        stripe_customer_id = COALESCE(customers.stripe_customer_id, EXCLUDED.stripe_customer_id)
  RETURNING *;
$$;
