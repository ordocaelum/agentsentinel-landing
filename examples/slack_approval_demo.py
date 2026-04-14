"""Slack approval handler demo for AgentSentinel.

Shows how to gate dangerous agent actions behind a Slack approval workflow.
A Block Kit message with ✅ Approve / ❌ Deny buttons is posted when the
agent tries to invoke a tool marked as requiring approval.

Requirements:
    A Slack bot with `chat:write` scope and the bot token set as an env var.

Setup:
    1. Create a Slack app at https://api.slack.com/apps
    2. Add the `chat:write` OAuth scope
    3. Install the app to your workspace
    4. Copy the Bot User OAuth Token

Run:
    SLACK_BOT_TOKEN=xoxb-... SLACK_CHANNEL=#agent-approvals \\
        python examples/slack_approval_demo.py
"""

import os
import time

from agentsentinel import AgentGuard, AgentPolicy, InMemoryAuditSink, AuditLogger
from agentsentinel.handlers.slack import SlackApprover, SlackConfig

# ── Configuration ────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
CHANNEL   = os.environ.get("SLACK_CHANNEL", "#agent-approvals")

if not BOT_TOKEN:
    print("⚠️  SLACK_BOT_TOKEN not set — running in simulation mode (no real Slack messages).")
    print("   Set the variable and re-run to see live Slack messages.\n")
    SIMULATE = True
else:
    SIMULATE = False


# ── Build policy + guard ──────────────────────────────────────────────────────
def build_guard(approver) -> tuple:
    sink = InMemoryAuditSink()
    policy = AgentPolicy(
        daily_budget=10.0,
        require_approval=["send_email", "delete_file", "post_tweet"],
        rate_limits={"*": "60/min"},
    )
    guard = AgentGuard(
        policy=policy,
        approval_handler=approver,
        audit_logger=AuditLogger(sinks=[sink]),
    )
    return guard, sink


# ── Simulate mode: use InMemoryApprover ──────────────────────────────────────
def run_simulation() -> None:
    """Demo without real Slack — uses InMemoryApprover to auto-approve."""
    from agentsentinel import InMemoryApprover

    print("📋 Running in simulation mode — using InMemoryApprover")
    approver = InMemoryApprover(approved_tools={"send_email"})
    guard, sink = build_guard(approver)

    @guard.protect(tool_name="send_email", cost=0.001)
    def send_email(to: str, subject: str, body: str) -> str:
        return f"Email sent to {to}: {subject}"

    @guard.protect(tool_name="read_file")
    def read_file(path: str) -> str:
        return f"Contents of {path}"

    # This will be auto-approved (pre-approved in InMemoryApprover)
    result = send_email(to="user@example.com", subject="Hello", body="World")
    print(f"✅ send_email approved & executed: {result}")

    # This requires no approval
    result = read_file("/tmp/notes.txt")
    print(f"✅ read_file executed: {result}")

    # delete_file needs approval but isn't in the approver list
    from agentsentinel.errors import ApprovalRequiredError

    @guard.protect(tool_name="delete_file")
    def delete_file(path: str) -> str:
        return f"Deleted {path}"

    try:
        delete_file("/important/data.db")
    except ApprovalRequiredError as exc:
        print(f"🚫 delete_file blocked (expected): {exc}")

    print_audit(sink)


# ── Live Slack mode ───────────────────────────────────────────────────────────
def run_slack_demo() -> None:
    """Post a real Slack approval request and wait for a human click."""
    config = SlackConfig(
        bot_token=BOT_TOKEN,
        channel=CHANNEL,
        timeout_seconds=120,
        callback_host="0.0.0.0",
        callback_port=9_876,
        default_on_timeout="deny",
    )

    approver = SlackApprover(config, start_server=True)
    guard, sink = build_guard(approver)

    @guard.protect(tool_name="send_email", cost=0.001)
    def send_email(to: str, subject: str, body: str) -> str:
        return f"Email sent to {to}"

    print(f"📨 Posting approval request to Slack channel {CHANNEL}…")
    print(f"   Callback server listening on port {config.callback_port}")
    print(f"   Timeout: {config.timeout_seconds}s\n")

    from agentsentinel.errors import ApprovalRequiredError
    try:
        result = send_email(
            to="alice@example.com",
            subject="Quarterly Report",
            body="Please find the Q4 report attached.",
        )
        print(f"✅ Approved and executed: {result}")
    except ApprovalRequiredError as exc:
        print(f"🚫 Denied or timed out: {exc}")
    finally:
        approver.stop()

    print_audit(sink)


# ── Audit helper ─────────────────────────────────────────────────────────────
def print_audit(sink) -> None:
    print(f"\n📋 Audit log ({len(sink.events)} events):")
    for event in sink.events:
        print(
            f"   {event.tool_name:25s} | {event.decision:22s} | "
            f"status={event.status:7s} | cost=${event.cost:.4f}"
        )


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("═" * 60)
    print("  AgentSentinel × Slack Approval Demo")
    print("═" * 60)

    if SIMULATE:
        run_simulation()
    else:
        run_slack_demo()
