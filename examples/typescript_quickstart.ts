/**
 * AgentSentinel TypeScript Quickstart Example
 *
 * Demonstrates:
 *   - Defining an AgentPolicy with budget limits, approval patterns, and rate limits.
 *   - Wrapping async tools with guard.protect().
 *   - BudgetExceededError when the daily limit is hit.
 *   - ApprovalRequiredError for tools that require human sign-off.
 *   - RateLimitExceededError when a tool fires too often.
 *   - InMemoryApprover for testing/demo purposes.
 *
 * Run:
 *     cd typescript
 *     npm install
 *     npm run build
 *     node dist/../../examples/typescript_quickstart.js
 *
 *   Or compile + run directly with ts-node:
 *     npx ts-node ../examples/typescript_quickstart.ts
 */

import {
  AgentGuard,
  AgentPolicy,
  ApprovalRequiredError,
  BudgetExceededError,
  InMemoryApprover,
  InMemoryAuditSink,
  AuditLogger,
  RateLimitExceededError,
} from "./src/index";

// ─── 1. Define your safety policy ──────────────────────────────────────────

const policy = new AgentPolicy({
  dailyBudget: 10.0,           // hard stop at $10/day
  hourlyBudget: 2.0,           // never more than $2/hour
  requireApproval: [
    "send_email",              // outbound communications
    "delete_*",                // any destructive action
    "execute_sql",             // database writes
  ],
  rateLimits: {
    search_web: "5/min",       // max 5 searches per minute
    "*": "50/hour",            // global default
  },
  auditLog: true,
  alertChannel: "console",
});

// ─── 2. Create a guard, using in-memory sinks for demo output ──────────────

const sink = new InMemoryAuditSink();
const logger = new AuditLogger([sink]);
const guard = new AgentGuard({ policy, auditLogger: logger });

// ─── 3. Wrap your tools ────────────────────────────────────────────────────

const searchWeb = guard.protect(
  async (query: string): Promise<string> => {
    return `[search results for: ${query}]`;
  },
  { toolName: "search_web", cost: 0.01 }
);

const sendEmail = guard.protect(
  async (to: string, subject: string, body: string): Promise<void> => {
    console.log(`  📧  Email sent to '${to}': ${subject}`);
  },
  { toolName: "send_email" }
);

// ─── Main async demo ───────────────────────────────────────────────────────

async function main(): Promise<void> {
  // --- Demo 1: Allowed calls ---
  console.log("=".repeat(60));
  console.log("Demo 1: Allowed tool calls");
  console.log("=".repeat(60));

  const r1 = await searchWeb("AI safety best practices");
  console.log(`searchWeb result → ${r1}\n`);

  const r2 = await searchWeb("how to limit LLM costs");
  console.log(`searchWeb result → ${r2}\n`);

  // --- Demo 2: Approval gate (DenyAllApprover by default) ---
  console.log("=".repeat(60));
  console.log("Demo 2: Approval gate (DenyAllApprover by default)");
  console.log("=".repeat(60));

  try {
    await sendEmail("user@example.com", "Hello from agent", "Test message");
  } catch (e) {
    if (e instanceof ApprovalRequiredError) {
      console.log(`✋ Blocked — ${e.message}\n`);
    } else throw e;
  }

  // --- Demo 3: Approval gate (InMemoryApprover — pre-approved) ---
  console.log("=".repeat(60));
  console.log("Demo 3: Approval gate (InMemoryApprover — pre-approved)");
  console.log("=".repeat(60));

  const approver = new InMemoryApprover(new Set(["send_email"]));
  const guard2 = new AgentGuard({ policy, approvalHandler: approver, auditLogger: logger });

  const sendEmailApproved = guard2.protect(
    async (to: string, subject: string, body: string): Promise<void> => {
      console.log(`  📧  Email sent to '${to}': ${subject}`);
    },
    { toolName: "send_email" }
  );

  await sendEmailApproved("user@example.com", "Hello from agent", "Test message");
  console.log();

  // --- Demo 4: Rate limit exceeded ---
  console.log("=".repeat(60));
  console.log("Demo 4: Rate limit exceeded");
  console.log("=".repeat(60));

  for (let i = 0; i < 5; i++) {
    await searchWeb(`query ${i}`);
    console.log(`  ✓ searchWeb call ${i + 1} succeeded`);
  }

  try {
    await searchWeb("one too many");
  } catch (e) {
    if (e instanceof RateLimitExceededError) {
      console.log(`⏱️  Blocked — ${e.message}\n`);
    } else throw e;
  }

  // --- Demo 5: Budget exceeded ---
  console.log("=".repeat(60));
  console.log("Demo 5: Budget exceeded");
  console.log("=".repeat(60));

  const tightPolicy = new AgentPolicy({ dailyBudget: 0.02 });
  const tightGuard = new AgentGuard({ policy: tightPolicy, auditLogger: logger });

  const expensiveTool = tightGuard.protect(
    async (): Promise<string> => "expensive result",
    { toolName: "expensive_tool", cost: 0.015 }
  );

  await expensiveTool(); // $0.015 — under budget
  console.log(`  ✓ First call succeeded (spent: $${tightGuard.dailySpent.toFixed(3)})`);

  try {
    await expensiveTool(); // Would bring total to $0.03 > $0.02
  } catch (e) {
    if (e instanceof BudgetExceededError) {
      console.log(`💸  Blocked — ${e.message}\n`);
    } else throw e;
  }

  // --- Audit log summary ---
  console.log("=".repeat(60));
  console.log(`Audit log: ${sink.events.length} events recorded`);
  console.log("=".repeat(60));
  for (const ev of sink.events) {
    const ts = new Date(ev.timestamp).toISOString().substr(11, 8);
    console.log(
      `  ${ts} | ${ev.toolName.padEnd(20)} | ${ev.decision.padEnd(22)} | $${ev.cost.toFixed(4)}`
    );
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
