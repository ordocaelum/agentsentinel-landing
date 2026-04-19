-- Migration: 003_pro_team_seats.sql
-- Add seat_count column to licenses table for Pro Team per-seat tracking.
-- This column is NULL for Starter, Pro, and Enterprise plans.
-- For Pro Team subscriptions it is set (and kept in sync) by the
-- customer.subscription.created / customer.subscription.updated webhook handlers.

ALTER TABLE licenses
  ADD COLUMN IF NOT EXISTS seat_count INTEGER DEFAULT NULL;

COMMENT ON COLUMN licenses.seat_count IS
  'For Pro Team subscriptions: the number of seats (team members) on this license. '
  'NULL for non-team plans. Synced from the Stripe per-seat subscription item quantity '
  'on customer.subscription.created and customer.subscription.updated webhook events.';
