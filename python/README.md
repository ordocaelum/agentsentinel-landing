# AgentSentinel

**Safety controls for AI agents** — budgets, approvals, rate limits, audit logs, and DLP.

[![PyPI version](https://badge.fury.io/py/agentsentinel.svg)](https://pypi.org/project/agentsentinel/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Installation

```bash
pip install agentsentinel
```

## Quick Start

```python
from agentsentinel import AgentPolicy, AgentGuard

policy = AgentPolicy(
    daily_budget=10.00,
    require_approval=["send_email", "delete_*"],
    rate_limits={"web_search": "10/min"},
)

guard = AgentGuard(policy)

@guard.protect("web_search")
def search_web(query: str) -> str:
    return f"Results for: {query}"
```

## Features

- 💰 **Budget Controls** — Daily/hourly spending limits with per-model caps
- ✋ **Approval Gates** — Require human approval for sensitive operations
- ⏱️ **Rate Limiting** — Prevent runaway loops with sliding window limits
- 📋 **Audit Logging** — Complete trail of every tool invocation
- 🔒 **DLP & PII Detection** — Block credit cards, SSNs, API keys from leaking
- 🌐 **Network Controls** — Allowlist/blocklist outbound domains

## Framework Integrations

```python
# LangChain
from agentsentinel.integrations.langchain import protect_langchain_agent
executor = protect_langchain_agent(executor, policy=policy)

# CrewAI
from agentsentinel.integrations.crewai import protect_crew
crew = protect_crew(crew, policy=policy)

# LlamaIndex
from agentsentinel.integrations.llamaindex import protect_agent
agent = protect_agent(agent, policy=policy)

# OpenAI Assistants
from agentsentinel.integrations.openai_assistants import protect_function_map
functions = protect_function_map(functions, guard=guard)

# Anthropic Tools
from agentsentinel.integrations.anthropic_tools import protect_tool_handlers
handlers = protect_tool_handlers(handlers, guard=guard)
```

## 101 Models Supported

Cost tracking for OpenAI, Anthropic, Google, Mistral, Cohere, Meta, AWS Bedrock, Azure OpenAI, Groq, Together, Perplexity, DeepSeek, xAI, and local models.

## Documentation

Full docs at [docs.agentsentinel.net](https://docs.agentsentinel.net)

## License

MIT
