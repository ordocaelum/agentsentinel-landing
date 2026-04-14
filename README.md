# 🛡️ AgentSentinel

[![PyPI version](https://badge.fury.io/py/agentsentinel.svg)](https://pypi.org/project/agentsentinel/)
[![npm version](https://badge.fury.io/js/@agentsentinel%2Fsdk.svg)](https://www.npmjs.com/package/@agentsentinel/sdk)
[![CI](https://github.com/ordocaelum/agentsentinel-landing/actions/workflows/ci.yml/badge.svg)](https://github.com/ordocaelum/agentsentinel-landing/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Safety controls, spend limits, and audit logging for AI agents.

## Installation

**Python:**
```bash
pip install agentsentinel
```

**TypeScript/JavaScript:**
```bash
npm install @agentsentinel/sdk
```

---

## What is AgentSentinel?

AgentSentinel is a lightweight SDK that wraps AI agent tools with:

- **Hard spend limits** — daily and hourly budget caps that raise `BudgetExceededError` before a runaway loop becomes a surprise invoice.
- **Human-in-the-loop approvals** — gate sensitive tools (email, database writes, deletions) behind an approval handler. Ships with `DenyAllApprover` and `InMemoryApprover`; plug in your own.
- **Rate limiting** — per-tool sliding-window caps (`"10/min"`, `"100/hour"`) to prevent runaway retry storms.
- **Audit logging** — every tool invocation produces a timestamped `AuditEvent` (tool name, decision, cost, status). Ships with `ConsoleAuditSink` and `InMemoryAuditSink`; extend with your own sink.
- **Security controls** — permanently block catastrophic tools, auto-redact API keys and passwords from logs, enforce sandbox mode for untrusted agents. Designed for OpenClaw and other agents with real tool access (shell, file system, APIs).
- **Framework-agnostic** — wraps any Python or TypeScript function. Works with LangChain, AutoGen, CrewAI, OpenClaw, plain OpenAI clients, or anything else.

---

## Repository Layout

```
/
├── index.html                   # Landing page (GitHub Pages)
├── docs.html                    # Documentation page (GitHub Pages)
├── security.html                # Security reference page (GitHub Pages)
├── README.md
│
├── python/
│   ├── agentsentinel/           # Python SDK source
│   │   ├── __init__.py
│   │   ├── policy.py            # AgentPolicy dataclass
│   │   ├── guard.py             # AgentGuard decorator/wrapper
│   │   ├── errors.py            # Exception classes (incl. ToolBlockedError)
│   │   ├── audit.py             # AuditEvent, AuditLogger, sinks
│   │   ├── approval.py          # ApprovalHandler, DenyAllApprover, InMemoryApprover
│   │   ├── rate_limit.py        # RateLimiter (sliding window)
│   │   └── security.py          # SecurityConfig, redact_sensitive, is_tool_blocked
│   ├── pyproject.toml
│   └── tests/
│       └── test_guard.py        # pytest test suite
│
├── typescript/
│   ├── src/                     # TypeScript SDK source
│   │   ├── index.ts             # Re-exports everything
│   │   ├── policy.ts            # AgentPolicy class
│   │   ├── guard.ts             # AgentGuard class
│   │   ├── errors.ts            # Error classes (incl. ToolBlockedError)
│   │   ├── audit.ts             # AuditEvent, AuditLogger, sinks
│   │   ├── approval.ts          # ApprovalHandler, DenyAllApprover, InMemoryApprover
│   │   ├── rateLimit.ts         # RateLimiter (sliding window)
│   │   └── security.ts          # SecurityConfig, redactSensitive, isToolBlocked
│   ├── package.json
│   └── tsconfig.json
│
└── examples/
    ├── python_quickstart.py       # Runnable Python demo
    ├── typescript_quickstart.ts   # Runnable TypeScript demo
    └── openclaw_integration.py    # OpenClaw security-focused demo
```

---

## Quick Start: Python

```bash
cd python
pip install -e .
```

```python
from agentsentinel import AgentPolicy, AgentGuard, BudgetExceededError, ApprovalRequiredError

policy = AgentPolicy(
    daily_budget=10.0,
    hourly_budget=2.0,
    require_approval=["send_email", "delete_*"],
    rate_limits={"search_web": "10/min"},
    audit_log=True,
)

guard = AgentGuard(policy=policy)

@guard.protect(tool_name="search_web", cost=0.01)
def search_web(query: str) -> str:
    return f"Results for: {query}"

@guard.protect(tool_name="send_email")
def send_email(to: str, subject: str, body: str):
    print(f"Sending email to {to}: {subject}")

# Works — search is within budget and rate limit
result = search_web("AI safety best practices")

# Raises ApprovalRequiredError (DenyAllApprover by default)
try:
    send_email("user@example.com", "Hello", "Test")
except ApprovalRequiredError as e:
    print(f"Blocked: {e}")
```

Run the full demo:

```bash
cd python && pip install -e .
python ../examples/python_quickstart.py
```

### Run Tests

```bash
cd python
pip install -e ".[dev]"
pytest -v
```

---

## Quick Start: TypeScript

```bash
cd typescript
npm install
npm run build
```

```typescript
import { AgentGuard, AgentPolicy, ApprovalRequiredError } from "@agentsentinel/sdk";

const policy = new AgentPolicy({
  dailyBudget: 10.0,
  hourlyBudget: 2.0,
  requireApproval: ["send_email", "delete_*"],
  rateLimits: { search_web: "10/min" },
});

const guard = new AgentGuard({ policy });

const searchWeb = guard.protect(
  async (query: string) => `Results for: ${query}`,
  { toolName: "search_web", cost: 0.01 }
);

const result = await searchWeb("AI safety best practices");
```

---

## What's Implemented vs Planned

### ✅ Implemented (v0.1.0-preview)

| Feature | Python | TypeScript |
|---|---|---|
| `AgentPolicy` configuration | ✅ | ✅ |
| `AgentGuard.protect()` decorator | ✅ | ✅ |
| Daily / hourly budget enforcement | ✅ | ✅ |
| `BudgetExceededError` | ✅ | ✅ |
| `ApprovalRequiredError` | ✅ | ✅ |
| `RateLimitExceededError` | ✅ | ✅ |
| `DenyAllApprover` | ✅ | ✅ |
| `InMemoryApprover` | ✅ | ✅ |
| `ConsoleAuditSink` | ✅ | ✅ |
| `InMemoryAuditSink` | ✅ | ✅ |
| Sliding-window rate limiter | ✅ | ✅ |
| Wildcard pattern matching | ✅ | ✅ |
| Audit event model | ✅ | ✅ |

### 🔜 Planned (v0.2+)

- Slack / webhook approval and alert adapters
- LangChain, AutoGen, and CrewAI first-class adapters
- Persistent audit sinks (file, database)
- Dashboard / UI for audit review
- Token-count-based cost estimation (OpenAI, Anthropic)
- Daily budget counter reset at midnight UTC

---

## About the Landing Site

`index.html` and `docs.html` are static GitHub Pages files. They serve as the public face of the project and contain real SDK API examples matching the code in this repo.

No build step is required for the site — it uses Tailwind CSS via CDN and vanilla JavaScript.

---

## Contributing

This project is in early development. Issues and pull requests are welcome.

1. Fork the repo and create a feature branch.
2. Make your changes, add tests for Python changes.
3. Run `pytest -v` in the `python/` directory before submitting.
4. Open a pull request with a clear description.

---

## License

[MIT](https://opensource.org/licenses/MIT)
