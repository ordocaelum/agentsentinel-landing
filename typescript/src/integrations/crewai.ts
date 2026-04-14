/**
 * CrewAI integration for AgentSentinel.
 *
 * Wraps CrewAI tools and agent actions with AgentSentinel protection.
 *
 * @example
 * ```ts
 * import { AgentPolicy, AgentGuard } from "@agentsentinel/sdk";
 * import { CrewAIGuard, protectCrew } from "@agentsentinel/sdk/integrations/crewai";
 *
 * const policy = new AgentPolicy({ dailyBudget: 10.0, requireApproval: ["send_email"] });
 * const guard = new AgentGuard({ policy });
 * const crewaiGuard = new CrewAIGuard(guard);
 *
 * const searchWeb = crewaiGuard.tool(
 *   (query: string) => `Results for ${query}`,
 *   { name: "search_web", cost: 0.01 }
 * );
 * ```
 */

import { AgentGuard, ProtectOptions } from "../guard";
import { AgentPolicy } from "../policy";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyFn = (...args: any[]) => any;

export interface CrewAIToolOptions {
  /** Override tool name (defaults to function name). */
  name?: string;
  /** Fixed cost per call (USD). */
  cost?: number;
  /** Model name for cost tracking. */
  model?: string;
}

/**
 * Wraps CrewAI tools and agents with {@link AgentGuard} policy enforcement.
 */
export class CrewAIGuard {
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
   * Wrap a tool function with policy enforcement.
   *
   * @param fn   The tool function to protect.
   * @param opts Optional overrides for name, cost, and model.
   * @returns    Protected function with the same signature.
   */
  tool<T extends AnyFn>(fn: T, opts: CrewAIToolOptions = {}): T {
    const options: ProtectOptions = {
      toolName: opts.name ?? fn.name,
      cost: opts.cost,
      model: opts.model,
    };
    return this._guard.protect(fn, options);
  }

  /**
   * Wrap an array of CrewAI tool objects (objects with a `_run` method).
   *
   * @param tools Array of CrewAI BaseTool instances.
   * @returns     The same array with each tool's `_run` patched.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  protectTools(tools: any[]): any[] {
    return tools.map((t) => this._wrapTool(t));
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private _wrapTool(tool: any): any {
    if (tool == null || typeof tool._run !== "function") return tool;

    const toolName: string = tool.name ?? tool.constructor?.name ?? "unknown_tool";
    const originalRun = tool._run.bind(tool) as AnyFn;

    tool._run = this._guard.protect(originalRun, { toolName });
    return tool;
  }
}

/**
 * Protect an entire CrewAI Crew by wrapping all agent tools.
 *
 * @param crew            A CrewAI Crew instance.
 * @param guardOrPolicy   {@link AgentGuard} or {@link AgentPolicy} to use.
 * @returns               The same Crew with all agent tools wrapped.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function protectCrew(crew: any, guardOrPolicy: AgentGuard | AgentPolicy): any {
  const crewaiGuard = new CrewAIGuard(guardOrPolicy);

  const agents: unknown[] = crew?.agents ?? [];
  for (const agent of agents) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const a = agent as any;
    if (Array.isArray(a.tools) && a.tools.length > 0) {
      a.tools = crewaiGuard.protectTools(a.tools);
    }
  }

  return crew;
}

/**
 * Protect a single CrewAI Agent by wrapping its tools.
 *
 * @param agent           A CrewAI Agent instance.
 * @param guardOrPolicy   {@link AgentGuard} or {@link AgentPolicy} to use.
 * @returns               The same Agent with its tools wrapped.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function protectCrewAIAgent(agent: any, guardOrPolicy: AgentGuard | AgentPolicy): any {
  const crewaiGuard = new CrewAIGuard(guardOrPolicy);

  if (Array.isArray(agent?.tools) && agent.tools.length > 0) {
    agent.tools = crewaiGuard.protectTools(agent.tools);
  }

  return agent;
}
