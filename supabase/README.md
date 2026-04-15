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
```

### 6. Deploy Edge Functions
```bash
supabase functions deploy stripe-webhook
supabase functions deploy validate-license
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
| `.env.example` | Environment variables template |
