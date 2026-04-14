/**
 * AgentSentinel — Safety controls for AI agents
 * Copyright (c) 2026 Leland E. Doss. All rights reserved.
 * Licensed under the Business Source License 1.1
 * See LICENSE.md for details
 */
/** Custom error base class for all AgentSentinel errors. */
export class AgentSentinelError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AgentSentinelError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** Thrown when an agent exceeds its configured spend budget. */
export class BudgetExceededError extends AgentSentinelError {
  readonly budget: number;
  readonly spent: number;

  constructor(
    message = "Budget limit exceeded",
    { budget = 0, spent = 0 }: { budget?: number; spent?: number } = {}
  ) {
    super(message);
    this.name = "BudgetExceededError";
    this.budget = budget;
    this.spent = spent;
  }
}

/** Thrown when a tool invocation requires human approval before proceeding. */
export class ApprovalRequiredError extends AgentSentinelError {
  readonly toolName: string;

  constructor(
    message = "Human approval required",
    { toolName = "" }: { toolName?: string } = {}
  ) {
    super(message);
    this.name = "ApprovalRequiredError";
    this.toolName = toolName;
  }
}

/** Thrown when a tool has been called more times than its rate limit allows. */
export class RateLimitExceededError extends AgentSentinelError {
  readonly toolName: string;
  readonly limit: string;

  constructor(
    message = "Rate limit exceeded",
    { toolName = "", limit = "" }: { toolName?: string; limit?: string } = {}
  ) {
    super(message);
    this.name = "RateLimitExceededError";
    this.toolName = toolName;
    this.limit = limit;
  }
}

/**
 * Thrown when a tool is permanently blocked by the security policy.
 *
 * Unlike {@link ApprovalRequiredError} there is no approval pathway —
 * the tool is hard-blocked and will never execute.
 */
export class ToolBlockedError extends AgentSentinelError {
  readonly toolName: string;

  constructor(
    message = "Tool is blocked by security policy",
    { toolName = "" }: { toolName?: string } = {}
  ) {
    super(message);
    this.name = "ToolBlockedError";
    this.toolName = toolName;
  }
}

/** Thrown when PII is detected in outbound data and blocking is enabled. */
export class PIIDetectedError extends AgentSentinelError {
  readonly piiTypes: readonly string[];
  readonly toolName: string;

  constructor(
    message = "PII detected in data",
    { piiTypes = [], toolName = "" }: { piiTypes?: string[]; toolName?: string } = {}
  ) {
    super(message);
    this.name = "PIIDetectedError";
    this.piiTypes = Object.freeze(piiTypes);
    this.toolName = toolName;
  }
}

/** Thrown when an outbound request violates the network policy. */
export class NetworkPolicyViolationError extends AgentSentinelError {
  readonly url: string;
  readonly reason: string;

  constructor(
    message = "Network policy violation",
    { url = "", reason = "" }: { url?: string; reason?: string } = {}
  ) {
    super(message);
    this.name = "NetworkPolicyViolationError";
    this.url = url;
    this.reason = reason;
  }
}

/** Thrown when content inspection fails or detects a policy violation. */
export class ContentInspectionError extends AgentSentinelError {
  readonly toolName: string;
  readonly reason: string;

  constructor(
    message = "Content inspection failed",
    { toolName = "", reason = "" }: { toolName?: string; reason?: string } = {}
  ) {
    super(message);
    this.name = "ContentInspectionError";
    this.toolName = toolName;
    this.reason = reason;
  }
}

/** Thrown when a model's per-model budget limit is exceeded. */
export class ModelBudgetExceededError extends AgentSentinelError {
  readonly model: string;
  readonly spent: number;
  readonly budget: number;

  constructor(model: string, spent: number, budget: number) {
    super(`Model '${model}' budget exceeded: $${spent.toFixed(4)} >= $${budget.toFixed(2)}`);
    this.name = "ModelBudgetExceededError";
    this.model = model;
    this.spent = spent;
    this.budget = budget;
  }
}
