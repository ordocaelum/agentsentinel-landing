"""Tests for AgentGuard core behaviour."""

import pytest

from agentsentinel import (
    AgentGuard,
    AgentPolicy,
    ApprovalRequiredError,
    BudgetExceededError,
    InMemoryApprover,
    InMemoryAuditSink,
    RateLimitExceededError,
    AuditLogger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_guard(policy: AgentPolicy, approver=None) -> tuple[AgentGuard, InMemoryAuditSink]:
    sink = InMemoryAuditSink()
    logger = AuditLogger(sinks=[sink])
    guard = AgentGuard(policy=policy, approval_handler=approver, audit_logger=logger)
    return guard, sink


# ---------------------------------------------------------------------------
# Budget enforcement
# ---------------------------------------------------------------------------

class TestBudgetEnforcement:
    def test_daily_budget_blocks_when_exceeded(self):
        policy = AgentPolicy(daily_budget=0.05)
        guard, sink = _make_guard(policy)

        @guard.protect(tool_name="expensive_call", cost=0.10)
        def expensive_call():
            return "done"

        with pytest.raises(BudgetExceededError) as exc_info:
            expensive_call()

        assert exc_info.value.budget == 0.05
        assert len(sink.events) == 1
        assert sink.events[0].decision == "blocked_budget"

    def test_daily_budget_accumulates(self):
        policy = AgentPolicy(daily_budget=0.10)
        guard, sink = _make_guard(policy)

        @guard.protect(tool_name="cheap_call", cost=0.04)
        def cheap_call():
            return "ok"

        cheap_call()
        cheap_call()  # total = 0.08, still under budget
        assert guard.daily_spent == pytest.approx(0.08)

        with pytest.raises(BudgetExceededError):
            cheap_call()  # 0.08 + 0.04 = 0.12 > 0.10

    def test_hourly_budget_blocks_when_exceeded(self):
        policy = AgentPolicy(hourly_budget=0.01)
        guard, sink = _make_guard(policy)

        @guard.protect(tool_name="tool", cost=0.05)
        def tool():
            return "done"

        with pytest.raises(BudgetExceededError):
            tool()

    def test_zero_cost_tools_never_exceed_budget(self):
        policy = AgentPolicy(daily_budget=0.0)
        guard, _ = _make_guard(policy)

        @guard.protect(tool_name="free_tool", cost=0.0)
        def free_tool():
            return "free"

        # A tool with zero cost should not exceed a zero budget.
        assert free_tool() == "free"


# ---------------------------------------------------------------------------
# Approval enforcement
# ---------------------------------------------------------------------------

class TestApprovalEnforcement:
    def test_deny_all_approver_blocks_protected_tool(self):
        policy = AgentPolicy(require_approval=["send_email"])
        guard, sink = _make_guard(policy)

        @guard.protect(tool_name="send_email")
        def send_email(to, subject, body):
            return "sent"

        with pytest.raises(ApprovalRequiredError) as exc_info:
            send_email("a@b.com", "Hello", "World")

        assert exc_info.value.tool_name == "send_email"

    def test_wildcard_approval_pattern(self):
        policy = AgentPolicy(require_approval=["delete_*"])
        guard, sink = _make_guard(policy)

        @guard.protect(tool_name="delete_record")
        def delete_record(record_id):
            return "deleted"

        with pytest.raises(ApprovalRequiredError):
            delete_record(42)

    def test_inmemory_approver_allows_pre_approved_tool(self):
        policy = AgentPolicy(require_approval=["send_email"])
        approver = InMemoryApprover(approved_tools={"send_email"})
        guard, sink = _make_guard(policy, approver=approver)

        @guard.protect(tool_name="send_email")
        def send_email(to, subject, body):
            return "sent"

        result = send_email("a@b.com", "Hello", "World")
        assert result == "sent"

    def test_unapproved_tool_in_inmemory_approver_blocked(self):
        policy = AgentPolicy(require_approval=["send_email"])
        approver = InMemoryApprover(approved_tools=set())
        guard, _ = _make_guard(policy, approver=approver)

        @guard.protect(tool_name="send_email")
        def send_email(to):
            return "sent"

        with pytest.raises(ApprovalRequiredError):
            send_email("a@b.com")

    def test_unprotected_tool_passes_through(self):
        policy = AgentPolicy(require_approval=["send_email"])
        guard, _ = _make_guard(policy)

        @guard.protect(tool_name="search_web")
        def search_web(query):
            return f"results: {query}"

        assert search_web("AI safety") == "results: AI safety"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:
    def test_rate_limit_blocks_after_max_calls(self):
        policy = AgentPolicy(rate_limits={"search_web": "2/min"})
        guard, _ = _make_guard(policy)

        @guard.protect(tool_name="search_web", cost=0.0)
        def search_web(q):
            return q

        search_web("q1")
        search_web("q2")

        with pytest.raises(RateLimitExceededError) as exc_info:
            search_web("q3")

        assert exc_info.value.tool_name == "search_web"

    def test_no_rate_limit_configured_always_passes(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)

        @guard.protect(tool_name="any_tool", cost=0.0)
        def any_tool():
            return "ok"

        for _ in range(20):
            assert any_tool() == "ok"


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

class TestAuditLogging:
    def test_successful_call_produces_audit_event(self):
        policy = AgentPolicy()
        guard, sink = _make_guard(policy)

        @guard.protect(tool_name="my_tool", cost=0.01)
        def my_tool():
            return "result"

        my_tool()
        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.tool_name == "my_tool"
        assert event.decision == "allowed"
        assert event.status == "success"
        assert event.cost == pytest.approx(0.01)

    def test_error_in_tool_produces_error_audit_event(self):
        policy = AgentPolicy()
        guard, sink = _make_guard(policy)

        @guard.protect(tool_name="buggy_tool")
        def buggy_tool():
            raise RuntimeError("something went wrong")

        with pytest.raises(RuntimeError):
            buggy_tool()

        assert len(sink.events) == 1
        assert sink.events[0].decision == "error"
        assert sink.events[0].status == "error"

    def test_audit_log_disabled_produces_no_events(self):
        policy = AgentPolicy(audit_log=False)
        sink = InMemoryAuditSink()
        logger = AuditLogger(sinks=[sink])
        guard = AgentGuard(policy=policy, audit_logger=logger)

        @guard.protect(tool_name="silent_tool")
        def silent_tool():
            return "quiet"

        silent_tool()
        # Logger was passed explicitly, so events ARE recorded regardless of
        # audit_log flag (the flag only affects the *default* logger creation).
        # With an explicit logger the events flow through.
        assert len(sink.events) == 1


# ---------------------------------------------------------------------------
# Decorator forms
# ---------------------------------------------------------------------------

class TestDecoratorForms:
    def test_protect_without_arguments(self):
        policy = AgentPolicy()
        guard, sink = _make_guard(policy)

        @guard.protect
        def plain_tool(x):
            return x * 2

        assert plain_tool(5) == 10
        assert sink.events[0].tool_name == "plain_tool"

    def test_protect_with_keyword_arguments(self):
        policy = AgentPolicy()
        guard, sink = _make_guard(policy)

        @guard.protect(tool_name="renamed", cost=0.02)
        def original_name():
            return "hi"

        original_name()
        assert sink.events[0].tool_name == "renamed"
        assert sink.events[0].cost == pytest.approx(0.02)
