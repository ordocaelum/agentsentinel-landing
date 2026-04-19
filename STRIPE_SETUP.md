# Stripe Pro Team Per-Seat Pricing — Setup Guide

This document describes the full integration between the AgentSentinel landing page,
Supabase Edge Functions, and Stripe for the **Pro Team** per-seat subscription plan.

---

## Architecture Overview

```
Browser (pricing-team.html)
  └─ POST { seats } ──────────────────────────────────────────────►
                          Supabase Edge Function: checkout-team
                          (supabase/functions/checkout-team/index.ts)
                            └─ stripe.checkout.sessions.create()
                                 line_items:
                                   [{ price: BASE,  qty: 1     },
                                    { price: SEAT,  qty: seats }]
                          ◄── { url: session.url } ───────────────
  └─ window.location.href = url
         │
         ▼
    Stripe Checkout (hosted page — customer enters card)
         │  checkout.session.completed
         ▼
    Stripe Webhook ──────────────────────────────────────────────►
                          Supabase Edge Function: stripe-webhook
                          (supabase/functions/stripe-webhook/index.ts)
                            └─ Generate license key
                            └─ Insert into licenses (with seat_count)
                            └─ Send welcome email via Resend
         │  customer.subscription.updated  (seat count changes)
         └────────────────────────────────────────────────────────►
                          stripe-webhook
                            └─ Update licenses.seat_count
```

---

## Price IDs

See Supabase secrets `STRIPE_PRICE_PRO_TEAM_BASE` and `STRIPE_PRICE_PRO_TEAM_SEAT` for the actual price IDs.
Set them using:

```bash
supabase secrets set STRIPE_PRICE_PRO_TEAM_BASE=<base_price_id>
supabase secrets set STRIPE_PRICE_PRO_TEAM_SEAT=<per_seat_price_id>
```

| Product | Env Var | Amount |
|---------|---------|--------|
| Pro Team Base | `STRIPE_PRICE_PRO_TEAM_BASE` | $49 / month |
| Pro Team Per-Seat | `STRIPE_PRICE_PRO_TEAM_SEAT` | $29 / seat / month |

**Invoice formula:** `$49 + ($29 × seat_count)`

---

## Webhook Endpoint

**URL:** `https://hjjeowbgqyabpacxqbww.supabase.co/functions/v1/stripe-webhook`

> **Note:** This URL is specific to the AgentSentinel Supabase project. Replace with your
> project's URL if redeploying to a different Supabase project.

### Registered Events

| Event | Purpose |
|-------|---------|
| `checkout.session.completed` | Create customer, generate & email license key |
| `customer.subscription.created` | Set initial `seat_count` on the license |
| `customer.subscription.updated` | Sync `seat_count` when team size changes |
| `customer.subscription.deleted` | Mark license as cancelled |
| `invoice.payment_failed` | Log payment failure |
| `invoice.upcoming` | Send Pro intro-pricing reminder emails |

### Registering the Webhook

