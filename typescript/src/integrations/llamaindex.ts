/**
 * LlamaIndex integration for AgentSentinel.
 *
 * Wraps LlamaIndex tools and query engines with AgentSentinel protection.
 *
 * @example
 * ```ts
 * import { AgentPolicy, AgentGuard } from "@agentsentinel/sdk";
 * import { LlamaIndexGuard, protectLlamaIndexAgent } from "@agentsentinel/sdk/integrations/llamaindex";
 *
 * const policy = new AgentPolicy({ dailyBudget: 10.0 });
 * const guard = new AgentGuard({ policy });
 * const llamaGuard = new LlamaIndexGuard(guard);
 *
 * const queryKb = llamaGuard.tool(
 *   (query: string) => `Results for ${query}`,
 *   { name: "query_knowledge_base", model: "gpt-4o" }
 * );
 * ```
 */

import { AgentGuard, ProtectOptions } from "../guard";
import { AgentPolicy } from "../policy";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyFn = (...args: any[]) => any;

export interface LlamaIndexToolOptions {
  /** Override tool name. */
  name?: string;
  /** Fixed cost per call (USD). */
  cost?: number;
  /** Model name for cost tracking. */
  model?: string;
}

/**
 * Wraps LlamaIndex tools and agents with {@link AgentGuard} policy enforcement.
 */
export class LlamaIndexGuard {
  private readonly _guard: AgentGuard;

  constructor(guardOrPolicy: AgentGuard | AgentPolicy) {
    this._guard =
      guardOrPolicy instanceof AgentGuard
        ? guardOrPolicy
        : new AgentGuard({ policy: guardOrPolicy });
  }

  /** Access the underlying {@link AgentGuard}. */
  get guard(): AgentGuard {
    return this._guard;
  }

  /**
   * Wrap a plain function that will be used as a LlamaIndex tool.
   *
   * @param fn   The function to protect.
   * @param opts Optional overrides for name, cost, and model.
   * @returns    Protected function with the same signature.
   */
  tool<T extends AnyFn>(fn: T, opts: LlamaIndexToolOptions = {}): T {
    const options: ProtectOptions = {
      toolName: opts.name ?? fn.name,
      cost: opts.cost,
      model: opts.model,
    };
    return this._guard.protect(fn, options);
  }

  /**
   * Wrap a LlamaIndex tool object (with a `call` method).
   *
   * @param tool  A LlamaIndex BaseTool instance.
   * @param name  Optional override for the tool name.
   * @returns     The same tool with its `call` method patched.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  wrapTool(tool: any, name?: string): any {
    if (tool == null || typeof tool.call !== "function") return tool;

    const toolName: string =
      name ?? tool.metadata?.name ?? tool.constructor?.name ?? "unknown_tool";
    const originalCall = tool.call.bind(tool) as AnyFn;

    tool.call = this._guard.protect(originalCall, { toolName });
    return tool;
  }

  /**
   * Wrap multiple LlamaIndex tool objects.
   *
   * @param tools Array of LlamaIndex BaseTool instances.
   * @returns     The same array with each tool's `call` method patched.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  wrapTools(tools: any[]): any[] {
    return tools.map((t) => this.wrapTool(t));
  }

  /**
   * Wrap a LlamaIndex QueryEngine with protection.
   *
   * @param engine  A LlamaIndex query engine instance.
   * @param name    Tool name for policy matching and audit logs.
   * @returns       The same engine with its `query` method patched.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  wrapQueryEngine(engine: any, name = "query_engine"): any {
    if (engine == null || typeof engine.query !== "function") return engine;

    const originalQuery = engine.query.bind(engine) as AnyFn;
    engine.query = this._guard.protect(originalQuery, { toolName: name });
    return engine;
  }
}

/**
 * Protect a LlamaIndex agent by wrapping all of its tools.
 *
 * @param agent           A LlamaIndex agent instance.
 * @param guardOrPolicy   {@link AgentGuard} or {@link AgentPolicy} to use.
 * @returns               The same agent with its tools wrapped.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function protectLlamaIndexAgent(agent: any, guardOrPolicy: AgentGuard | AgentPolicy): any {
  const llamaGuard = new LlamaIndexGuard(guardOrPolicy);

  if (Array.isArray(agent?._tools)) {
    agent._tools = llamaGuard.wrapTools(agent._tools);
  } else if (Array.isArray(agent?.tools)) {
    agent.tools = llamaGuard.wrapTools(agent.tools);
  }

  return agent;
}

/**
 * Protect a LlamaIndex QueryEngine.
 *
 * @param engine          A LlamaIndex query engine instance.
 * @param guardOrPolicy   {@link AgentGuard} or {@link AgentPolicy} to use.
 * @param name            Tool name for policy matching (default: `"query_engine"`).
 * @returns               The same engine with its `query` method wrapped.
 */
export function protectQueryEngine(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  engine: any,
  guardOrPolicy: AgentGuard | AgentPolicy,
  name = "query_engine",
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
): any {
  const llamaGuard = new LlamaIndexGuard(guardOrPolicy);
  return llamaGuard.wrapQueryEngine(engine, name);
}
