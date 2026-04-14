/**
 * AgentSentinel TypeScript SDK — developer preview
 *
 * @module @agentsentinel/sdk
 */

export { AgentPolicy } from "./policy";
export type { AgentPolicyOptions } from "./policy";

export { AgentGuard } from "./guard";
export type { ProtectOptions } from "./guard";

export {
  AgentSentinelError,
  BudgetExceededError,
  ApprovalRequiredError,
  RateLimitExceededError,
} from "./errors";

export {
  AuditEvent,
  AuditLogger,
  ConsoleAuditSink,
  InMemoryAuditSink,
} from "./audit";
export type { AuditSink, Decision } from "./audit";

export { DenyAllApprover, InMemoryApprover } from "./approval";
export type { ApprovalHandler } from "./approval";

export { RateLimiter } from "./rateLimit";

export const VERSION = "0.1.0-preview";
