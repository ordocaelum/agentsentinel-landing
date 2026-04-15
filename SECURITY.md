# Security Policy

## Reporting Vulnerabilities

Please report security vulnerabilities privately to **contact@agentsentinel.net**.
Include reproduction steps, impact, and affected versions. Do not open public issues for active vulnerabilities.

## Deployment Security Best Practices

- Run with `AGENTSENTINEL_DEV_MODE=false` in production.
- Store secrets only in environment variables (never in source control).
- Restrict dashboard/network access to trusted origins and private networks.
- Enable TLS termination in front of any public-facing API endpoint.
- Monitor logs for repeated invalid license attempts and webhook failures.

## Required Environment Variables

- `AGENTSENTINEL_LICENSE_API` — backend endpoint for license validation.
- `AGENTSENTINEL_LICENSE_SIGNING_SECRET` — HMAC secret for offline signed license verification.
- `STRIPE_PUBLISHABLE_KEY` — public Stripe key for frontend checkout.
- `STRIPE_SECRET_KEY` — server-side Stripe API key.
- `STRIPE_WEBHOOK_SECRET` — Stripe webhook signature verification secret.
- `AGENTSENTINEL_DEV_MODE` — must be `false` in production.

## Stripe Webhook Verification

1. Configure your webhook endpoint in Stripe Dashboard.
2. Set `STRIPE_WEBHOOK_SECRET` from the endpoint signing secret.
3. Verify the `Stripe-Signature` header against the raw request payload.
4. Reject requests with invalid signatures or stale timestamps.
5. Ensure idempotency by storing processed Stripe event IDs.
