"""Dashboard demo for AgentSentinel.

Spins up the local web dashboard and runs a simulated agent that fires tools
rapidly — so you can watch the real-time stats update in your browser.

Run:
    python examples/dashboard_demo.py

Then open:
    http://localhost:8080

Press Ctrl-C to stop.
"""

import random
import threading
import time

from agentsentinel import (
    AgentGuard,
    AgentPolicy,
    InMemoryApprover,
    InMemoryAuditSink,
    AuditLogger,
)
from agentsentinel.dashboard import start_dashboard

# ── Build a guard with an InMemoryAuditSink so the dashboard can read events ─
sink = InMemoryAuditSink()

policy = AgentPolicy(
    daily_budget=5.0,
    hourly_budget=1.0,
    require_approval=["send_email", "delete_file"],
    rate_limits={
        "search_web": "20/min",
        "execute_code": "5/min",
    },
)

# Pre-approve send_email so we can see approved events in the dashboard
approver = InMemoryApprover(approved_tools={"send_email"})

guard = AgentGuard(
    policy=policy,
    approval_handler=approver,
    audit_logger=AuditLogger(sinks=[sink]),
)

# ── Define some protected tools ───────────────────────────────────────────────

@guard.protect(tool_name="search_web", cost=0.002)
def search_web(query: str) -> str:
    time.sleep(random.uniform(0.02, 0.08))
    return f"Search results for: {query}"


@guard.protect(tool_name="read_file", cost=0.001)
def read_file(path: str) -> str:
    time.sleep(random.uniform(0.01, 0.04))
    return f"File contents of {path}"


@guard.protect(tool_name="send_email", cost=0.005)
def send_email(to: str, subject: str) -> str:
    time.sleep(random.uniform(0.05, 0.1))
    return f"Email sent to {to}"


@guard.protect(tool_name="execute_code", cost=0.01)
def execute_code(code: str) -> str:
    time.sleep(random.uniform(0.03, 0.07))
    return f"Code executed: {code[:40]}…"


@guard.protect(tool_name="delete_file", cost=0.0)
def delete_file(path: str) -> str:
    return f"Deleted {path}"


# ── Simulated agent loop ──────────────────────────────────────────────────────

_QUERIES  = ["latest AI news", "Python best practices", "LangChain docs", "AgentSentinel GitHub"]
_FILES    = ["/data/report.csv", "/logs/agent.log", "/config/settings.json"]
_SUBJECTS = ["Weekly Summary", "Alert: anomaly detected", "Your results are ready"]
_CODE     = ["import os; os.listdir('.')", "print('hello')", "sum(range(100))"]


def _agent_loop() -> None:
    """Mimic an agent calling tools at random intervals."""
    from agentsentinel.errors import (
        ApprovalRequiredError, BudgetExceededError, RateLimitExceededError
    )

    tools = [
        lambda: search_web(random.choice(_QUERIES)),
        lambda: read_file(random.choice(_FILES)),
        lambda: send_email(f"user{random.randint(1,9)}@example.com", random.choice(_SUBJECTS)),
        lambda: execute_code(random.choice(_CODE)),
        # delete_file always needs approval (not in approver list) — will be blocked
        lambda: delete_file(random.choice(_FILES)),
    ]

    iteration = 0
    while True:
        iteration += 1
        fn = random.choice(tools)
        try:
            fn()
        except (ApprovalRequiredError, BudgetExceededError, RateLimitExceededError):
            pass  # Expected — gets recorded in audit log as blocked
        except Exception:
            pass

        # Vary the sleep to create interesting bursts in the dashboard
        delay = random.choice([0.2, 0.2, 0.3, 0.5, 1.0])
        time.sleep(delay)

        # Print a summary every 20 iterations
        if iteration % 20 == 0:
            allowed = sum(1 for e in sink.events if e.decision == "allowed")
            blocked = sum(1 for e in sink.events if e.status == "blocked")
            print(
                f"[Agent] {len(sink.events):4d} events | "
                f"{allowed} allowed | {blocked} blocked | "
                f"${guard.daily_spent:.4f} spent"
            )


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("═" * 60)
    print("  AgentSentinel Dashboard Demo")
    print("═" * 60)
    print()
    print("  Open your browser at:  http://localhost:8080")
    print("  Press Ctrl-C to stop.")
    print()

    # Start the simulated agent in a background thread
    agent_thread = threading.Thread(target=_agent_loop, daemon=True)
    agent_thread.start()

    # Start dashboard (blocks until Ctrl-C)
    start_dashboard(guard, port=8080)
