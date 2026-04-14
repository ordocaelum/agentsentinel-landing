"""
AgentSentinel + OpenClaw Integration Example
=============================================

This example shows how to protect an OpenClaw agent with AgentSentinel
safety controls.  OpenClaw agents often have access to powerful tools
(shell execution, file system, APIs) that require careful guardrails.

Run:
    cd python
    pip install -e .
    python ../examples/openclaw_integration.py
"""

from agentsentinel import (
    AgentGuard,
    AgentPolicy,
    ApprovalRequiredError,
    BudgetExceededError,
    InMemoryApprover,
    InMemoryAuditSink,
    AuditLogger,
    SecurityConfig,
    ToolBlockedError,
)

# ---------------------------------------------------------------------------
# 1. Security-first configuration for OpenClaw
# ---------------------------------------------------------------------------

security = SecurityConfig(
    # Block catastrophic / irreversible operations entirely —
    # no approval flow, these will NEVER run.
    blocked_tools=[
        "rm_rf",
        "format_disk",
        "drop_database",
    ],

    # These always require human approval, even if not in policy.require_approval.
    sensitive_tools=[
        "execute_shell",
        "write_file",
        "delete_*",
        "send_*",
        "post_*",
        "api_call",
    ],

    # Never log these credential patterns to the audit trail.
    redact_patterns=[
        r'OPENAI_API_KEY=[\w-]+',
        r'ANTHROPIC_API_KEY=[\w-]+',
        r'password=\S+',
        r'api[_-]?key["\']?\s*[:=]\s*["\']?[\w-]+',
        r'bearer\s+[\w-]+',
    ],

    # Truncate large parameters (e.g. file contents) after 500 chars.
    max_param_log_size=500,
)

# ---------------------------------------------------------------------------
# 2. Define the full policy
# ---------------------------------------------------------------------------

policy = AgentPolicy(
    # Tight budget limits — start conservatively and raise if needed.
    daily_budget=5.00,
    hourly_budget=1.00,

    # Require human approval for all external / destructive actions.
    require_approval=[
        "execute_shell",   # Shell commands
        "write_file",      # File modifications
        "delete_*",        # Any deletion
        "http_post",       # Outbound HTTP mutations
        "send_email",      # Communications
    ],

    # Aggressive per-tool rate limits.
    rate_limits={
        "execute_shell": "5/min",   # At most 5 shell commands per minute
        "read_file":     "30/min",  # File reads
        "http_get":      "20/min",  # Outbound HTTP reads
        "*":             "100/hour", # Global cap
    },

    security=security,
    sandbox_mode=True,  # Extra restrictions for untrusted agent code
)

# ---------------------------------------------------------------------------
# 3. Create the guard with an in-memory approver for demo purposes
#    In production replace InMemoryApprover with a webhook/Slack approver.
# ---------------------------------------------------------------------------

# Pre-approve only read_file for this demo run.
approver = InMemoryApprover(approved_tools={"read_file"})

# Capture audit events so we can inspect them at the end.
audit_sink = InMemoryAuditSink()
audit_logger = AuditLogger(sinks=[audit_sink])

guard = AgentGuard(
    policy=policy,
    approval_handler=approver,
    audit_logger=audit_logger,
)

# ---------------------------------------------------------------------------
# 4. Protect OpenClaw tools with the guard
# ---------------------------------------------------------------------------

@guard.protect(tool_name="execute_shell")
def execute_shell(command: str) -> str:
    """Execute a shell command — guarded by an approval gate and rate limit.

    WARNING: This demo uses ``shell=True`` for brevity. In production, prefer
    ``shell=False`` with a list of command arguments to prevent shell injection:

        subprocess.run(["ls", "-la", path], shell=False, ...)
    """
    import subprocess
    result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10)  # noqa: S602
    return result.stdout or result.stderr


@guard.protect(tool_name="write_file")
def write_file(path: str, content: str) -> bool:
    """Write to a file — guarded by an approval gate."""
    with open(path, "w") as fh:
        fh.write(content)
    return True


@guard.protect(tool_name="read_file", cost=0.001)
def read_file(path: str) -> str:
    """Read a file — pre-approved in this demo, costs $0.001 per call."""
    with open(path) as fh:
        return fh.read()


@guard.protect(tool_name="rm_rf")
def rm_rf(path: str) -> None:
    """This tool is blocked by SecurityConfig.blocked_tools — it will never run."""
    import shutil
    shutil.rmtree(path)


# ---------------------------------------------------------------------------
# 5. Run the demo
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("AgentSentinel + OpenClaw Integration Demo")
    print("=" * 60)
    print(f"Daily budget:     ${policy.daily_budget:.2f}")
    print(f"Hourly budget:    ${policy.hourly_budget:.2f}")
    print(f"Blocked tools:    {security.blocked_tools}")
    print(f"Sandbox mode:     {policy.sandbox_mode}")
    print()

    # --- Attempt 1: blocked tool (rm_rf) ---
    print(">>> Calling rm_rf('/tmp/test') — should be blocked immediately")
    try:
        rm_rf("/tmp/test")
    except ToolBlockedError as exc:
        print(f"    ✓ Blocked: {exc}")
    print()

    # --- Attempt 2: unapproved shell command ---
    print(">>> Calling execute_shell('echo hello') — requires approval (denied)")
    try:
        execute_shell("echo hello")
    except ApprovalRequiredError as exc:
        print(f"    ✓ Approval required: {exc}")
    print()

    # --- Attempt 3: pre-approved read_file ---
    print(">>> Calling read_file('/etc/hostname') — pre-approved, should succeed")
    try:
        hostname = read_file("/etc/hostname")
        print(f"    ✓ Read succeeded: {hostname.strip()!r}")
    except Exception as exc:
        print(f"    ! Error: {exc}")
    print()

    # --- Attempt 4: exceed hourly budget ---
    print(">>> Simulating budget exhaustion (hourly limit $1.00)")
    # Manually drain the budget by recording a high-cost call via the guard internals
    guard._hourly_spent = 0.99
    try:
        read_file("/etc/hostname")  # $0.001 cost — would push total to $0.991, still OK
        guard._hourly_spent = 1.00  # exhaust budget
        read_file("/etc/hostname")  # should be blocked
    except BudgetExceededError as exc:
        print(f"    ✓ Budget blocked: {exc}")
    guard.reset_costs()
    print()

    # --- Audit log summary ---
    print("Audit trail:")
    for event in audit_sink.events:
        import datetime
        ts = datetime.datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S")
        print(f"  [{ts}] {event.tool_name:20s} | {event.decision:20s} | status={event.status}")


if __name__ == "__main__":
    main()
