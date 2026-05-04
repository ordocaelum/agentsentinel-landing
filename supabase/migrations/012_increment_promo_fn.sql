-- ============================================
-- Atomic promo code usage counter increment
-- ============================================
-- Called by the stripe-webhook Edge Function on checkout.session.completed
-- to avoid the read-then-write race condition that updating
-- used_count = used_count + 1 at the application layer would introduce when
-- multiple checkouts complete simultaneously.

CREATE OR REPLACE FUNCTION increment_promo_used_count(promo_code_id UUID)
RETURNS VOID
LANGUAGE SQL
SECURITY DEFINER
AS $$
  UPDATE promo_codes
  SET used_count = used_count + 1
  WHERE id = promo_code_id;
$$;
