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
