/**
 * AgentSentinel — Safety controls for AI agents
 * Copyright (c) 2026 Leland E. Doss. All rights reserved.
 * Licensed under the Business Source License 1.1
 * See LICENSE.md for details
 */
/**
 * Anthropic Claude Tools integration for AgentSentinel.
 *
 * Wraps Anthropic's `tool_use` feature with AgentSentinel protection.
 *
 * @example
 * ```ts
 * import { AgentPolicy, AgentGuard } from "@agentsentinel/sdk";
 * import { protectToolHandlers } from "@agentsentinel/sdk/integrations/anthropicTools";
 *
 * const policy = new AgentPolicy({ dailyBudget: 15.0 });
 * const guard = new AgentGuard({ policy });
 *
 * const handlers = protectToolHandlers(
 *   { get_weather: getWeather, search_web: searchWeb },
 *   guard,
 *   { model: "claude-3-5-sonnet" },
 * );
 * ```
 */

import { AgentGuard } from "../guard";
import { AgentPolicy } from "../policy";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyFn = (...args: any[]) => any;

export interface ToolHandlerOptions {
  /** Per-tool cost overrides (tool name → cost in USD). */
  costs?: Record<string, number>;
  /** Per-tool model name overrides. */
  models?: Record<string, string>;
  /** Default Claude model for cost tracking. */
  model?: string;
}

/** Shape of a `tool_result` content block for the next messages request. */
export interface ToolResultBlock {
  type: "tool_result";
  tool_use_id: string;
  content: string;
  is_error: boolean;
}

/**
 * Wraps Anthropic Claude `tool_use` handlers with {@link AgentGuard}.
 */
export class AnthropicToolsGuard {
  private readonly _guard: AgentGuard;
  private readonly _defaultModel: string;

  constructor(
    guardOrPolicy: AgentGuard | AgentPolicy,
    defaultModel = "claude-3-5-sonnet",
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
   * Protect a single tool handler function.
   *
   * @param fn     The handler callable to protect.
   * @param name   Override the tool name (defaults to `fn.name`).
   * @param cost   Explicit cost per invocation (USD).
   * @param model  Model name for per-model budget tracking.
   * @returns      Protected callable with the same signature.
   */
  protectHandler<T extends AnyFn>(
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
   * Protect a dictionary of tool handlers.
   *
   * @param handlers  Mapping of tool names to handler callables.
   * @param opts      Optional cost/model overrides.
   * @returns         New map with the same keys but guarded callables.
   */
  protectHandlers(
    handlers: Record<string, AnyFn>,
    opts: ToolHandlerOptions = {},
  ): Record<string, AnyFn> {
    const costs = opts.costs ?? {};
    const models = opts.models ?? {};
    const defaultModel = opts.model ?? this._defaultModel;

    const protected_: Record<string, AnyFn> = {};
    for (const [toolName, fn] of Object.entries(handlers)) {
      protected_[toolName] = this.protectHandler(
        fn,
        toolName,
        costs[toolName],
        models[toolName] ?? defaultModel,
      );
    }
    return protected_;
  }

  /**
   * Handle a single `tool_use` block from Claude's response.
   *
   * @param toolUseBlock  A `tool_use` content block from the API response.
   * @param handlers      Protected handler functions.
   * @returns             A `tool_result` block for the next `messages` request.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handleToolUse(toolUseBlock: any, handlers: Record<string, AnyFn>): ToolResultBlock {
    const toolName: string = toolUseBlock.name;
    const toolInput = toolUseBlock.input as Record<string, unknown>;
    const toolUseId: string = toolUseBlock.id;

    let content: string;
    let isError: boolean;

    try {
      if (toolName in handlers) {
        content = String(handlers[toolName](toolInput));
        isError = false;
      } else {
        content = `Unknown tool: ${toolName}`;
        isError = true;
      }
    } catch (err) {
      content = err instanceof Error ? err.message : String(err);
      isError = true;
    }

    return {
      type: "tool_result",
      tool_use_id: toolUseId,
      content,
      is_error: isError,
    };
  }

  /**
   * Handle all `tool_use` blocks in an Anthropic API response.
   *
   * @param response  Full API response from `client.messages.create()`.
   * @param handlers  Protected handler functions.
   * @returns         Array of `tool_result` blocks for the next `messages` request.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  handleToolUses(response: any, handlers: Record<string, AnyFn>): ToolResultBlock[] {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const content: any[] = response?.content ?? [];
    return content
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .filter((block: any) => block?.type === "tool_use")
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .map((block: any) => this.handleToolUse(block, handlers));
  }
}

/**
 * One-liner: protect every handler in `handlers` for Anthropic tool_use.
 *
 * @param handlers       Mapping of tool names to handler callables.
 * @param guardOrPolicy  {@link AgentGuard} or {@link AgentPolicy} to use.
 * @param opts           Optional cost/model overrides.
 * @returns              New map with the same keys but every callable wrapped.
 */
export function protectToolHandlers(
  handlers: Record<string, AnyFn>,
  guardOrPolicy: AgentGuard | AgentPolicy,
  opts: ToolHandlerOptions = {},
): Record<string, AnyFn> {
  const anthropicGuard = new AnthropicToolsGuard(guardOrPolicy, opts.model);
  return anthropicGuard.protectHandlers(handlers, opts);
}
