/**
 * Cost tracking and token counting for AgentSentinel.
 */

import { calculateCost, getModelPricing } from "./pricing";

/** Track usage for a specific model. */
export interface ModelUsage {
  readonly modelName: string;
  totalInputTokens: number;
  totalOutputTokens: number;
  totalCost: number;
  callCount: number;
  firstCall: number | undefined;
  lastCall: number | undefined;
}

/** Configuration for cost tracking. */
export interface CostTrackerConfigOptions {
  /** Whether cost tracking is enabled. Default: true. */
  enabled?: boolean;
  /** Track token counts per model. Default: true. */
  trackTokens?: boolean;
  /** Track costs broken down by model. Default: true. */
  trackByModel?: boolean;
  /** Track costs broken down by tool. Default: true. */
  trackByTool?: boolean;
  /**
   * Per-model budget limits (USD).
   * Keys support glob-style wildcards: `{ "gpt-4o": 5.0, "claude-*": 3.0 }`.
   */
  modelBudgets?: Record<string, number>;
}

export class CostTrackerConfig {
  readonly enabled: boolean;
  readonly trackTokens: boolean;
  readonly trackByModel: boolean;
  readonly trackByTool: boolean;
  readonly modelBudgets: Readonly<Record<string, number>>;

  constructor(options: CostTrackerConfigOptions = {}) {
    this.enabled = options.enabled ?? true;
    this.trackTokens = options.trackTokens ?? true;
    this.trackByModel = options.trackByModel ?? true;
    this.trackByTool = options.trackByTool ?? true;
    this.modelBudgets = Object.freeze(options.modelBudgets ?? {});
  }
}

/** Tracks costs across all model calls. */
export class CostTracker {
  readonly config: CostTrackerConfig;

  private _modelUsage = new Map<string, ModelUsage>();
  private _toolCosts = new Map<string, number>();
  private _dailyCosts = new Map<string, number>(); // "YYYY-MM-DD" -> cost
  private _totalCost = 0;
  private _startTime = Date.now();

  constructor(config?: CostTrackerConfig) {
    this.config = config ?? new CostTrackerConfig();
  }

  /**
   * Record token usage and return the cost.
   */
  recordUsage(
    modelName: string,
    inputTokens: number,
    outputTokens: number,
    toolName?: string
  ): number {
    const cost = calculateCost(modelName, inputTokens, outputTokens);
    const now = Date.now();

    // Track by model
    if (!this._modelUsage.has(modelName)) {
      this._modelUsage.set(modelName, {
        modelName,
        totalInputTokens: 0,
        totalOutputTokens: 0,
        totalCost: 0,
        callCount: 0,
        firstCall: undefined,
        lastCall: undefined,
      });
    }

    const usage = this._modelUsage.get(modelName)!;
    usage.totalInputTokens += inputTokens;
    usage.totalOutputTokens += outputTokens;
    usage.totalCost += cost;
    usage.callCount += 1;
    if (usage.firstCall === undefined) usage.firstCall = now;
    usage.lastCall = now;

    // Track by tool
    if (toolName && this.config.trackByTool) {
      this._toolCosts.set(toolName, (this._toolCosts.get(toolName) ?? 0) + cost);
    }

    // Track daily
    const today = new Date().toISOString().slice(0, 10);
    this._dailyCosts.set(today, (this._dailyCosts.get(today) ?? 0) + cost);

    this._totalCost += cost;
    return cost;
  }

  /**
   * Check if a model is within its budget.
   * Returns `{ allowed: true }` or `{ allowed: false, reason: string }`.
   */
  checkModelBudget(modelName: string): { allowed: boolean; reason?: string } {
    for (const [pattern, budget] of Object.entries(this.config.modelBudgets)) {
      if (matchesGlob(modelName.toLowerCase(), pattern.toLowerCase())) {
        const usage = this._modelUsage.get(modelName);
        if (usage && usage.totalCost >= budget) {
          return {
            allowed: false,
            reason: `Model ${modelName} exceeded budget: $${usage.totalCost.toFixed(4)} >= $${budget.toFixed(2)}`,
          };
        }
      }
    }
    return { allowed: true };
  }

  getModelUsage(modelName: string): ModelUsage | undefined {
    return this._modelUsage.get(modelName);
  }

  getAllUsage(): Map<string, ModelUsage> {
    return new Map(this._modelUsage);
  }

  getTodayCost(): number {
    const today = new Date().toISOString().slice(0, 10);
    return this._dailyCosts.get(today) ?? 0;
  }

  getTotalCost(): number {
    return this._totalCost;
  }

  getCostByTool(): Map<string, number> {
    return new Map(this._toolCosts);
  }

  getStats(): {
    totalCost: number;
    todayCost: number;
    models: Record<string, { inputTokens: number; outputTokens: number; cost: number; calls: number }>;
    tools: Record<string, number>;
    daily: Record<string, number>;
  } {
    const models: Record<string, { inputTokens: number; outputTokens: number; cost: number; calls: number }> = {};
    for (const [name, u] of this._modelUsage) {
      models[name] = {
        inputTokens: u.totalInputTokens,
        outputTokens: u.totalOutputTokens,
        cost: u.totalCost,
        calls: u.callCount,
      };
    }

    const tools: Record<string, number> = {};
    for (const [name, cost] of this._toolCosts) {
      tools[name] = cost;
    }

    const daily: Record<string, number> = {};
    for (const [date, cost] of this._dailyCosts) {
      daily[date] = cost;
    }

    return {
      totalCost: this._totalCost,
      todayCost: this.getTodayCost(),
      models,
      tools,
      daily,
    };
  }

  reset(): void {
    this._modelUsage.clear();
    this._toolCosts.clear();
    this._dailyCosts.clear();
    this._totalCost = 0;
    this._startTime = Date.now();
  }
}

/** Simple glob pattern matcher supporting `*` wildcards. */
export function matchesGlob(str: string, pattern: string): boolean {
  if (!pattern.includes("*")) return str === pattern;
  const re = new RegExp(
    "^" + pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*") + "$"
  );
  return re.test(str);
}

/**
 * Estimate token counts from an API response object.
 * Returns `[inputTokens, outputTokens]`.
 */
export function estimateTokensFromResponse(
  response: unknown
): [number, number] {
  if (!response || typeof response !== "object") return [0, 0];

  const r = response as Record<string, unknown>;

  // Dict format
  if (r["usage"] && typeof r["usage"] === "object") {
    const usage = r["usage"] as Record<string, unknown>;
    const input = (usage["prompt_tokens"] ?? usage["input_tokens"] ?? 0) as number;
    const output = (usage["completion_tokens"] ?? usage["output_tokens"] ?? 0) as number;
    if (input > 0 || output > 0) return [input, output];
  }

  return [0, 0];
}
