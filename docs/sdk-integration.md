# SDK Integration Guide

> **Time to first validation: ~5 minutes**

This guide shows how to integrate the AgentSentinel Python SDK with your application so that your AI agents are governed by your license tier.

---

## Prerequisites

- Python 3.9+
- An AgentSentinel license key (obtained from the [customer portal](https://agentsentinel.net/portal.html))
- (Optional) `AGENTSENTINEL_LICENSE_SIGNING_SECRET` for offline verification

---

## 1. Installation

```bash
pip install agentsentinel
```

---

## 2. Environment Variables

Set these in your environment (e.g. `.env`, Docker, or your CI secrets):

| Variable | Required | Description |
|---|---|---|
| `AGENTSENTINEL_LICENSE_KEY` | Yes | Your license key (`asv1_…` or `as_<tier>_…`) |
| `AGENTSENTINEL_LICENSE_SIGNING_SECRET` | Recommended | HMAC secret for offline key verification.  Obtain from your AgentSentinel admin. |
| `AGENTSENTINEL_LICENSE_API` | No | Override the license validation endpoint (default: production Supabase URL) |
| `AGENTSENTINEL_DEV_MODE` | No | Set to `true` to skip real validation in local development |

```bash
# .env
AGENTSENTINEL_LICENSE_KEY=asv1_eyJleH...
AGENTSENTINEL_LICENSE_SIGNING_SECRET=your-32-byte-secret-here
```

---

## 3. Basic Usage

### Auto-initialization from environment

The SDK reads `AGENTSENTINEL_LICENSE_KEY` automatically on first use:

```python
import agentsentinel as ags

# The license is loaded from AGENTSENTINEL_LICENSE_KEY.
# Call set_license_key() explicitly if you manage the key in code:
# ags.set_license_key("asv1_eyJleH...")

info = ags.get_license_info()
print(f"Tier: {info.tier.value}")          # e.g. "pro"
print(f"Valid: {info.is_valid}")           # True
print(f"Max agents: {info.limits.max_agents}")
```

### Protecting features by tier

```python
# Raise FeatureNotAvailableError if the feature isn't in the current tier:
ags.require_feature("integrations")

# Boolean check (no exception):
if ags.is_feature_available("multi_agent"):
    orchestrator.run_parallel()
```

Available feature strings: `"dashboard"`, `"integrations"`, `"multi_agent"`, `"policy_editor_basic"`, `"policy_editor_full"`.

### Registering agents

```python
from agentsentinel import AgentGuard

with AgentGuard(agent_id="my-agent") as guard:
    # AgentGuard registers the agent and enforces the per-tier agent limit.
    result = my_llm_agent.run(task)
```

If your tier's `max_agents` limit would be exceeded, `AgentGuard.__enter__` raises `UsageLimitExceededError`.

---

## 4. Offline Verification

The SDK automatically falls back to offline HMAC verification when the license API is unreachable:

1. Set `AGENTSENTINEL_LICENSE_SIGNING_SECRET` to the same secret used to sign your keys.
2. If the API call to `validate-license` fails (network timeout, etc.), the SDK verifies the key's HMAC signature locally — **no network required**.
3. The offline result does not check revocation; only the signature and expiry are validated.

```python
# Force offline verification (useful for air-gapped environments):
import os
os.environ["AGENTSENTINEL_LICENSE_API"] = "http://localhost:1"  # unreachable

from agentsentinel.licensing import LicenseManager
mgr = LicenseManager()
mgr.set_license_key("asv1_eyJleH...")
info = mgr.get_license_info()
print(info.validation_error)  # "Offline validation (signed key)"
print(info.is_valid)          # True if signature and expiry are valid
```

---

## 5. Tier Limits Reference

| Tier | Max agents | Max events/month | Integrations | Multi-agent |
|---|---|---|---|---|
| `free` | 1 | 1,000 | ✗ | ✗ |
| `starter` | 1 | 1,000 | ✗ | ✗ |
| `pro` | 5 | 50,000 | ✓ | ✗ |
| `pro_team` | 5 | 50,000 | ✓ | ✓ |
| `team` | 20 | 500,000 | ✓ | ✓ |
| `enterprise` | Unlimited | Unlimited | ✓ | ✓ |

---

## 6. Validate-License API Reference

The SDK calls this endpoint internally.  You can also call it directly from server-side code.

**Endpoint:** `POST /functions/v1/validate-license`  
**Rate limit:** 20 requests / minute per IP (HTTP 429 with `Retry-After: 60`)

**Request:**

```json
{ "license_key": "asv1_eyJleH..." }
```

**Success response (HTTP 200):**

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

**Error responses:**

| HTTP | Payload | Meaning |
|---|---|---|
| 400 | `{"valid":false,"reason":"malformed","error":"..."}` | Key doesn't match any known prefix |
| 404 | `{"valid":false,"error":"Invalid license key"}` | Key not found in database |
| 403 | `{"valid":false,"reason":"expired","error":"..."}` | Key exists but has expired |
| 429 | `{"valid":false,"error":"Too many requests..."}` | Rate limited |

---

## 7. Error Handling

```python
from agentsentinel.licensing import (
    LicenseError,
    FeatureNotAvailableError,
    UsageLimitExceededError,
)

try:
    ags.require_feature("multi_agent")
except FeatureNotAvailableError as e:
    print(f"Upgrade required: {e}")

try:
    ags.record_event()
except UsageLimitExceededError as e:
    print(f"Monthly limit reached: {e}")
```

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `validation_error: "Signing secret unavailable"` | `AGENTSENTINEL_LICENSE_SIGNING_SECRET` not set | Set the env var or call `verify_license_key(key, secret="...")` |
| `validation_error: "Invalid signature"` | Wrong signing secret | Ensure the secret matches the one used when the key was generated |
| `is_valid=False, validation_error: "License expired"` | Key has passed its `exp` timestamp | Re-issue the license or renew your subscription |
| HTTP 429 from validate-license | Too many SDK instances calling validate at once | Cache the license info; the SDK caches for 1 hour by default |
| HTTP 400 `reason: malformed` | Key has an unrecognised prefix | Check the key starts with `asv1_` or `as_<valid_tier>_` |

---

## 9. Key Format Specification

See [`docs/license-key-format.md`](license-key-format.md) for the full canonical specification of the `asv1_*` HMAC-signed key format, including the payload schema, signing algorithm, and key rotation procedure.
