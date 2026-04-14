"""Demo: AgentSentinel + Anthropic Claude Tools.

Requirements:
    pip install anthropic

Run:
    ANTHROPIC_API_KEY=sk-ant-... python examples/anthropic_tools_demo.py
"""

from agentsentinel import AgentGuard, AgentPolicy, InMemoryAuditSink, AuditLogger
from agentsentinel.integrations.anthropic_tools import (
    AnthropicToolsGuard,
    protect_tool_handlers,
)

# ── Policy & Guard setup ──────────────────────────────────────────────────────

policy = AgentPolicy(
    daily_budget=15.0,
    model_budgets={"claude-3-5-sonnet": 10.0},
)

sink = InMemoryAuditSink()
guard = AgentGuard(policy=policy, audit_logger=AuditLogger(sinks=[sink]))

# ── Define tool handlers ──────────────────────────────────────────────────────

def get_weather(location: str) -> str:
    return f"Weather in {location}: Cloudy, 65°F"


def search_web(query: str) -> str:
    return f"Search results for: {query}"


def calculate(expression: str) -> str:
    """Safe calculator — evaluates simple arithmetic."""
    try:
        # Only allow digits and basic operators for safety
        allowed = set("0123456789+-*/(). ")
        if not all(c in allowed for c in expression):
            return "Error: unsupported characters in expression"
        return str(eval(expression))  # noqa: S307
    except Exception as exc:
        return f"Error: {exc}"


# ── Protect handlers ──────────────────────────────────────────────────────────

handlers = protect_tool_handlers(
    {
        "get_weather": get_weather,
        "search_web": search_web,
        "calculate": calculate,
    },
    guard=guard,
    model="claude-3-5-sonnet",
)

# ── Demo ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Anthropic tool handlers protected with AgentSentinel!")
    print(f"Protected handlers: {list(handlers.keys())}")
    print(f"Daily budget: ${policy.daily_budget}")

    result = handlers["get_weather"](location="London")
    print(f"\nget_weather: {result}")

    result = handlers["search_web"](query="AI safety")
    print(f"search_web: {result}")

    result = handlers["calculate"](expression="2 + 2 * 10")
    print(f"calculate: {result}")

    print(f"\nAudit events: {len(sink.events)}")
    for event in sink.events:
        print(f"  [{event.status}] {event.tool_name}")

    # Demonstrate handle_tool_uses helper
    anthropic_guard = AnthropicToolsGuard(guard=guard, default_model="claude-3-5-sonnet")

    class _MockToolUseBlock:
        """Minimal mock of an Anthropic tool_use content block."""
        type = "tool_use"

        def __init__(self, block_id: str, name: str, input_data: dict):
            self.id = block_id
            self.name = name
            self.input = input_data

    class _MockResponse:
        content = [
            _MockToolUseBlock("toolu_01", "get_weather", {"location": "Tokyo"}),
            _MockToolUseBlock("toolu_02", "calculate", {"expression": "42 * 2"}),
        ]

    tool_results = anthropic_guard.handle_tool_uses(_MockResponse(), handlers)
    print(f"\nTool results:")
    for tr in tool_results:
        print(f"  {tr['tool_use_id']}: {tr['content']} (error={tr['is_error']})")

    print("\n✅ Anthropic Claude Tools integration demo complete.")
