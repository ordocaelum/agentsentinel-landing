"""AgentSentinel Python Quickstart Example

Demonstrates:
  - Defining an AgentPolicy with budget limits, approval patterns, and rate limits.
  - Wrapping tools with @guard.protect.
  - BudgetExceededError when the daily limit is hit.
  - ApprovalRequiredError for tools that require human sign-off.
  - RateLimitExceededError when a tool fires too often.
  - In-memory approval for testing/demo purposes.

Run:
    cd python
    pip install -e .
    python ../examples/python_quickstart.py
"""

from agentsentinel import (
    AgentGuard,
    AgentPolicy,
    ApprovalRequiredError,
    BudgetExceededError,
    InMemoryApprover,
    InMemoryAuditSink,
    AuditLogger,
    RateLimitExceededError,
)

# ─── 1. Define your safety policy ──────────────────────────────────────────

policy = AgentPolicy(
    daily_budget=10.0,           # hard stop at $10/day
    hourly_budget=2.0,           # never more than $2/hour
    require_approval=[
        "send_email",            # outbound communications
        "delete_*",              # any destructive action
        "execute_sql",           # database writes
    ],
    rate_limits={
        "search_web": "5/min",   # max 5 searches per minute
        "*": "50/hour",          # global default: 50 calls/hour
    },
    audit_log=True,
    alert_channel="console",
)

# ─── 2. Create a guard, using in-memory sinks for demo output ──────────────

sink = InMemoryAuditSink()
logger = AuditLogger(sinks=[sink])
guard = AgentGuard(policy=policy, audit_logger=logger)


# ─── 3. Decorate your tools ────────────────────────────────────────────────

@guard.protect(tool_name="search_web", cost=0.01)
def search_web(query: str) -> str:
    """Simulates a web search."""
    return f"[search results for: {query}]"


@guard.protect(tool_name="send_email")
def send_email(to: str, subject: str, body: str) -> None:
    """Simulates sending an email (requires approval)."""
    print(f"  📧  Email sent to {to!r}: {subject}")


@guard.protect(tool_name="delete_record")
def delete_record(record_id: int) -> None:
    """Simulates deleting a record (requires approval — matches 'delete_*')."""
    print(f"  🗑️  Record {record_id} deleted.")


# ─── 4. Demo: allowed calls ────────────────────────────────────────────────

print("=" * 60)
print("Demo 1: Allowed tool calls")
print("=" * 60)

result = search_web("AI safety best practices")
print(f"search_web result → {result}\n")

result = search_web("how to limit LLM costs")
print(f"search_web result → {result}\n")

# ─── 5. Demo: approval-gated tool (denied by default) ─────────────────────

print("=" * 60)
print("Demo 2: Approval gate (DenyAllApprover by default)")
print("=" * 60)

try:
    send_email("user@example.com", "Hello from agent", "This is a test.")
except ApprovalRequiredError as e:
    print(f"✋ Blocked — {e}\n")

# ─── 6. Demo: approval-gated tool (pre-approved) ──────────────────────────

print("=" * 60)
print("Demo 3: Approval gate (InMemoryApprover — pre-approved)")
print("=" * 60)

approver = InMemoryApprover(approved_tools={"send_email"})
guard2 = AgentGuard(policy=policy, approval_handler=approver, audit_logger=logger)


@guard2.protect(tool_name="send_email")
def send_email_approved(to: str, subject: str, body: str) -> None:
    print(f"  📧  Email sent to {to!r}: {subject}")


send_email_approved("user@example.com", "Hello from agent", "This is a test.")
print()

# ─── 7. Demo: rate limiting ────────────────────────────────────────────────

print("=" * 60)
print("Demo 4: Rate limit exceeded")
print("=" * 60)

# Use a fresh guard so Demo 1 call history doesn't count against the limit.
rate_policy = AgentPolicy(rate_limits={"search_web": "3/min"})
rate_guard = AgentGuard(policy=rate_policy, audit_logger=logger)


@rate_guard.protect(tool_name="search_web", cost=0.01)
def search_web_limited(query: str) -> str:
    return f"[search results for: {query}]"


for i in range(3):
    search_web_limited(f"query {i}")
    print(f"  ✓ search_web call {i + 1} succeeded")

try:
    search_web_limited("one too many")
except RateLimitExceededError as e:
    print(f"⏱️  Blocked — {e}\n")

# ─── 8. Demo: budget enforcement ──────────────────────────────────────────

print("=" * 60)
print("Demo 5: Budget exceeded")
print("=" * 60)

tight_policy = AgentPolicy(daily_budget=0.02)
tight_guard = AgentGuard(policy=tight_policy, audit_logger=logger)


@tight_guard.protect(tool_name="expensive_tool", cost=0.015)
def expensive_tool() -> str:
    return "expensive result"


expensive_tool()  # $0.015 — under budget
print(f"  ✓ First call succeeded (spent: ${tight_guard.daily_spent:.3f})")

try:
    expensive_tool()  # Would bring total to $0.03 > $0.02
except BudgetExceededError as e:
    print(f"💸  Blocked — {e}\n")

# ─── 9. Audit log summary ─────────────────────────────────────────────────

print("=" * 60)
print(f"Audit log: {len(sink.events)} events recorded")
print("=" * 60)
for ev in sink.events:
    import datetime
    ts = datetime.datetime.fromtimestamp(ev.timestamp).strftime("%H:%M:%S")
    print(f"  {ts} | {ev.tool_name:20s} | {ev.decision:22s} | ${ev.cost:.4f}")
