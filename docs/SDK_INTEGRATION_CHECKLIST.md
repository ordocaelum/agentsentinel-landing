# AgentSentinel — SDK Integration Checklist

Get from zero to a licensed, monitored AI agent in under 5 minutes.

---

## Prerequisites

- Python 3.9+ or Node.js 18+
- An AgentSentinel license key (`asv1_…` or `as_pro_…`)  
  → Get one at [agentsentinel.net/portal](https://agentsentinel.net/portal)

---

## ⚡ Python Quick Start (3 minutes)

### Step 1 — Install

```bash
pip install agentsentinel
```

### Step 2 — Set your license key

```bash
export AGENTSENTINEL_LICENSE_KEY="asv1_your_license_key_here"
```

Or add it to your `.env` file:

```dotenv
AGENTSENTINEL_LICENSE_KEY=asv1_your_license_key_here
```

### Step 3 — Initialise and use

```python
from agentsentinel import AgentSentinel

# Initialise — validates the license and starts monitoring
sentinel = AgentSentinel()   # reads AGENTSENTINEL_LICENSE_KEY from env

# Or pass the key explicitly:
# sentinel = AgentSentinel(license_key="asv1_…")

print(f"Tier: {sentinel.tier}")          # e.g. "pro"
print(f"Max agents: {sentinel.limits.max_agents}")

# Monitor an agent call
with sentinel.monitor("my-agent"):
    result = my_agent.run("What is the weather today?")
```

### Step 4 — Verify it works

```bash
python -c "from agentsentinel import AgentSentinel; s = AgentSentinel(); print('✅ Licensed:', s.tier)"
```

---

## ⚡ TypeScript / Node.js Quick Start (3 minutes)

### Step 1 — Install

```bash
npm install @agentsentinel/sdk
```

### Step 2 — Set your license key

```bash
export AGENTSENTINEL_LICENSE_KEY="asv1_your_license_key_here"
```

### Step 3 — Initialise and use

```typescript
import { AgentSentinel } from '@agentsentinel/sdk';

const sentinel = new AgentSentinel({
  licenseKey: process.env.AGENTSENTINEL_LICENSE_KEY,
});

const status = await sentinel.validate();
console.log(`Tier: ${status.tier}`);

// Wrap an agent call
const result = await sentinel.monitor('my-agent', async () => {
  return await myAgent.run('What is the weather?');
});
```

---

## Validation Behaviour

| Scenario | Behaviour |
|---|---|
| Valid license, online | Calls `validate-license` Edge Function, caches result |
| Valid license, offline | Falls back to HMAC offline verification (no network required) |
| Invalid/expired license | Throws `LicenseError` with reason |
| Rate limited (>20/min) | Returns `Retry-After: 60` — SDK retries after back-off |
| `AGENTSENTINEL_DEV_MODE=true` | Bypasses license check (dev only — **never set in production**) |

---

## Tier Limits

| Tier | Max Agents | Max Events/Month | Features |
|---|---|---|---|
| `free` | 1 | 1,000 | Basic monitoring |
| `starter` | 3 | 10,000 | Basic monitoring + alerts |
| `pro` | 10 | 100,000 | Full monitoring + policy editor |
| `pro_team` | 25 | 500,000 | Multi-agent + team features |
| `team` | 50 | 2,000,000 | All Pro Team features + priority support |
| `enterprise` | Unlimited | Unlimited | Custom limits + SLA |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `AGENTSENTINEL_LICENSE_KEY` | ✅ | Your license key |
| `AGENTSENTINEL_LICENSE_SIGNING_SECRET` | Only for offline verification | HMAC secret (must match server-side) |
| `AGENTSENTINEL_LICENSE_API` | ❌ | Override API URL (default: production endpoint) |
| `AGENTSENTINEL_DEV_MODE` | ❌ | Set `true` to bypass license check in development |

---

## Framework Integrations

### LangChain

```python
from agentsentinel import AgentSentinel
from langchain.agents import AgentExecutor

sentinel = AgentSentinel()

# Wrap LangChain agent execution
with sentinel.monitor("langchain-agent"):
    result = agent_executor.invoke({"input": "..."})
```

### CrewAI

```python
from agentsentinel import AgentSentinel
from crewai import Crew

sentinel = AgentSentinel()

with sentinel.monitor("crewai-crew"):
    result = crew.kickoff()
```

### OpenAI Assistants

```python
from agentsentinel import AgentSentinel
from openai import OpenAI

sentinel = AgentSentinel()
client = OpenAI()

with sentinel.monitor("openai-assistant"):
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id,
    )
```

See `examples/` for complete integration demos.

---

## License Key Format

License keys follow one of two formats:

| Format | Example | Description |
|---|---|---|
| HMAC-signed | `asv1_<base64url-payload>.<base64url-sig>` | New format — verifiable offline |
| Legacy | `as_<tier>_<random>` | Old format — requires online validation |

For detailed format specification, see [`docs/license-key-format.md`](license-key-format.md).

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `LicenseError: Invalid license key` | Key doesn't exist in database | Verify the key at [portal](https://agentsentinel.net/portal) |
| `LicenseError: License is expired` | `expires_at` in the past | Renew subscription at [portal](https://agentsentinel.net/portal) |
| `LicenseError: License is cancelled` | Subscription was cancelled | Resubscribe at [portal](https://agentsentinel.net/portal) |
| `LicenseError: Too many requests` | >20 calls/min to validate-license | Use offline HMAC verification for high-frequency calls |
| `AGENTSENTINEL_LICENSE_KEY not set` | Environment variable missing | Set `AGENTSENTINEL_LICENSE_KEY` in your `.env` |
| `Unrecognised license key format` | Key doesn't start with `asv1_` or `as_<tier>_` | Use the key from your portal |

For more troubleshooting, see [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

---

## Security Best Practices

- ✅ Store your license key in an **environment variable**, not in source code.
- ✅ Add `AGENTSENTINEL_LICENSE_KEY` to `.gitignore` (your `.env` file should never be committed).
- ✅ Use **offline HMAC verification** for high-throughput workloads to avoid rate limits.
- ✅ Set `AGENTSENTINEL_DEV_MODE=false` (or leave unset) in production.
- ❌ Never share your license key in GitHub issues, Slack, or public forums.

---

## Support

- 📖 **Documentation:** [agentsentinel.net/docs](https://agentsentinel.net/docs)
- 🐛 **Issues:** [GitHub Issues](https://github.com/ordocaelum/agentsentinel-landing/issues)
- 🔑 **Portal:** [agentsentinel.net/portal](https://agentsentinel.net/portal)
