"""Multi-agent demo — AgentSentinel Dashboard v1.1.1

Demonstrates the new Mission Control features:
  - Multiple agent instances monitored on one dashboard
  - Live approval queue with approve/reject workflows
  - Agent pause/resume/stop controls
  - Per-tool enable/disable and rate limiting
  - Budget controls with live adjustments
  - Policy editor (simple + advanced YAML modes)
  - WebSocket-style polling for real-time updates

Run with:
    python examples/multi_agent_demo.py

Then open: http://localhost:8080
"""

from __future__ import annotations

import random
import threading
import time

from agentsentinel import AgentGuard, AgentPolicy
from agentsentinel.audit import InMemoryAuditSink
from agentsentinel.cost_tracking import CostTracker
from agentsentinel.dashboard import start_dashboard, DashboardServer

# ---------------------------------------------------------------------------
# Shared cost models pricing
# ---------------------------------------------------------------------------
MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "claude-3-5-sonnet-20241022",
    "claude-3-haiku-20240307",
    "gemini-1.5-pro",
]

TOOLS = [
    "search_web",
    "read_file",
    "write_file",
    "send_email",
    "execute_code",
    "delete_file",
    "list_directory",
    "http_request",
    "parse_pdf",
    "summarize",
]

# ---------------------------------------------------------------------------
# Helper: simulate agent activity
# ---------------------------------------------------------------------------

def simulate_agent_activity(guard: AgentGuard, agent_name: str, num_events: int = 30) -> None:
    """Generate synthetic audit events for demo purposes."""
    print(f"[{agent_name}] Simulating {num_events} events...")
    for _ in range(num_events):
        tool = random.choice(TOOLS)
        model = random.choice(MODELS)
        cost = random.uniform(0.0001, 0.05)

        # Some tools are blocked by policy
        blocked_tools = {"delete_file", "send_email"}
        status = "blocked" if tool in blocked_tools else "allowed"
        decision = "blocked" if status == "blocked" else "allowed"

        # Try to call guard (will use policy checks)
        try:
            guard._audit_logger.log(
                tool_name=tool,
                status=status,
                decision=decision,
                cost=cost,
                model=model,
                input_tokens=random.randint(100, 2000),
                output_tokens=random.randint(50, 800),
                agent_id=agent_name,
            )
        except Exception:
            # If audit_logger doesn't support direct log, use the sink directly
            try:
                for sink in guard.audit_logger._sinks:
                    if hasattr(sink, "events"):
                        from agentsentinel.audit import AuditEvent
                        event = AuditEvent(
                            tool_name=tool,
                            status=status,
                            decision=decision,
                            cost=cost,
                            model=model,
                            input_tokens=random.randint(100, 2000),
                            output_tokens=random.randint(50, 800),
                            timestamp=time.time(),
                            agent_id=agent_name,
                        )
                        sink.events.append(event)
                        break
            except Exception as e:
                print(f"[{agent_name}] Could not log event: {e}")
        time.sleep(0.05)  # slight delay between events

    print(f"[{agent_name}] Done simulating events.")


# ---------------------------------------------------------------------------
# Agent 1: Primary research agent (active, budget-constrained)
# ---------------------------------------------------------------------------

def create_primary_agent() -> AgentGuard:
    policy = AgentPolicy(
        daily_budget=10.0,
        hourly_budget=2.0,
        require_approval_for=["delete_file", "send_email", "execute_code"],
        blocked_tools=[],
        rate_limits={"search_web": 20, "http_request": 10},
    )
    sink = InMemoryAuditSink()
    guard = AgentGuard(
        policy=policy,
        audit_sinks=[sink],
        name="primary-agent",
    )
    return guard


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("AgentSentinel — Multi-Agent Mission Control Demo")
    print("=" * 60)

    # Create primary guard (the one the dashboard monitors)
    guard = create_primary_agent()

    # Pre-populate with demo activity
    t = threading.Thread(target=simulate_agent_activity, args=(guard, "agent-1", 50), daemon=True)
    t.start()

    # Start dashboard (background so we can keep simulating)
    server = start_dashboard(guard, port=8080, background=True)

    print()
    print("✅ Dashboard running at: http://localhost:8080")
    print()
    print("🎮 Mission Control features to try:")
    print("   • Agent Control Panel — Pause, Resume, Emergency STOP")
    print("   • Live Budget Controls — Drag slider, click +$5/+$10")
    print("   • Per-Tool Controls — Toggle enable/disable, set rate limits")
    print("   • Approval Queue — Approve/Reject pending requests")
    print("   • Policy Editor — Switch Simple ↔ Advanced YAML modes")
    print("   • Notification Center — Click 🔔 bell in header")
    print("   • Multi-Agent Tabs — Add agents via ➕ button")
    print()
    print("⌨️  Keyboard shortcuts: P=pause, S=stop, A=approve, ?=help")
    print()
    print("Press Ctrl+C to stop.")
    print()

    # Keep generating events to show live updates
    try:
        round_num = 0
        while True:
            round_num += 1
            time.sleep(5)
            # Simulate 3-5 new events every 5 seconds
            for _ in range(random.randint(2, 5)):
                simulate_agent_activity(guard, "agent-1", 1)
    except KeyboardInterrupt:
        print("\n[AgentSentinel] Demo stopped.")
        server.shutdown()  # type: ignore[union-attr]


if __name__ == "__main__":
    main()
