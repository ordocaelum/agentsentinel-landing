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
  ToolBlockedError,
  PIIDetectedError,
  NetworkPolicyViolationError,
  ContentInspectionError,
  ModelBudgetExceededError,
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

export { SecurityConfig, redactSensitive, isToolBlocked } from "./security";
export type { SecurityConfigOptions } from "./security";

export { PIIConfig, PIIScanner, PIIType, luhnCheck } from "./pii";
export type { PIIConfigOptions, PIIMatch } from "./pii";

export { NetworkPolicy, NetworkGuard } from "./network";
export type { NetworkPolicyOptions } from "./network";

export {
  ContentInspector,
  InspectorConfig,
  InspectionResult,
} from "./inspector";
export type {
  InspectorConfigOptions,
  InspectionReport,
  InspectorFn,
} from "./inspector";

export {
  MODEL_PRICING,
  ModelProvider,
  getModelPricing,
  calculateCost,
  listModelsByProvider,
  listAllProviders,
} from "./pricing";
export type { ModelPricing } from "./pricing";

export {
  CostTracker,
  CostTrackerConfig,
  estimateTokensFromResponse,
} from "./costTracker";
export type { ModelUsage, CostTrackerConfigOptions } from "./costTracker";

export const VERSION = "0.1.0-preview";
