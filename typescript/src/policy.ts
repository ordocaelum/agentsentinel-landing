import { SecurityConfig } from "./security";

/** Configuration for agent safety controls. */
export interface AgentPolicyOptions {
  /** Maximum cumulative cost (USD) allowed per calendar day. Default: unlimited. */
  dailyBudget?: number;
  /** Maximum cumulative cost (USD) allowed per rolling hour. Default: unlimited. */
  hourlyBudget?: number;
  /**
   * Tool name patterns that require human approval before execution.
   * Supports exact names and glob-style wildcards: `["delete_*", "send_email"]`.
   */
  requireApproval?: string[];
  /**
   * Per-tool rate limit strings keyed by tool name pattern.
   * Values are strings like `"10/min"` or `"100/hour"`.
   * The key `"*"` acts as a global default.
   */
  rateLimits?: Record<string, string>;
  /** When `true` (default) every invocation is passed to the audit logger. */
  auditLog?: boolean;
  /**
   * Where to send real-time alerts.
   * Currently `"console"` is supported; future versions will add `"slack"` / webhooks.
   */
  alertChannel?: "console" | string;
  /**
   * Optional function `(toolName, args) => number` that returns an estimated cost.
   * Used when no explicit `cost` is supplied to `AgentGuard.protect()`.
   */
  costEstimator?: (toolName: string, args: unknown[]) => number;
  /**
   * Fine-grained security settings: blocked-tools kill-list, sensitive tools that
   * always require approval, secrets redaction patterns, and parameter log controls.
   */
  security?: SecurityConfig;
  /**
   * When `true`, applies extra restrictions for untrusted/experimental agents:
   * all {@link SecurityConfig.sensitiveTools} are implicitly added to the approval
   * list, and blocked-tool violations raise immediately.
   */
  sandboxMode?: boolean;
}

/** Immutable policy value object used by {@link AgentGuard}. */
export class AgentPolicy {
  readonly dailyBudget: number;
  readonly hourlyBudget: number;
  readonly requireApproval: readonly string[];
  readonly rateLimits: Readonly<Record<string, string>>;
  readonly auditLog: boolean;
  readonly alertChannel: string;
  readonly costEstimator: ((toolName: string, args: unknown[]) => number) | undefined;
  readonly security: SecurityConfig;
  readonly sandboxMode: boolean;

  constructor(options: AgentPolicyOptions = {}) {
    this.dailyBudget = options.dailyBudget ?? Infinity;
    this.hourlyBudget = options.hourlyBudget ?? Infinity;
    this.requireApproval = Object.freeze(options.requireApproval ?? []);
    this.rateLimits = Object.freeze(options.rateLimits ?? {});
    this.auditLog = options.auditLog ?? true;
    this.alertChannel = options.alertChannel ?? "console";
    this.costEstimator = options.costEstimator;
    this.security = options.security ?? new SecurityConfig();
    this.sandboxMode = options.sandboxMode ?? false;
  }
}
