/**
 * OpenAI Assistants API integration for AgentSentinel.
 *
 * Wraps OpenAI Assistants API function calling with AgentSentinel protection.
 *
 * @example
 * ```ts
 * import { AgentPolicy, AgentGuard } from "@agentsentinel/sdk";
 * import { protectFunctionMap } from "@agentsentinel/sdk/integrations/openaiAssistants";
 *
 * const policy = new AgentPolicy({ dailyBudget: 10.0, requireApproval: ["send_email"] });
 * const guard = new AgentGuard({ policy });
 *
 * const protectedFns = protectFunctionMap(
 *   { get_weather: getWeather, send_email: sendEmail },
 *   guard,
 * );
 * ```
 */

import { AgentGuard } from "../guard";
import { AgentPolicy } from "../policy";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyFn = (...args: any[]) => any;

export interface FunctionMapOptions {
  /** Per-function cost overrides (function name → cost in USD). */
  costs?: Record<string, number>;
  /** Per-function model name overrides. */
  models?: Record<string, string>;
  /** Default model for cost tracking. */
  defaultModel?: string;
}

/**
 * Wraps OpenAI Assistants API function calls with {@link AgentGuard}.
 */
export class OpenAIAssistantsGuard {
  private readonly _guard: AgentGuard;
  private readonly _defaultModel: string;

  constructor(
    guardOrPolicy: AgentGuard | AgentPolicy,
    defaultModel = "gpt-4o",
  ) {
    this._guard =
      guardOrPolicy instanceof AgentGuard
        ? guardOrPolicy
        : new AgentGuard({ policy: guardOrPolicy });
    this._defaultModel = defaultModel;
  }

  /** Access the underlying {@link AgentGuard}. */
  get guard(): AgentGuard {
    return this._guard;
  }

  /**
   * Protect a single function.
   *
   * @param fn     The callable to protect.
   * @param name   Override the tool name (defaults to `fn.name`).
   * @param cost   Explicit cost per invocation (USD).
   * @param model  Model name for per-model budget tracking.
   * @returns      Protected callable with the same signature.
   */
  protectFunction<T extends AnyFn>(
    fn: T,
    name?: string,
    cost?: number,
    model?: string,
  ): T {
    return this._guard.protect(fn, {
      toolName: name ?? fn.name,
      cost,
      model: model ?? this._defaultModel,
    });
  }

  /**
   * Protect a dictionary of functions.
   *
   * @param functions  Mapping of function names to callables.
   * @param opts       Optional cost/model overrides and default model.
   * @returns          New map with the same keys but guarded callables.
   */
  protectFunctionMap(
    functions: Record<string, AnyFn>,
    opts: FunctionMapOptions = {},
  ): Record<string, AnyFn> {
    const costs = opts.costs ?? {};
    const models = opts.models ?? {};
    const defaultModel = opts.defaultModel ?? this._defaultModel;

    const protected_: Record<string, AnyFn> = {};
    for (const [fnName, fn] of Object.entries(functions)) {
      protected_[fnName] = this.protectFunction(
        fn,
        fnName,
        costs[fnName],
        models[fnName] ?? defaultModel,
      );
    }
    return protected_;
  }

  /**
   * Handle tool calls from an Assistant run, returning tool outputs.
   *
   * @param toolCalls  Tool call objects from `run.required_action.submit_tool_outputs.tool_calls`.
   * @param functions  Protected function map.
   * @returns          Array of `{ tool_call_id, output }` objects.
   */
  handleToolCalls(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    toolCalls: any[],
    functions: Record<string, AnyFn>,
  ): Array<{ tool_call_id: string; output: string }> {
    return toolCalls.map((toolCall) => {
      const fnName: string = toolCall.function.name;
      const fnArgs = JSON.parse(toolCall.function.arguments as string) as Record<string, unknown>;

      let result: string;
      try {
        if (fnName in functions) {
          result = String(functions[fnName](fnArgs));
        } else {
          result = `Error: Unknown function '${fnName}'`;
        }
      } catch (err) {
        result = `Error: ${err instanceof Error ? err.message : String(err)}`;
      }

      return { tool_call_id: toolCall.id as string, output: result };
    });
  }
}

/**
 * One-liner: protect every function in `functions` for the Assistants API.
 *
 * @param functions      Mapping of function names to callables.
 * @param guardOrPolicy  {@link AgentGuard} or {@link AgentPolicy} to use.
 * @param opts           Optional cost/model overrides.
 * @returns              New map with the same keys but every callable wrapped.
 */
export function protectFunctionMap(
  functions: Record<string, AnyFn>,
  guardOrPolicy: AgentGuard | AgentPolicy,
  opts: FunctionMapOptions = {},
): Record<string, AnyFn> {
  const oaiGuard = new OpenAIAssistantsGuard(guardOrPolicy, opts.defaultModel);
  return oaiGuard.protectFunctionMap(functions, opts);
}
