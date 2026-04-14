"""Demo: AgentSentinel + CrewAI integration.

Requirements:
    pip install crewai

Run:
    python examples/crewai_demo.py
"""

from agentsentinel import AgentGuard, AgentPolicy, InMemoryAuditSink, AuditLogger
from agentsentinel.integrations.crewai import CrewAIGuard, protect_crew

# ── Policy & Guard setup ──────────────────────────────────────────────────────

policy = AgentPolicy(
    daily_budget=5.0,
    require_approval=["send_email", "post_to_social"],
    rate_limits={"search_web": "10/min"},
)

sink = InMemoryAuditSink()
guard = AgentGuard(policy=policy, audit_logger=AuditLogger(sinks=[sink]))
crewai_guard = CrewAIGuard(guard)

# ── Define protected tools ────────────────────────────────────────────────────

@crewai_guard.tool(cost=0.01)
def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Search results for: {query}"


@crewai_guard.tool(cost=0.001)
def analyze_text(text: str) -> str:
    """Analyze text content."""
    return f"Analysis of: {text[:50]}..."


# ── Demo ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("CrewAI tools protected with AgentSentinel!")
    print(f"Daily budget: ${policy.daily_budget}")
    print(f"Approval required for: {policy.require_approval}")

    # Exercise the protected tools
    result = search_web("AI safety research")
    print(f"\nsearch_web result: {result}")

    result = analyze_text("This is a sample text for analysis.")
    print(f"analyze_text result: {result}")

    print(f"\nAudit events recorded: {len(sink.events)}")
    for event in sink.events:
        print(f"  [{event.status}] {event.tool_name} — cost=${event.cost:.4f}")

    print("\n✅ CrewAI integration demo complete.")
