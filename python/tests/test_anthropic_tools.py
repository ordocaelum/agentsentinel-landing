"""Tests for the Anthropic Claude Tools integration."""

import pytest

from agentsentinel import (
    AgentGuard,
    AgentPolicy,
    ApprovalRequiredError,
    BudgetExceededError,
    InMemoryAuditSink,
    RateLimitExceededError,
    AuditLogger,
)
from agentsentinel.integrations.anthropic_tools import (
    AnthropicToolsGuard,
    protect_tool_handlers,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_guard(policy: AgentPolicy) -> tuple[AgentGuard, InMemoryAuditSink]:
    sink = InMemoryAuditSink()
    logger = AuditLogger(sinks=[sink])
    guard = AgentGuard(policy=policy, audit_logger=logger)
    return guard, sink


class _MockToolUseBlock:
    """Minimal mock of an Anthropic tool_use content block."""
    type = "tool_use"

    def __init__(self, block_id: str, name: str, input_data: dict):
        self.id = block_id
        self.name = name
        self.input = input_data


class _MockResponse:
    """Minimal mock of an Anthropic messages.create() response."""
    def __init__(self, blocks):
        self.content = blocks


# ---------------------------------------------------------------------------
# protect_tool_handlers (convenience one-liner)
# ---------------------------------------------------------------------------

class TestProtectToolHandlers:
    def test_raises_without_guard_or_policy(self):
        with pytest.raises(ValueError, match="Supply either"):
            protect_tool_handlers({"fn": lambda: None})

    def test_wraps_with_guard(self):
        policy = AgentPolicy()
        guard, sink = _make_guard(policy)

        def greet(name: str) -> str:
            return f"Hello, {name}"

        handlers = protect_tool_handlers({"greet": greet}, guard=guard)
        result = handlers["greet"](name="Claude")
        assert result == "Hello, Claude"
        assert sink.events[0].tool_name == "greet"

    def test_wraps_with_policy(self):
        policy = AgentPolicy(daily_budget=5.0)
        handlers = protect_tool_handlers({"fn": lambda: "ok"}, policy=policy)
        assert callable(handlers["fn"])

    def test_all_keys_preserved(self):
        policy = AgentPolicy()
        raw = {"a": lambda: "a", "b": lambda: "b"}
        handlers = protect_tool_handlers(raw, policy=policy)
        assert set(handlers.keys()) == {"a", "b"}

    def test_budget_enforcement(self):
        policy = AgentPolicy(daily_budget=0.04)
        guard, _ = _make_guard(policy)

        handlers = protect_tool_handlers(
            {"expensive": lambda: "done"},
            guard=guard,
            costs={"expensive": 0.05},
        )
        with pytest.raises(BudgetExceededError):
            handlers["expensive"]()

    def test_approval_enforcement(self):
        policy = AgentPolicy(require_approval=["send_email"])
        guard, _ = _make_guard(policy)

        handlers = protect_tool_handlers(
            {"send_email": lambda to: f"sent to {to}"},
            guard=guard,
        )
        with pytest.raises(ApprovalRequiredError):
            handlers["send_email"](to="a@b.com")

    def test_rate_limit_enforcement(self):
        policy = AgentPolicy(rate_limits={"search": "1/min"})
        guard, _ = _make_guard(policy)

        handlers = protect_tool_handlers({"search": lambda q: q}, guard=guard)
        handlers["search"](q="first")
        with pytest.raises(RateLimitExceededError):
            handlers["search"](q="second")


# ---------------------------------------------------------------------------
# AnthropicToolsGuard
# ---------------------------------------------------------------------------

class TestAnthropicToolsGuard:
    def test_construct_with_guard(self):
        guard = AgentGuard(AgentPolicy())
        ag = AnthropicToolsGuard(guard=guard)
        assert ag.guard is guard

    def test_construct_with_policy(self):
        ag = AnthropicToolsGuard(policy=AgentPolicy(daily_budget=5.0))
        assert isinstance(ag.guard, AgentGuard)

    def test_construct_default(self):
        ag = AnthropicToolsGuard()
        assert isinstance(ag.guard, AgentGuard)

    def test_protect_handler_single(self):
        policy = AgentPolicy()
        guard, sink = _make_guard(policy)
        ag = AnthropicToolsGuard(guard=guard)

        fn = ag.protect_handler(lambda x: x.upper(), name="upper_tool")
        assert fn(x="hello") == "HELLO"
        assert sink.events[0].tool_name == "upper_tool"

    def test_protect_handlers_costs(self):
        policy = AgentPolicy(daily_budget=0.1)
        guard, sink = _make_guard(policy)
        ag = AnthropicToolsGuard(guard=guard)

        protected = ag.protect_handlers(
            {"fn": lambda: "ok"},
            costs={"fn": 0.03},
        )
        protected["fn"]()
        assert sink.events[0].cost == pytest.approx(0.03)

    def test_handle_tool_use_success(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)
        ag = AnthropicToolsGuard(guard=guard)

        def get_weather(location: str) -> str:
            return f"Sunny in {location}"

        handlers = ag.protect_handlers({"get_weather": get_weather})
        block = _MockToolUseBlock("toolu_01", "get_weather", {"location": "London"})

        result = ag.handle_tool_use(block, handlers)
        assert result["type"] == "tool_result"
        assert result["tool_use_id"] == "toolu_01"
        assert "London" in result["content"]
        assert result["is_error"] is False

    def test_handle_tool_use_unknown_tool(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)
        ag = AnthropicToolsGuard(guard=guard)

        block = _MockToolUseBlock("toolu_02", "nonexistent", {})
        result = ag.handle_tool_use(block, {})
        assert result["is_error"] is True
        assert "Unknown tool" in result["content"]

    def test_handle_tool_use_error_propagated(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)
        ag = AnthropicToolsGuard(guard=guard)

        def broken(**kwargs) -> str:
            raise ValueError("something broke")

        handlers = {"broken": broken}
        block = _MockToolUseBlock("toolu_03", "broken", {})
        result = ag.handle_tool_use(block, handlers)
        assert result["is_error"] is True
        assert "something broke" in result["content"]

    def test_handle_tool_uses_filters_tool_use_blocks(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)
        ag = AnthropicToolsGuard(guard=guard)

        def fn(x: str) -> str:
            return x

        handlers = ag.protect_handlers({"my_tool": fn})
        block = _MockToolUseBlock("toolu_04", "my_tool", {"x": "hello"})

        class _TextBlock:
            type = "text"
            text = "some text"

        response = _MockResponse([_TextBlock(), block])
        results = ag.handle_tool_uses(response, handlers)

        # Only the tool_use block should be processed
        assert len(results) == 1
        assert results[0]["content"] == "hello"

    def test_default_model_used_for_tracking(self):
        """Model budget check blocks once accumulated cost meets the budget cap."""
        from agentsentinel.errors import ModelBudgetExceededError

        # Policy caps 'claude-3-opus' at $0.00 and guard uses that model by default.
        policy = AgentPolicy(model_budgets={"claude-3-opus": 0.0})
        guard, _ = _make_guard(policy)
        ag = AnthropicToolsGuard(guard=guard, default_model="claude-3-opus")

        # Explicitly pass model= to make the test intention unambiguous.
        fn = ag.protect_handler(lambda: "ok", name="test_tool", model="claude-3-opus")

        # First call always succeeds (no usage recorded yet).
        fn()

        # Second call is blocked because accumulated cost (0.0) >= budget (0.0).
        with pytest.raises(ModelBudgetExceededError):
            fn()
