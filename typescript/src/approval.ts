import { ApprovalRequiredError } from "./errors";

/** Interface for deciding whether a tool invocation is approved. */
export interface ApprovalHandler {
  /**
   * Return `true` if approved, `false` to deny (or throw
   * {@link ApprovalRequiredError} to signal that no synchronous decision
   * is possible).
   */
  requestApproval(toolName: string, args: unknown[]): boolean | Promise<boolean>;
}

/**
 * Denies every approval request by throwing {@link ApprovalRequiredError}.
 * This is the **default** approval handler.
 */
export class DenyAllApprover implements ApprovalHandler {
  requestApproval(toolName: string): never {
    throw new ApprovalRequiredError(
      `Tool '${toolName}' requires human approval — no approver is configured.`,
      { toolName }
    );
  }
}

/**
 * Simple approver backed by an in-memory allow-list.
 * Useful for demos and unit tests.
 *
 * @example
 * ```ts
 * const approver = new InMemoryApprover(new Set(["send_email"]));
 * const guard = new AgentGuard({ policy, approvalHandler: approver });
 * ```
 */
export class InMemoryApprover implements ApprovalHandler {
  private approved: Set<string>;

  constructor(approvedTools: Set<string> = new Set()) {
    this.approved = new Set(approvedTools);
  }

  approve(toolName: string): void {
    this.approved.add(toolName);
  }

  revoke(toolName: string): void {
    this.approved.delete(toolName);
  }

  requestApproval(toolName: string): boolean {
    if (this.approved.has(toolName)) return true;
    throw new ApprovalRequiredError(
      `Tool '${toolName}' is not in the pre-approved list.`,
      { toolName }
    );
  }
}
