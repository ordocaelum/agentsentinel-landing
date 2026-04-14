"""Tests for the CrewAI integration."""

import pytest

from agentsentinel import (
    AgentGuard,
    AgentPolicy,
    ApprovalRequiredError,
    BudgetExceededError,
    InMemoryAuditSink,
    RateLimitExceededError,
    AuditLogger,
    InMemoryApprover,
)
from agentsentinel.integrations.crewai import CrewAIGuard, protect_crew, protect_agent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_guard(policy: AgentPolicy, approver=None) -> tuple[AgentGuard, InMemoryAuditSink]:
    sink = InMemoryAuditSink()
    logger = AuditLogger(sinks=[sink])
    guard = AgentGuard(policy=policy, approval_handler=approver, audit_logger=logger)
    return guard, sink


# ---------------------------------------------------------------------------
# CrewAIGuard.tool decorator
# ---------------------------------------------------------------------------

class TestCrewAIGuardTool:
    def test_tool_decorator_without_args(self):
        policy = AgentPolicy()
        guard, sink = _make_guard(policy)
        crewai_guard = CrewAIGuard(guard)

        @crewai_guard.tool
        def my_tool(x: str) -> str:
            return f"result: {x}"

        assert my_tool("hello") == "result: hello"
        assert len(sink.events) == 1
        assert sink.events[0].tool_name == "my_tool"

    def test_tool_decorator_with_cost(self):
        policy = AgentPolicy(daily_budget=1.0)
        guard, sink = _make_guard(policy)
        crewai_guard = CrewAIGuard(guard)

        @crewai_guard.tool(cost=0.05)
        def search_web(query: str) -> str:
            return f"results: {query}"

        search_web("AI safety")
        assert sink.events[0].cost == pytest.approx(0.05)

    def test_tool_decorator_with_name_override(self):
        policy = AgentPolicy()
        guard, sink = _make_guard(policy)
        crewai_guard = CrewAIGuard(guard)

        @crewai_guard.tool(name="custom_name")
        def original_name() -> str:
            return "ok"

        original_name()
        assert sink.events[0].tool_name == "custom_name"

    def test_tool_blocks_on_budget_exceeded(self):
        policy = AgentPolicy(daily_budget=0.04)
        guard, _ = _make_guard(policy)
        crewai_guard = CrewAIGuard(guard)

        @crewai_guard.tool(cost=0.05)
        def expensive_tool() -> str:
            return "done"

        with pytest.raises(BudgetExceededError):
            expensive_tool()

    def test_tool_requires_approval(self):
        policy = AgentPolicy(require_approval=["send_email"])
        guard, _ = _make_guard(policy)
        crewai_guard = CrewAIGuard(guard)

        @crewai_guard.tool(name="send_email")
        def send_email(to: str) -> str:
            return "sent"

        with pytest.raises(ApprovalRequiredError):
            send_email("user@example.com")

    def test_tool_rate_limit(self):
        policy = AgentPolicy(rate_limits={"search_web": "2/min"})
        guard, _ = _make_guard(policy)
        crewai_guard = CrewAIGuard(guard)

        @crewai_guard.tool(name="search_web")
        def search_web(q: str) -> str:
            return q

        search_web("q1")
        search_web("q2")
        with pytest.raises(RateLimitExceededError):
            search_web("q3")


# ---------------------------------------------------------------------------
# CrewAIGuard constructor variants
# ---------------------------------------------------------------------------

class TestCrewAIGuardConstruction:
    def test_construct_with_guard(self):
        policy = AgentPolicy()
        guard = AgentGuard(policy)
        crewai_guard = CrewAIGuard(guard)
        assert crewai_guard.guard is guard

    def test_construct_with_policy(self):
        policy = AgentPolicy(daily_budget=3.0)
        crewai_guard = CrewAIGuard(policy=policy)
        assert isinstance(crewai_guard.guard, AgentGuard)

    def test_construct_with_no_args_uses_default_policy(self):
        crewai_guard = CrewAIGuard()
        assert isinstance(crewai_guard.guard, AgentGuard)


# ---------------------------------------------------------------------------
# protect_tools with mock BaseTool objects
# ---------------------------------------------------------------------------

class _MockBaseTool:
    """Minimal stand-in for crewai.tools.BaseTool."""
    def __init__(self, name: str):
        self.name = name
        self._run_calls = 0

    def _run(self, *args, **kwargs):
        self._run_calls += 1
        return f"ran {self.name}"


class TestProtectTools:
    def test_protect_tools_wraps_run_method(self):
        """When crewai is not installed the tool is returned as-is (no error)."""
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)
        crewai_guard = CrewAIGuard(guard)

        tool = _MockBaseTool("search_web")

        # crewai not installed → _wrap_tool returns the tool unchanged.
        result = crewai_guard._wrap_tool(tool)
        assert result is tool

    def test_protect_tools_returns_list(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)
        crewai_guard = CrewAIGuard(guard)

        class _Plain:
            pass

        tools = [_Plain(), _Plain()]
        protected = crewai_guard.protect_tools(tools)
        assert len(protected) == 2


# ---------------------------------------------------------------------------
# protect_crew
# ---------------------------------------------------------------------------

class TestProtectCrew:
    def test_protect_crew_iterates_agents(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)

        class _Agent:
            tools = []  # no tools to wrap

        class _Crew:
            agents = [_Agent(), _Agent()]

        crew = _Crew()
        result = protect_crew(crew, guard=guard)
        assert result is crew  # same object returned

    def test_protect_crew_requires_no_guard_when_policy_given(self):
        policy = AgentPolicy(daily_budget=1.0)

        class _Crew:
            agents = []

        crew = _Crew()
        result = protect_crew(crew, policy=policy)
        assert result is crew


# ---------------------------------------------------------------------------
# protect_agent
# ---------------------------------------------------------------------------

class TestProtectAgent:
    def test_protect_agent_no_tools(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)

        class _Agent:
            tools = None

        agent = _Agent()
        result = protect_agent(agent, guard=guard)
        assert result is agent
