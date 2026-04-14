import { AuditEvent, AuditLogger, ConsoleAuditSink } from "./audit";
import { ApprovalRequiredError, BudgetExceededError } from "./errors";
import { AgentPolicy } from "./policy";
import { RateLimiter } from "./rateLimit";
import { ApprovalHandler, DenyAllApprover } from "./approval";

export interface ProtectOptions {
  /** Override the tool name used for policy matching and audit logs. */
  toolName?: string;
  /** Explicit cost per invocation (USD). Defaults to `0`. */
  cost?: number;
}

/** A generic async (or sync) callable. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyFn = (...args: any[]) => any;

/**
 * Wraps agent tools with spend controls, approval gates, rate limiting,
 * and audit logging — all driven by an {@link AgentPolicy}.
 *
 * @example
 * ```ts
 * const policy = new AgentPolicy({ dailyBudget: 10.0, requireApproval: ["send_email"] });
 * const guard  = new AgentGuard({ policy });
 *
 * const searchWeb = guard.protect(
 *   async (query: string) => `Results for ${query}`,
 *   { toolName: "search_web", cost: 0.01 }
 * );
 * ```
 */
export class AgentGuard {
  private readonly policy: AgentPolicy;
  private readonly approvalHandler: ApprovalHandler;
  private readonly auditLogger: AuditLogger;
  private readonly rateLimiter: RateLimiter;

  private _dailySpent = 0;
  private _hourlySpent = 0;
  private _hourlyResetAt = Date.now();

  constructor({
    policy,
    approvalHandler,
    auditLogger,
  }: {
    policy: AgentPolicy;
    approvalHandler?: ApprovalHandler;
    auditLogger?: AuditLogger;
  }) {
    this.policy = policy;
    this.approvalHandler = approvalHandler ?? new DenyAllApprover();

    if (auditLogger) {
      this.auditLogger = auditLogger;
    } else {
      const sink = new ConsoleAuditSink();
      this.auditLogger = new AuditLogger(policy.auditLog ? [sink] : []);
    }

    this.rateLimiter = new RateLimiter(policy.rateLimits);
  }

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------

  private resetHourlyIfNeeded(): void {
    if (Date.now() - this._hourlyResetAt >= 3_600_000) {
      this._hourlySpent = 0;
      this._hourlyResetAt = Date.now();
    }
  }

  private requiresApproval(toolName: string): boolean {
    for (const pattern of this.policy.requireApproval) {
      if (this.matchesPattern(toolName, pattern)) return true;
    }
    return false;
  }

  /** Simple glob-style pattern matching (supports `*` and `?`). */
  private matchesPattern(name: string, pattern: string): boolean {
    if (pattern === name) return true;
    const re = new RegExp(
      "^" + pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".") + "$"
    );
    return re.test(name);
  }

  // -----------------------------------------------------------------------
  // Public API
  // -----------------------------------------------------------------------

  /**
   * Wrap *fn* with all policy checks.
   *
   * @param fn        The function to protect.
   * @param options   Optional tool name override and cost per call.
   * @returns A wrapped function with the same signature as *fn*.
   */
  protect<T extends AnyFn>(fn: T, options: ProtectOptions = {}): T {
    const resolvedName = options.toolName ?? fn.name ?? "anonymous";
    const cost = options.cost ?? 0;
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    const self = this;

    const wrapped = async function (...args: Parameters<T>): Promise<Awaited<ReturnType<T>>> {
      const invocationCost =
        cost !== 0 ? cost : (self.policy.costEstimator?.(resolvedName, args) ?? 0);

      self.resetHourlyIfNeeded();

      // --- Hourly budget check ---
      if (self._hourlySpent + invocationCost > self.policy.hourlyBudget) {
        self.auditLogger.record(
          AuditEvent.now(resolvedName, "blocked", invocationCost, "blocked_budget", {
            reason: "hourly_budget_exceeded",
          })
        );
        throw new BudgetExceededError(
          `Hourly budget exceeded for '${resolvedName}'. Budget: $${self.policy.hourlyBudget.toFixed(2)}, spent: $${self._hourlySpent.toFixed(2)}.`,
          { budget: self.policy.hourlyBudget, spent: self._hourlySpent }
        );
      }

      // --- Daily budget check ---
      if (self._dailySpent + invocationCost > self.policy.dailyBudget) {
        self.auditLogger.record(
          AuditEvent.now(resolvedName, "blocked", invocationCost, "blocked_budget", {
            reason: "daily_budget_exceeded",
          })
        );
        throw new BudgetExceededError(
          `Daily budget exceeded for '${resolvedName}'. Budget: $${self.policy.dailyBudget.toFixed(2)}, spent: $${self._dailySpent.toFixed(2)}.`,
          { budget: self.policy.dailyBudget, spent: self._dailySpent }
        );
      }

      // --- Rate limit check ---
      self.rateLimiter.check(resolvedName);

      // --- Approval check ---
      if (self.requiresApproval(resolvedName)) {
        const approved = await self.approvalHandler.requestApproval(resolvedName, args);
        if (!approved) {
          self.auditLogger.record(
            AuditEvent.now(resolvedName, "blocked", 0, "approval_required")
          );
          throw new ApprovalRequiredError(
            `Tool '${resolvedName}' was denied by the approval handler.`,
            { toolName: resolvedName }
          );
        }
        self.auditLogger.record(AuditEvent.now(resolvedName, "approved", invocationCost, "approved"));
      }

      // --- Execute ---
      try {
        const result = await Promise.resolve(fn(...args));

        self._dailySpent += invocationCost;
        self._hourlySpent += invocationCost;

        self.auditLogger.record(AuditEvent.now(resolvedName, "success", invocationCost, "allowed"));

        return result as Awaited<ReturnType<T>>;
      } catch (err) {
        self.auditLogger.record(
          AuditEvent.now(resolvedName, "error", 0, "error", {
            error: err instanceof Error ? err.message : String(err),
          })
        );
        throw err;
      }
    };

    return wrapped as unknown as T;
  }

  get dailySpent(): number {
    return this._dailySpent;
  }

  get hourlySpent(): number {
    return this._hourlySpent;
  }

  resetCosts(): void {
    this._dailySpent = 0;
    this._hourlySpent = 0;
    this._hourlyResetAt = Date.now();
  }
}
