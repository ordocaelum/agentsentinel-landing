"""Tests for the OpenAI Assistants integration."""

import json
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
from agentsentinel.integrations.openai_assistants import (
    OpenAIAssistantsGuard,
    protect_function_map,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_guard(policy: AgentPolicy) -> tuple[AgentGuard, InMemoryAuditSink]:
    sink = InMemoryAuditSink()
    logger = AuditLogger(sinks=[sink])
    guard = AgentGuard(policy=policy, audit_logger=logger)
    return guard, sink


class _MockToolCall:
    """Minimal mock of an OpenAI Assistants API tool_call object."""
    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.function = type("F", (), {"name": name, "arguments": arguments})()


# ---------------------------------------------------------------------------
# protect_function_map (convenience one-liner)
# ---------------------------------------------------------------------------

class TestProtectFunctionMap:
    def test_raises_without_guard_or_policy(self):
        with pytest.raises(ValueError, match="Supply either"):
            protect_function_map({"fn": lambda: None})

    def test_wraps_with_guard(self):
        policy = AgentPolicy()
        guard, sink = _make_guard(policy)

        def greet(name: str) -> str:
            return f"Hello, {name}"

        protected = protect_function_map({"greet": greet}, guard=guard)
        result = protected["greet"](name="World")
        assert result == "Hello, World"
        assert sink.events[0].tool_name == "greet"

    def test_wraps_with_policy(self):
        policy = AgentPolicy(daily_budget=5.0)
        protected = protect_function_map({"fn": lambda: "ok"}, policy=policy)
        assert callable(protected["fn"])

    def test_all_keys_preserved(self):
        policy = AgentPolicy()
        fns = {"a": lambda: "a", "b": lambda: "b", "c": lambda: "c"}
        protected = protect_function_map(fns, policy=policy)
        assert set(protected.keys()) == {"a", "b", "c"}

    def test_budget_enforcement(self):
        policy = AgentPolicy(daily_budget=0.04)
        guard, _ = _make_guard(policy)

        def expensive() -> str:
            return "done"

        protected = protect_function_map(
            {"expensive": expensive}, guard=guard, costs={"expensive": 0.05}
        )
        with pytest.raises(BudgetExceededError):
            protected["expensive"]()

    def test_approval_enforcement(self):
        policy = AgentPolicy(require_approval=["send_email"])
        guard, _ = _make_guard(policy)

        protected = protect_function_map(
            {"send_email": lambda to: f"sent to {to}"},
            guard=guard,
        )
        with pytest.raises(ApprovalRequiredError):
            protected["send_email"](to="a@b.com")

    def test_rate_limit_enforcement(self):
        policy = AgentPolicy(rate_limits={"search": "1/min"})
        guard, _ = _make_guard(policy)

        protected = protect_function_map({"search": lambda q: q}, guard=guard)
        protected["search"](q="first")
        with pytest.raises(RateLimitExceededError):
            protected["search"](q="second")


# ---------------------------------------------------------------------------
# OpenAIAssistantsGuard
# ---------------------------------------------------------------------------

class TestOpenAIAssistantsGuard:
    def test_construct_with_guard(self):
        guard = AgentGuard(AgentPolicy())
        oai_guard = OpenAIAssistantsGuard(guard=guard)
        assert oai_guard.guard is guard

    def test_construct_with_policy(self):
        oai_guard = OpenAIAssistantsGuard(policy=AgentPolicy(daily_budget=10.0))
        assert isinstance(oai_guard.guard, AgentGuard)

    def test_construct_default(self):
        oai_guard = OpenAIAssistantsGuard()
        assert isinstance(oai_guard.guard, AgentGuard)

    def test_protect_function_single(self):
        policy = AgentPolicy()
        guard, sink = _make_guard(policy)
        oai_guard = OpenAIAssistantsGuard(guard=guard)

        fn = oai_guard.protect_function(lambda x: x * 2, name="double")
        assert fn(x=5) == 10
        assert sink.events[0].tool_name == "double"

    def test_protect_function_map_costs(self):
        policy = AgentPolicy(daily_budget=0.1)
        guard, sink = _make_guard(policy)
        oai_guard = OpenAIAssistantsGuard(guard=guard)

        protected = oai_guard.protect_function_map(
            {"fn": lambda: "ok"},
            costs={"fn": 0.05},
        )
        protected["fn"]()
        assert sink.events[0].cost == pytest.approx(0.05)

    def test_handle_tool_calls_success(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)
        oai_guard = OpenAIAssistantsGuard(guard=guard)

        def get_weather(location: str) -> str:
            return f"Sunny in {location}"

        protected = oai_guard.protect_function_map({"get_weather": get_weather})

        tool_calls = [
            _MockToolCall("call_01", "get_weather", '{"location": "Paris"}'),
        ]
        outputs = oai_guard.handle_tool_calls(tool_calls, protected)
        assert len(outputs) == 1
        assert outputs[0]["tool_call_id"] == "call_01"
        assert "Paris" in outputs[0]["output"]

    def test_handle_tool_calls_unknown_function(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)
        oai_guard = OpenAIAssistantsGuard(guard=guard)

        tool_calls = [
            _MockToolCall("call_02", "nonexistent_fn", "{}"),
        ]
        outputs = oai_guard.handle_tool_calls(tool_calls, {})
        assert "Unknown function" in outputs[0]["output"]

    def test_handle_tool_calls_error_handling(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)
        oai_guard = OpenAIAssistantsGuard(guard=guard)

        def broken_fn(**kwargs) -> str:
            raise RuntimeError("boom")

        protected = {"broken_fn": broken_fn}
        tool_calls = [
            _MockToolCall("call_03", "broken_fn", "{}"),
        ]
        outputs = oai_guard.handle_tool_calls(tool_calls, protected)
        assert "Error" in outputs[0]["output"]
