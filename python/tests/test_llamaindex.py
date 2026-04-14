"""Tests for the LlamaIndex integration."""

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
from agentsentinel.integrations.llamaindex import (
    LlamaIndexGuard,
    protect_agent,
    protect_query_engine,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_guard(policy: AgentPolicy) -> tuple[AgentGuard, InMemoryAuditSink]:
    sink = InMemoryAuditSink()
    logger = AuditLogger(sinks=[sink])
    guard = AgentGuard(policy=policy, audit_logger=logger)
    return guard, sink


class _MockQueryEngine:
    """Minimal stand-in for a LlamaIndex QueryEngine."""
    def __init__(self):
        self.call_count = 0

    def query(self, query_str: str) -> str:
        self.call_count += 1
        return f"results for: {query_str}"


# ---------------------------------------------------------------------------
# LlamaIndexGuard.tool decorator
# ---------------------------------------------------------------------------

class TestLlamaIndexGuardTool:
    def test_tool_decorator_without_args(self):
        policy = AgentPolicy()
        guard, sink = _make_guard(policy)
        llama_guard = LlamaIndexGuard(guard)

        @llama_guard.tool
        def query_kb(query: str) -> str:
            return f"kb: {query}"

        assert query_kb("test") == "kb: test"
        assert sink.events[0].tool_name == "query_kb"

    def test_tool_decorator_with_cost(self):
        policy = AgentPolicy(daily_budget=1.0)
        guard, sink = _make_guard(policy)
        llama_guard = LlamaIndexGuard(guard)

        @llama_guard.tool(cost=0.02)
        def expensive_query(q: str) -> str:
            return q

        expensive_query("hello")
        assert sink.events[0].cost == pytest.approx(0.02)

    def test_tool_decorator_with_name_override(self):
        policy = AgentPolicy()
        guard, sink = _make_guard(policy)
        llama_guard = LlamaIndexGuard(guard)

        @llama_guard.tool(name="renamed_tool")
        def original() -> str:
            return "ok"

        original()
        assert sink.events[0].tool_name == "renamed_tool"

    def test_tool_blocks_when_budget_exceeded(self):
        policy = AgentPolicy(daily_budget=0.01)
        guard, _ = _make_guard(policy)
        llama_guard = LlamaIndexGuard(guard)

        @llama_guard.tool(cost=0.05)
        def costly() -> str:
            return "done"

        with pytest.raises(BudgetExceededError):
            costly()

    def test_tool_requires_approval(self):
        policy = AgentPolicy(require_approval=["send_email"])
        guard, _ = _make_guard(policy)
        llama_guard = LlamaIndexGuard(guard)

        @llama_guard.tool(name="send_email")
        def send_email(to: str) -> str:
            return "sent"

        with pytest.raises(ApprovalRequiredError):
            send_email("a@b.com")

    def test_tool_rate_limit_enforced(self):
        policy = AgentPolicy(rate_limits={"my_tool": "1/min"})
        guard, _ = _make_guard(policy)
        llama_guard = LlamaIndexGuard(guard)

        @llama_guard.tool(name="my_tool")
        def my_tool() -> str:
            return "ok"

        my_tool()
        with pytest.raises(RateLimitExceededError):
            my_tool()


# ---------------------------------------------------------------------------
# LlamaIndexGuard construction
# ---------------------------------------------------------------------------

class TestLlamaIndexGuardConstruction:
    def test_construct_with_guard(self):
        guard = AgentGuard(AgentPolicy())
        llama_guard = LlamaIndexGuard(guard)
        assert llama_guard.guard is guard

    def test_construct_with_policy(self):
        llama_guard = LlamaIndexGuard(policy=AgentPolicy(daily_budget=5.0))
        assert isinstance(llama_guard.guard, AgentGuard)

    def test_construct_default(self):
        llama_guard = LlamaIndexGuard()
        assert isinstance(llama_guard.guard, AgentGuard)


# ---------------------------------------------------------------------------
# wrap_query_engine
# ---------------------------------------------------------------------------

class TestWrapQueryEngine:
    def test_query_engine_wrapped_and_audited(self):
        policy = AgentPolicy()
        guard, sink = _make_guard(policy)
        llama_guard = LlamaIndexGuard(guard)

        engine = _MockQueryEngine()
        protected = llama_guard.wrap_query_engine(engine, name="my_engine")

        result = protected.query("AI safety")
        assert "AI safety" in result
        assert engine.call_count == 1
        assert sink.events[0].tool_name == "my_engine"

    def test_query_engine_budget_enforced(self):
        policy = AgentPolicy(daily_budget=0.0)
        guard, _ = _make_guard(policy)
        llama_guard = LlamaIndexGuard(guard)

        @llama_guard.tool(cost=0.01, name="query_engine")
        def query(q: str) -> str:
            return q

        with pytest.raises(BudgetExceededError):
            query("test")

    def test_protect_query_engine_convenience(self):
        policy = AgentPolicy()
        guard, sink = _make_guard(policy)

        engine = _MockQueryEngine()
        protected = protect_query_engine(engine, guard=guard, name="docs_engine")
        protected.query("hello")

        assert sink.events[0].tool_name == "docs_engine"


# ---------------------------------------------------------------------------
# wrap_tool and wrap_tools (without llama_index installed)
# ---------------------------------------------------------------------------

class TestWrapTool:
    def test_wrap_tool_returns_non_basetool_unchanged(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)
        llama_guard = LlamaIndexGuard(guard)

        plain_obj = object()
        assert llama_guard.wrap_tool(plain_obj) is plain_obj

    def test_wrap_tools_returns_list_unchanged_when_no_llama(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)
        llama_guard = LlamaIndexGuard(guard)

        items = [object(), object()]
        result = llama_guard.wrap_tools(items)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# protect_agent
# ---------------------------------------------------------------------------

class TestProtectAgent:
    def test_protect_agent_with_tools_attr(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)

        class _Agent:
            tools: list = []

        agent = _Agent()
        result = protect_agent(agent, guard=guard)
        assert result is agent

    def test_protect_agent_with_underscore_tools_attr(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)

        class _Agent:
            _tools: list = []

        agent = _Agent()
        result = protect_agent(agent, guard=guard)
        assert result is agent
