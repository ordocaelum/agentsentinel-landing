# AgentSentinel SDK Integration Guide

> **TL;DR:** Get from zero to a licensed, monitored AI agent in 5 minutes. Install the SDK, set your license key, and wrap your agent calls.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Python SDK — 5-Minute Quickstart](#2-python-sdk--5-minute-quickstart)
3. [TypeScript SDK — 5-Minute Quickstart](#3-typescript-sdk--5-minute-quickstart)
4. [Environment Variables](#4-environment-variables)
5. [License Key Formats](#5-license-key-formats)
6. [Rate Limits](#6-rate-limits)
7. [Offline HMAC Verification](#7-offline-hmac-verification)
8. [Error Codes and Retry Guidance](#8-error-codes-and-retry-guidance)
9. [Framework Integrations](#9-framework-integrations)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Prerequisites

- **Python:** 3.9+ (for the Python SDK)
- **Node.js:** 18+ (for the TypeScript/JavaScript SDK)
- **License key:** Get yours at [agentsentinel.net/portal](https://agentsentinel.net/portal). Format: `asv1_…` or `as_pro_…`

---

## 2. Python SDK — 5-Minute Quickstart

### Step 1 — Install

```bash
pip install agentsentinel-core
```

Or add to your `requirements.txt`:
```
agentsentinel-core>=0.1.0
```

### Step 2 — Set your license key

The SDK reads the key from the environment. This keeps your key out of source code.

```bash
export AGENTSENTINEL_LICENSE_KEY="asv1_your_license_key_here"
```

Or in a `.env` file (loaded by `python-dotenv` or similar):

```dotenv
AGENTSENTINEL_LICENSE_KEY=asv1_your_license_key_here
```

> **Security:** Never put your license key directly in source code or commit it to Git.

### Step 3 — Protect your first tool

```python
from agentsentinel import AgentPolicy, AgentGuard, BudgetExceededError, ApprovalRequiredError

# Define your policy
policy = AgentPolicy(
    daily_budget=10.0,          # max $10/day in tool costs
    hourly_budget=2.0,          # max $2/hour
    require_approval=["send_email", "delete_*"],  # gate these tools
    rate_limits={"search_web": "10/min"},          # 10 searches per minute
    audit_log=True,             # log every tool call
)

guard = AgentGuard(policy=policy)

@guard.protect(tool_name="search_web", cost=0.01)
def search_web(query: str) -> str:
    return f"Results for: {query}"

@guard.protect(tool_name="send_email")
def send_email(to: str, subject: str, body: str):
    print(f"Sending email to {to}")

# This works — within budget and rate limit
result = search_web("AI safety best practices")

# This raises ApprovalRequiredError (DenyAllApprover by default)
try:
    send_email("user@example.com", "Hello", "Test")
except ApprovalRequiredError as e:
    print(f"Blocked: {e}")
```

### Step 4 — Verify it works

```bash
python -c "
from agentsentinel import AgentSentinel
s = AgentSentinel()
print('✅ Licensed:', s.tier)
print('Limits:', s.limits)
"
```

Expected output:
```
✅ Licensed: pro
Limits: AgentLimits(max_agents=10, max_events_per_month=100000)
```

---

## 3. TypeScript SDK — 5-Minute Quickstart

### Step 1 — Install

```bash
npm install @agentsentinel/sdk
```

Or with yarn:
```bash
yarn add @agentsentinel/sdk
```

### Step 2 — Set your license key

```bash
export AGENTSENTINEL_LICENSE_KEY="asv1_your_license_key_here"
```

Or in `.env`:
```dotenv
AGENTSENTINEL_LICENSE_KEY=asv1_your_license_key_here
```

### Step 3 — Protect your first tool

```typescript
import { AgentGuard, AgentPolicy, ApprovalRequiredError, BudgetExceededError } from "@agentsentinel/sdk";

const policy = new AgentPolicy({
  dailyBudget: 10.0,
  hourlyBudget: 2.0,
  requireApproval: ["send_email", "delete_*"],
  rateLimits: { search_web: "10/min" },
});

const guard = new AgentGuard({ policy });

// Protect a tool with cost tracking
const searchWeb = guard.protect(
  async (query: string) => `Results for: ${query}`,
  { toolName: "search_web", cost: 0.01 }
);

// Use the protected tool
try {
  const result = await searchWeb("AI safety best practices");
  console.log(result);
} catch (e) {
  if (e instanceof BudgetExceededError) {
    console.error("Daily budget exceeded");
  }
}
```

### Step 4 — Verify it works

```typescript
import { AgentSentinel } from "@agentsentinel/sdk";

const sentinel = new AgentSentinel({
  licenseKey: process.env.AGENTSENTINEL_LICENSE_KEY,
});

const status = await sentinel.validate();
console.log("✅ Licensed:", status.tier);
console.log("Limits:", status.limits);
```

---

## 4. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AGENTSENTINEL_LICENSE_KEY` | ✅ | Your license key from the portal |
| `AGENTSENTINEL_LICENSE_SIGNING_SECRET` | Only for offline HMAC verification | 64-char hex string. Must match the server-side secret. |
| `AGENTSENTINEL_LICENSE_API` | ❌ | Override the validation API URL. Default: production endpoint. |
| `AGENTSENTINEL_DEV_MODE` | ❌ Dev only | Set `true` to bypass license check. **Never set in production.** |

### How to set them

**macOS / Linux:**
```bash
export AGENTSENTINEL_LICENSE_KEY="asv1_your_key"
export AGENTSENTINEL_LICENSE_SIGNING_SECRET="your_64_char_hex_secret"
```

**Windows PowerShell:**
```powershell
$env:AGENTSENTINEL_LICENSE_KEY = "asv1_your_key"
$env:AGENTSENTINEL_LICENSE_SIGNING_SECRET = "your_64_char_hex_secret"
```

**`.env` file (recommended for development):**
```dotenv
AGENTSENTINEL_LICENSE_KEY=asv1_your_key
AGENTSENTINEL_LICENSE_SIGNING_SECRET=your_64_char_hex_secret
# Never commit this file to Git
```

---

## 5. License Key Formats

AgentSentinel uses two license key formats:

| Format | Example | Description | Supports offline? |
|--------|---------|-------------|-------------------|
| **HMAC-signed** | `asv1_<base64url-payload>_<base64url-sig>` | Current format. Payload includes tier, expiry, nonce. | ✅ Yes |
| **Legacy** | `as_pro_<random>`, `as_team_<random>`, `as_starter_<random>` | Older format. No embedded payload. | ❌ Requires online lookup |

### HMAC-signed key structure

```
asv1_<base64url(JSON_payload)>_<base64url(HMAC-SHA256)>
```

The JSON payload contains:
```json
{
  "exp": 1756684800,      // Unix timestamp — key expiry
  "iat": 1725148800,      // Unix timestamp — key issued at
  "nonce": "abc123",      // Random nonce to prevent guessing
  "tier": "pro"           // License tier
}
```

The HMAC signature is computed over `base64url(sorted_json_payload)` using `HMAC-SHA256` with `AGENTSENTINEL_LICENSE_SIGNING_SECRET`.

> For the full format specification and cross-language test vectors, see [`docs/license-key-format.md`](license-key-format.md).

---

## 6. Rate Limits

| Endpoint | Limit | Window | What to do if exceeded |
|----------|-------|--------|------------------------|
| `validate-license` | 20 requests/min | Per IP, sliding window | Use offline HMAC verification (see below) |
| `validate-promo` | 10 requests/min | Per IP, sliding window | Cache validation result for checkout session duration |

When rate limited, the API returns:
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Content-Type: application/json

{"error": "Rate limit exceeded", "retry_after": 60}
```

**The SDK handles this automatically** — it backs off and retries after `Retry-After` seconds. If your application makes more than 20 validation calls per minute, switch to offline HMAC verification.

---

## 7. Offline HMAC Verification

Offline verification lets you validate `asv1_` keys without any network call. This is ideal for:
- High-frequency validation (>20/min)
- Air-gapped environments
- Low-latency requirements

### Setup

You need `AGENTSENTINEL_LICENSE_SIGNING_SECRET` — the same 64-char hex secret used by the server to sign keys. Get it from your `.env` or Supabase secrets.

> **Security:** The signing secret gives the ability to forge license keys. Keep it server-side. Never expose it to browser JavaScript or mobile apps.

### Python offline verification

```python
from agentsentinel import AgentSentinel

# Offline mode — no network calls
sentinel = AgentSentinel(
    license_key="asv1_your_key",
    offline=True,
)

result = sentinel.validate()
print(f"Valid: {result.valid}, Tier: {result.tier}")
```

Or use the lower-level HMAC utility:

```python
from agentsentinel.utils.keygen import verify_license_key

is_valid = verify_license_key(
    key="asv1_your_key",
    signing_secret="your_64_char_hex_secret",
)
```

### TypeScript offline verification

```typescript
import { verifyLicenseKeyOffline } from "@agentsentinel/sdk";

const result = verifyLicenseKeyOffline(
  "asv1_your_key",
  process.env.AGENTSENTINEL_LICENSE_SIGNING_SECRET!
);

console.log("Valid:", result.valid, "Tier:", result.tier);
```

### How it works

The SDK:
1. Splits the key on `_` to extract `payload` and `sig`
2. Decodes both from base64url
3. Re-computes `HMAC-SHA256(base64url(sorted_payload_json), signing_secret)`
4. Compares the computed signature with `sig` (constant-time comparison)
5. Checks `exp` timestamp against current time

If the signature matches and `exp > now()`, the key is valid.

---

## 8. Error Codes and Retry Guidance

### `LicenseError` exceptions

| Error message | Cause | What to do |
|---------------|-------|------------|
| `Invalid license key` | Key not found in database | Check your key at [portal](https://agentsentinel.net/portal) |
| `License is expired` | `expires_at` is in the past | Renew at [portal](https://agentsentinel.net/portal) |
| `License is cancelled` | Subscription was cancelled | Resubscribe at [portal](https://agentsentinel.net/portal) |
| `License is revoked` | Admin manually revoked the key | Contact support |
| `License is past_due` | Payment failed | Update payment method at [portal](https://agentsentinel.net/portal) |
| `Unrecognised license key format` | Key doesn't start with `asv1_` or `as_<tier>_` | Use the full key from the portal — check for truncation or extra spaces |
| `Too many requests` | >20 validation calls/min | Switch to offline HMAC verification, or wait 60 seconds |
| `AGENTSENTINEL_LICENSE_KEY not set` | Environment variable missing | Set `AGENTSENTINEL_LICENSE_KEY` in your environment |

### HTTP status codes from the validation API

| Status | Meaning | Action |
|--------|---------|--------|
| `200 OK` | Request processed. Check `valid` in response body. | — |
| `400 Bad Request` | Malformed request (missing `license_key`, wrong format) | Check the request body format |
| `429 Too Many Requests` | Rate limit hit | Wait `Retry-After` seconds, or switch to offline |
| `500 Internal Server Error` | Server error | Retry with exponential backoff; alert if persistent |

### Retry guidance

The SDK uses **exponential backoff** for 429 and 500 responses:

| Attempt | Wait |
|---------|------|
| 1 | Immediately |
| 2 | 1 second |
| 3 | 2 seconds |
| 4 | 4 seconds |
| 5 | Stop, raise exception |

For production workloads, cache the validation result for 5 minutes. License status changes are infrequent — daily at most for most customers.

---

## 9. Framework Integrations

### LangChain

```python
from agentsentinel import AgentPolicy, AgentGuard
from langchain.agents import AgentExecutor

policy = AgentPolicy(daily_budget=5.0, audit_log=True)
guard = AgentGuard(policy=policy)

with guard.monitor("langchain-agent"):
    result = agent_executor.invoke({"input": "What's the weather?"})
```

### CrewAI

```python
from agentsentinel import AgentPolicy, AgentGuard
from crewai import Crew

policy = AgentPolicy(daily_budget=10.0, require_approval=["web_scrape"])
guard = AgentGuard(policy=policy)

with guard.monitor("crewai-research-crew"):
    result = crew.kickoff()
```

### OpenAI Assistants API

```python
from agentsentinel import AgentPolicy, AgentGuard
from openai import OpenAI

policy = AgentPolicy(daily_budget=5.0, audit_log=True)
guard = AgentGuard(policy=policy)
client = OpenAI()

with guard.monitor("openai-assistant"):
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id,
    )
```

### AutoGen

```python
from agentsentinel import AgentPolicy, AgentGuard
import autogen

policy = AgentPolicy(rate_limits={"generate_code": "5/min"})
guard = AgentGuard(policy=policy)

with guard.monitor("autogen-assistant"):
    result = assistant.initiate_chat(user_proxy, message="Write a hello world")
```

---

## 10. Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `LicenseError: Invalid license key` | Key doesn't exist | Verify at [portal](https://agentsentinel.net/portal) |
| `LicenseError: Unrecognised license key format` | Key has wrong prefix | Must start with `asv1_` or `as_pro_` etc. — trim whitespace |
| `LicenseError: License is expired` | Subscription expired | Renew at portal |
| `AGENTSENTINEL_LICENSE_KEY not set` | Missing env var | `export AGENTSENTINEL_LICENSE_KEY=...` |
| Offline verification fails | Signing secret mismatch | Ensure `AGENTSENTINEL_LICENSE_SIGNING_SECRET` matches Supabase |
| `429 Too Many Requests` | >20 validations/min | Cache results or use offline verification |
| SDK initialises but tier is wrong | Key from wrong environment | Check you're using the production key, not a test key |

**For deeper issues**, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

**For admin-side license management**, see [ADMIN_WORKFLOW.md](ADMIN_WORKFLOW.md).
