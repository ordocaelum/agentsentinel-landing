# AgentSentinel Supabase Backend

## Setup Instructions

### 1. Install Supabase CLI
```bash
npm install -g supabase
```

### 2. Login to Supabase
```bash
supabase login
```

### 3. Link to your project
```bash
supabase link --project-ref hjjeowbgqyabpacxqbww
```

### 4. Run database migrations
```bash
supabase db push
```

### 5. Set environment secrets
```bash
supabase secrets set STRIPE_SECRET_KEY=sk_live_xxx
supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_xxx
supabase secrets set RESEND_API_KEY=re_xxx
supabase secrets set AGENTSENTINEL_LICENSE_SIGNING_SECRET=your_secret
supabase secrets set STRIPE_PRICE_PRO=price_xxxxx
supabase secrets set STRIPE_PRICE_TEAM=price_xxxxx
supabase secrets set STRIPE_PRICE_ENTERPRISE=price_xxxxx
supabase secrets set STRIPE_PRICE_PRO_TEAM_BASE=price_xxxxx
supabase secrets set STRIPE_PRICE_PRO_TEAM_SEAT=price_xxxxx
# Required for the admin-generate-promo Edge Function:
supabase secrets set ADMIN_API_SECRET=your_strong_secret_here
```

> **Generate a strong secret:**
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```
> Keep this value — you will need to paste it into the Admin API Secret field in the
> admin dashboard setup screen.

### 6. Deploy Edge Functions
```bash
supabase functions deploy stripe-webhook
supabase functions deploy validate-license
supabase functions deploy checkout-team
supabase functions deploy admin-generate-promo
```

### 7. Get your webhook URL
Your Stripe webhook URL will be:
```
https://hjjeowbgqyabpacxqbww.supabase.co/functions/v1/stripe-webhook
```

### 8. Configure Stripe Webhook
1. Go to Stripe Dashboard → Webhooks
2. Add endpoint: `https://hjjeowbgqyabpacxqbww.supabase.co/functions/v1/stripe-webhook`
3. Select events:
   - `checkout.session.completed`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
4. Copy the webhook signing secret
5. Update: `supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_xxx`

## API Endpoints

### Checkout — Pro Team (per-seat)
```bash
curl -X POST https://hjjeowbgqyabpacxqbww.supabase.co/functions/v1/checkout-team \
  -H "Content-Type: application/json" \
  -d '{"seats": 5}'
```

Response:
```json
{
  "checkoutUrl": "https://checkout.stripe.com/c/pay/cs_live_..."
}
```

Redirect the customer to `checkoutUrl` to complete payment. The session includes:
- Base price (`STRIPE_PRICE_PRO_TEAM_BASE`) × 1
- Per-seat price (`STRIPE_PRICE_PRO_TEAM_SEAT`) × seats

### Validate License
```bash
curl -X POST https://hjjeowbgqyabpacxqbww.supabase.co/functions/v1/validate-license \
  -H "Content-Type: application/json" \
  -d '{"license_key": "as_pro_xxxxxxxx"}'
```

Response:
```json
{
  "valid": true,
  "tier": "pro",
  "limits": {
    "max_agents": 5,
    "max_events_per_month": 50000
  },
  "features": {
    "dashboard_enabled": true,
    "integrations_enabled": true,
    "multi_agent_enabled": false,
    "policy_editor": "basic"
  }
}
```

## Database Schema

| Table | Purpose |
|-------|---------|
| `customers` | Customer records linked to Stripe |
| `licenses` | License keys and tier metadata |
| `webhook_events` | Audit log of all Stripe webhook events |
| `license_validations` | Analytics log of every validation call |

## Files

| File | Purpose |
|------|---------|
| `migrations/001_initial_schema.sql` | Database tables, indexes, RLS policies, helper functions |
| `functions/stripe-webhook/index.ts` | Handle Stripe webhook events (checkout, cancellation, payment failure) |
| `functions/validate-license/index.ts` | License validation API used by the SDK |
| `functions/checkout-team/index.ts` | Create Stripe Checkout Session for Pro Team per-seat subscriptions |
| `functions/admin-generate-promo/index.ts` | Admin-only Edge Function to create promo codes (requires `ADMIN_API_SECRET`) |
| `.env.example` | Environment variables template |

## Local Development Checklist

Use this checklist to verify all components are configured before testing promo code creation locally.

### Pre-flight checks

- [ ] `supabase db push` completed without errors (all migrations applied)
- [ ] `ADMIN_API_SECRET` set via `supabase secrets set ADMIN_API_SECRET=...`
- [ ] `admin-generate-promo` function deployed (`supabase functions deploy admin-generate-promo`)
- [ ] Admin dashboard served (see below) and opened in browser
- [ ] Admin API Secret entered in the setup screen — **this field is required** for promo creation

### Serving the admin dashboard locally

Start the Python dashboard server and access the admin SPA at `/admin`:

```bash
# From the repo root:
python -m agentsentinel.dashboard.server
# Then open: http://localhost:8000/admin
```

### Troubleshooting promo code creation failures

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `401 Unauthorized` from Edge Function | `ADMIN_API_SECRET` not set **or** wrong value entered in admin UI | Re-set the secret with `supabase secrets set ADMIN_API_SECRET=...` and ensure the same value is in the Admin API Secret field |
| `404` on `/functions/v1/admin-generate-promo` | Function not deployed | Run `supabase functions deploy admin-generate-promo` |
| CORS error in browser console | Calling Supabase from a non-allowed origin | Use the Python dashboard server (`/admin`) so requests originate from the same allowed context |
| `409 Conflict` | Promo code already exists | Choose a different code name |
| `500` from Edge Function | Missing `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` in function environment | Verify all secrets are set with `supabase secrets list` |

### Verifying the setup end-to-end

```sql
-- 1. Confirm the promo_codes table exists
SELECT EXISTS(
  SELECT 1 FROM information_schema.tables WHERE table_name = 'promo_codes'
) AS table_exists;

-- 2. Inspect RLS policies (should have service-role bypass)
SELECT policy_name, permissive, roles, qual
FROM pg_policies
WHERE tablename = 'promo_codes';

-- 3. List promo codes created in the last hour
SELECT id, code, type, value, active, created_at
FROM promo_codes
WHERE created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;
```
