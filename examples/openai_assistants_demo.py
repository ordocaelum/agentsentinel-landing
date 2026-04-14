"""Demo: AgentSentinel + OpenAI Assistants API.

Requirements:
    pip install openai

Run:
    OPENAI_API_KEY=sk-... python examples/openai_assistants_demo.py
"""

from agentsentinel import AgentGuard, AgentPolicy, InMemoryAuditSink, AuditLogger
from agentsentinel.integrations.openai_assistants import (
    OpenAIAssistantsGuard,
    protect_function_map,
)

# ── Policy & Guard setup ──────────────────────────────────────────────────────

policy = AgentPolicy(
    daily_budget=20.0,
    model_budgets={"gpt-4o": 10.0},
    require_approval=["send_email"],
)

sink = InMemoryAuditSink()
guard = AgentGuard(policy=policy, audit_logger=AuditLogger(sinks=[sink]))

# ── Define functions for the assistant ───────────────────────────────────────

def get_weather(location: str) -> str:
    return f"Weather in {location}: Sunny, 72°F"


def send_email(to: str, subject: str, body: str) -> str:
    # Would require approval due to policy
    return f"Email sent to {to}"


def search_database(query: str) -> str:
    return f"Database results: {query}"


# ── Protect all functions ─────────────────────────────────────────────────────

protected_functions = protect_function_map(
    {
        "get_weather": get_weather,
        "send_email": send_email,
        "search_database": search_database,
    },
    guard=guard,
    default_model="gpt-4o",
)

# ── Demo ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("OpenAI Assistants functions protected with AgentSentinel!")
    print(f"Protected functions: {list(protected_functions.keys())}")
    print(f"Daily budget: ${policy.daily_budget}")
    print(f"Approval required for: {policy.require_approval}")

    # Exercise unprotected functions
    result = protected_functions["get_weather"](location="San Francisco")
    print(f"\nget_weather: {result}")

    result = protected_functions["search_database"](query="recent AI papers")
    print(f"search_database: {result}")

    print(f"\nAudit events: {len(sink.events)}")
    for event in sink.events:
        print(f"  [{event.status}] {event.tool_name}")

    # Demonstrate handle_tool_calls helper
    oai_guard = OpenAIAssistantsGuard(guard=guard, default_model="gpt-4o")

    class _MockToolCall:
        """Minimal mock of an Assistants API tool_call object."""
        def __init__(self, call_id: str, name: str, arguments: str):
            self.id = call_id
            self.function = type("F", (), {"name": name, "arguments": arguments})()

    tool_calls = [
        _MockToolCall("call_001", "get_weather", '{"location": "Paris"}'),
        _MockToolCall("call_002", "search_database", '{"query": "AI agents"}'),
    ]

    outputs = oai_guard.handle_tool_calls(tool_calls, protected_functions)
    print(f"\nTool outputs:")
    for output in outputs:
        print(f"  {output['tool_call_id']}: {output['output']}")

    print("\n✅ OpenAI Assistants integration demo complete.")