1. Go to [Stripe Dashboard → Webhooks](https://dashboard.stripe.com/webhooks)
2. Click **+ Add endpoint**
3. Endpoint URL: `https://hjjeowbgqyabpacxqbww.supabase.co/functions/v1/stripe-webhook`
4. Select the events listed above
5. Copy the **Signing secret** (`whsec_…`) and add it as a Supabase secret:

```bash
supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_your_signing_secret_here
```

---

## Supabase Secrets Required

```bash
# Stripe API key (server-side only — never expose in browser)
supabase secrets set STRIPE_SECRET_KEY=sk_live_your_key_here

# Webhook signing secret (from Stripe Dashboard → Webhooks)
supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_your_secret_here

# Pro Team price IDs (from Stripe Dashboard → Products)
supabase secrets set STRIPE_PRICE_PRO_TEAM_BASE=<base_price_id>
supabase secrets set STRIPE_PRICE_PRO_TEAM_SEAT=<per_seat_price_id>

# Base site URL used for Stripe redirect URLs (defaults to https://agentsentinel.net)
supabase secrets set SITE_BASE_URL=https://agentsentinel.net

# License signing secret (for HMAC-signed asv1_ license keys)
supabase secrets set AGENTSENTINEL_LICENSE_SIGNING_SECRET=replace_with_random_secret

# Resend API key (for sending license-key emails)
supabase secrets set RESEND_API_KEY=re_your_key_here
```

---

## Database Schema

Run migration `003_pro_team_seats.sql` to add the `seat_count` column:

```sql
ALTER TABLE licenses
  ADD COLUMN IF NOT EXISTS seat_count INTEGER DEFAULT NULL;
```

The `licenses` table now stores:

| Column | Type | Notes |
|--------|------|-------|
| `stripe_subscription_id` | TEXT | Used to look up subscription on webhook events |
| `seat_count` | INTEGER | NULL for non-team plans; synced from Stripe on every subscription event |
| `tier` | TEXT | `'pro_team'` for team subscriptions |

---

## Backend Reference: checkout-team Edge Function

Located at `supabase/functions/checkout-team/index.ts`.

**Request:**
```http
POST https://hjjeowbgqyabpacxqbww.supabase.co/functions/v1/checkout-team
Content-Type: application/json

{ "seats": 5 }
```

**Response:**
```json
{ "url": "https://checkout.stripe.com/c/pay/..." }
```

**Stripe session created:**
```javascript
stripe.checkout.sessions.create({
  payment_method_types: ['card'],
  mode: 'subscription',
  line_items: [
    { price: process.env.STRIPE_PRICE_PRO_TEAM_BASE, quantity: 1 },      // $49 base
    { price: process.env.STRIPE_PRICE_PRO_TEAM_SEAT, quantity: seats },   // $29/seat
  ],
  metadata: { tier: 'pro_team', seat_count: String(seats) },
  success_url: 'https://agentsentinel.net/success.html',
  cancel_url:  'https://agentsentinel.net/pricing-team.html',
});
```

---

## Updating Seat Count After Initial Signup

When a customer adds or removes team members, update the subscription quantity via the
[Stripe Billing Portal](https://dashboard.stripe.com/settings/billing/portal) (self-service)
or directly via the API:

### Node.js / TypeScript
```typescript
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

async function updateProTeamSeats(subscriptionId: string, newSeatCount: number) {
  const subscription = await stripe.subscriptions.retrieve(subscriptionId);

  // Find the per-seat line item
  const perSeatItem = subscription.items.data.find(
    (item) => item.price.id === process.env.STRIPE_PRICE_PRO_TEAM_SEAT,
  );
  if (!perSeatItem) throw new Error('Per-seat item not found on subscription');

  return stripe.subscriptions.update(subscriptionId, {
    items: [{ id: perSeatItem.id, quantity: newSeatCount }],
    proration_behavior: 'create_prorations',
  });
}
```

### Python
```python
import stripe
stripe.api_key = os.environ['STRIPE_SECRET_KEY']

def update_pro_team_seats(subscription_id: str, new_seat_count: int):
    subscription = stripe.Subscription.retrieve(subscription_id)
    per_seat_item = next(
        (item for item in subscription['items']['data']
         if item['price']['id'] == os.environ['STRIPE_PRICE_PRO_TEAM_SEAT']),
        None,
    )
    if not per_seat_item:
        raise ValueError('Per-seat item not found on subscription')

    return stripe.Subscription.modify(
        subscription_id,
        items=[{'id': per_seat_item['id'], 'quantity': new_seat_count}],
        proration_behavior='create_prorations',
    )
```

---

## Webhook Handler: Syncing Seat Counts

The `stripe-webhook` function handles `customer.subscription.created` and
`customer.subscription.updated` by finding the per-seat item and updating
`licenses.seat_count`:

```typescript
// Simplified excerpt from supabase/functions/stripe-webhook/index.ts
if (
  event.type === 'customer.subscription.created' ||
  event.type === 'customer.subscription.updated'
) {
  const subscription = event.data.object as Stripe.Subscription;
  const perSeatPriceId = Deno.env.get('STRIPE_PRICE_PRO_TEAM_SEAT');

  const perSeatItem = subscription.items.data.find(
    (item) => perSeatPriceId && item.price.id === perSeatPriceId,
  );

  if (perSeatItem) {
    await supabase
      .from('licenses')
      .update({ seat_count: perSeatItem.quantity })
      .eq('stripe_subscription_id', subscription.id);
  }
}
```

---

## Enabling Self-Service Seat Management

Allow customers to adjust their own seat count without contacting support:

1. Go to [Stripe Dashboard → Billing Portal Settings](https://dashboard.stripe.com/settings/billing/portal)
2. Enable the **Subscriptions** section
3. Check **Allow customers to update quantities**
4. Save changes

Customers can then use the portal (accessible from your `/portal.html` page) to add or
remove seats, and your webhook will automatically sync the new count.

---

## Testing

Use [Stripe test mode](https://dashboard.stripe.com/test/dashboard) with test price IDs
and the Stripe CLI to forward webhooks locally:

```bash
stripe listen --forward-to https://hjjeowbgqyabpacxqbww.supabase.co/functions/v1/stripe-webhook
```

Test card numbers:
- `4242 4242 4242 4242` — succeeds
- `4000 0000 0000 9995` — declines
