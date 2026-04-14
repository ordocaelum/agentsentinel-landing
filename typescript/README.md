# @agentsentinel/sdk

**Safety controls for AI agents** — budgets, approvals, rate limits, audit logs, and DLP.

[![npm version](https://badge.fury.io/js/@agentsentinel%2Fsdk.svg)](https://www.npmjs.com/package/@agentsentinel/sdk)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Installation

```bash
npm install @agentsentinel/sdk
```

## Quick Start

```typescript
import { AgentPolicy, AgentGuard } from '@agentsentinel/sdk';

const policy = new AgentPolicy({
  dailyBudget: 10.00,
  requireApproval: ['send_email', 'delete_*'],
  rateLimits: { web_search: '10/min' },
});

const guard = new AgentGuard(policy);

const searchWeb = guard.protect('web_search', async (query: string) => {
  return `Results for: ${query}`;
});
```

## Features

- 💰 **Budget Controls** — Daily/hourly spending limits with per-model caps
- ✋ **Approval Gates** — Require human approval for sensitive operations
- ⏱️ **Rate Limiting** — Prevent runaway loops with sliding window limits
- 📋 **Audit Logging** — Complete trail of every tool invocation
- 🔒 **DLP & PII Detection** — Block credit cards, SSNs, API keys from leaking
- 🌐 **Network Controls** — Allowlist/blocklist outbound domains

## Framework Integrations

```typescript
// LangChain
import { protectLangchainAgent } from '@agentsentinel/sdk/integrations/langchain';

// CrewAI
import { protectCrew } from '@agentsentinel/sdk/integrations/crewai';

// LlamaIndex
import { protectAgent } from '@agentsentinel/sdk/integrations/llamaindex';

// OpenAI Assistants
import { protectFunctionMap } from '@agentsentinel/sdk/integrations/openai-assistants';

// Anthropic Tools
import { protectToolHandlers } from '@agentsentinel/sdk/integrations/anthropic-tools';
```

## Documentation

Full docs at [docs.agentsentinel.dev](https://docs.agentsentinel.dev)

## License

MIT
