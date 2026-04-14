"""Tests for the cost tracking engine."""

import time

import pytest

from agentsentinel import (
    AgentGuard,
    AgentPolicy,
    InMemoryAuditSink,
    AuditLogger,
    ModelBudgetExceededError,
)
from agentsentinel.cost_tracker import (
    CostTracker,
    CostTrackerConfig,
    ModelUsage,
    count_tokens,
    estimate_tokens_from_response,
)
from agentsentinel.pricing import ModelProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_guard(policy: AgentPolicy) -> tuple[AgentGuard, InMemoryAuditSink]:
    sink = InMemoryAuditSink()
    logger = AuditLogger(sinks=[sink])
    guard = AgentGuard(policy=policy, audit_logger=logger)
    return guard, sink


# ---------------------------------------------------------------------------
# CostTracker basics
# ---------------------------------------------------------------------------

class TestCostTrackerBasics:
    def test_starts_with_zero_cost(self):
        tracker = CostTracker()
        assert tracker.get_total_cost() == 0.0

    def test_record_usage_returns_cost(self):
        tracker = CostTracker()
        # gpt-4o: $2.50/1M input + $10.00/1M output
        cost = tracker.record_usage("gpt-4o", input_tokens=1_000_000, output_tokens=1_000_000)
        assert cost == pytest.approx(12.50)

    def test_record_usage_accumulates_total(self):
        tracker = CostTracker()
        tracker.record_usage("gpt-4o", 500_000, 0)
        tracker.record_usage("gpt-4o", 500_000, 0)
        assert tracker.get_total_cost() == pytest.approx(2.50)

    def test_record_usage_tracks_per_model(self):
        tracker = CostTracker()
        tracker.record_usage("gpt-4o", 1_000_000, 0)
        tracker.record_usage("gpt-4o-mini", 1_000_000, 0)

        usage_gpt4o = tracker.get_model_usage("gpt-4o")
        assert usage_gpt4o is not None
        assert usage_gpt4o.call_count == 1

        usage_mini = tracker.get_model_usage("gpt-4o-mini")
        assert usage_mini is not None
        assert usage_mini.call_count == 1

    def test_record_usage_increments_call_count(self):
        tracker = CostTracker()
        tracker.record_usage("claude-3-haiku", 100, 100)
        tracker.record_usage("claude-3-haiku", 100, 100)
        tracker.record_usage("claude-3-haiku", 100, 100)

        usage = tracker.get_model_usage("claude-3-haiku")
        assert usage is not None
        assert usage.call_count == 3

    def test_record_usage_accumulates_tokens(self):
        tracker = CostTracker()
        tracker.record_usage("gpt-4o", 1000, 500)
        tracker.record_usage("gpt-4o", 2000, 1000)

        usage = tracker.get_model_usage("gpt-4o")
        assert usage.total_input_tokens == 3000
        assert usage.total_output_tokens == 1500

    def test_record_usage_tracks_by_tool(self):
        tracker = CostTracker()
        tracker.record_usage("gpt-4o", 1_000_000, 0, tool_name="search_web")
        tracker.record_usage("gpt-4o", 1_000_000, 0, tool_name="search_web")

        by_tool = tracker.get_cost_by_tool()
        assert "search_web" in by_tool
        assert by_tool["search_web"] == pytest.approx(5.00)

    def test_unknown_model_records_zero_cost(self):
        tracker = CostTracker()
        cost = tracker.record_usage("completely-unknown-model", 1_000_000, 1_000_000)
        assert cost == 0.0
        assert tracker.get_total_cost() == 0.0

    def test_reset_clears_everything(self):
        tracker = CostTracker()
        tracker.record_usage("gpt-4o", 1_000_000, 0, tool_name="my_tool")
        tracker.reset()

        assert tracker.get_total_cost() == 0.0
        assert tracker.get_model_usage("gpt-4o") is None
        assert tracker.get_cost_by_tool() == {}

    def test_get_today_cost_updates(self):
        tracker = CostTracker()
        tracker.record_usage("gpt-4o", 1_000_000, 0)
        assert tracker.get_today_cost() == pytest.approx(2.50)

    def test_get_all_usage_returns_copy(self):
        tracker = CostTracker()
        tracker.record_usage("gpt-4o", 100, 100)
        all_usage = tracker.get_all_usage()
        all_usage.clear()  # mutate copy
        # Original should be unaffected
        assert tracker.get_model_usage("gpt-4o") is not None

    def test_get_stats_structure(self):
        tracker = CostTracker()
        tracker.record_usage("gpt-4o-mini", 1000, 500, tool_name="my_tool")
        stats = tracker.get_stats()

        assert "total_cost" in stats
        assert "today_cost" in stats
        assert "models" in stats
        assert "tools" in stats
        assert "daily" in stats
        assert "gpt-4o-mini" in stats["models"]


# ---------------------------------------------------------------------------
# Budget enforcement
# ---------------------------------------------------------------------------

class TestModelBudgetEnforcement:
    def test_check_budget_allows_under_budget(self):
        config = CostTrackerConfig(model_budgets={"gpt-4o": 10.0})
        tracker = CostTracker(config)
        tracker.record_usage("gpt-4o", 100_000, 0)  # small cost

        allowed, reason = tracker.check_model_budget("gpt-4o")
        assert allowed is True
        assert reason is None

    def test_check_budget_blocks_at_limit(self):
        config = CostTrackerConfig(model_budgets={"gpt-4o": 0.001})
        tracker = CostTracker(config)
        # gpt-4o: $2.50/1M input — 1M tokens exceeds $0.001 budget
        tracker.record_usage("gpt-4o", 1_000_000, 0)

        allowed, reason = tracker.check_model_budget("gpt-4o")
        assert allowed is False
        assert reason is not None
        assert "gpt-4o" in reason

    def test_wildcard_budget_pattern(self):
        config = CostTrackerConfig(model_budgets={"claude-*": 0.001})
        tracker = CostTracker(config)
        # claude-3-haiku: $0.25/1M input — 1M tokens = $0.25 > $0.001
        tracker.record_usage("claude-3-haiku", 1_000_000, 0)

        allowed, reason = tracker.check_model_budget("claude-3-haiku")
        assert allowed is False

    def test_unmatched_model_always_allowed(self):
        config = CostTrackerConfig(model_budgets={"gpt-4o": 1.0})
        tracker = CostTracker(config)
        tracker.record_usage("claude-3-haiku", 1_000_000, 0)

        allowed, reason = tracker.check_model_budget("claude-3-haiku")
        assert allowed is True

    def test_no_usage_always_allowed(self):
        config = CostTrackerConfig(model_budgets={"gpt-4o": 1.0})
        tracker = CostTracker(config)

        allowed, reason = tracker.check_model_budget("gpt-4o")
        assert allowed is True


# ---------------------------------------------------------------------------
# Guard integration: model budget raises ModelBudgetExceededError
# ---------------------------------------------------------------------------

class TestGuardModelBudget:
    def test_model_budget_exceeded_raises_error(self):
        policy = AgentPolicy(model_budgets={"gpt-4o": 0.001})
        guard, sink = _make_guard(policy)

        # First call: record enough cost to exceed budget
        guard.cost_tracker.record_usage("gpt-4o", 1_000_000, 0)

        @guard.protect(tool_name="call_llm", model="gpt-4o")
        def call_llm(prompt: str) -> str:
            return "response"

        with pytest.raises(ModelBudgetExceededError) as exc_info:
            call_llm("hello")

        assert exc_info.value.model == "gpt-4o"
        assert exc_info.value.spent > 0
        assert exc_info.value.budget == pytest.approx(0.001)

    def test_model_budget_not_exceeded_passes_through(self):
        policy = AgentPolicy(model_budgets={"gpt-4o": 100.0})
        guard, sink = _make_guard(policy)

        @guard.protect(tool_name="call_llm", model="gpt-4o")
        def call_llm(prompt: str) -> str:
            return "response"

        result = call_llm("hello")
        assert result == "response"

    def test_model_usage_recorded_after_successful_call(self):
        policy = AgentPolicy()
        guard, _ = _make_guard(policy)

        @guard.protect(tool_name="call_llm", model="gpt-4o-mini")
        def call_llm() -> str:
            return "ok"

        call_llm()
        call_llm()

        usage = guard.cost_tracker.get_model_usage("gpt-4o-mini")
        assert usage is not None
        assert usage.call_count == 2

    def test_model_wildcard_budget_from_policy(self):
        policy = AgentPolicy(model_budgets={"claude-*": 0.001})
        guard, _ = _make_guard(policy)

        # Exceed budget for claude models
        guard.cost_tracker.record_usage("claude-3-haiku", 1_000_000, 0)

        @guard.protect(model="claude-3-haiku")
        def call_claude() -> str:
            return "answer"

        with pytest.raises(ModelBudgetExceededError) as exc_info:
            call_claude()

        assert exc_info.value.model == "claude-3-haiku"

    def test_no_model_param_skips_model_budget_check(self):
        policy = AgentPolicy(model_budgets={"gpt-4o": 0.001})
        guard, _ = _make_guard(policy)

        # Even with exceeded budget in tracker, no model= param means no check
        guard.cost_tracker.record_usage("gpt-4o", 1_000_000, 0)

        @guard.protect(tool_name="some_tool")
        def some_tool() -> str:
            return "ok"

        # Should not raise ModelBudgetExceededError
        result = some_tool()
        assert result == "ok"

    def test_reset_costs_also_resets_tracker(self):
        policy = AgentPolicy(model_budgets={"gpt-4o": 0.001})
        guard, _ = _make_guard(policy)

        guard.cost_tracker.record_usage("gpt-4o", 1_000_000, 0)
        guard.reset_costs()

        @guard.protect(model="gpt-4o")
        def call_llm() -> str:
            return "ok"

        # After reset, budget check should pass
        result = call_llm()
        assert result == "ok"


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------

class TestCountTokens:
    def test_empty_string_returns_zero(self):
        assert count_tokens("") == 0

    def test_nonempty_string_returns_positive(self):
        result = count_tokens("Hello, world!", model_name="gpt-4o")
        assert result > 0

    def test_longer_text_has_more_tokens(self):
        short = count_tokens("Hi", model_name="gpt-4o-mini")
        long = count_tokens("Hello, this is a much longer sentence with many more tokens in it.", model_name="gpt-4o-mini")
        assert long > short

    def test_fallback_estimate_for_unknown_model(self):
        text = "a" * 400  # 400 chars → ~100 tokens
        result = count_tokens(text, model_name="some-unknown-model-without-tiktoken")
        # Without tiktoken, falls back to len // 4 = 100
        assert result == 100


# ---------------------------------------------------------------------------
# estimate_tokens_from_response
# ---------------------------------------------------------------------------

class TestEstimateTokensFromResponse:
    def test_openai_sdk_style_object(self):
        class Usage:
            prompt_tokens = 100
            completion_tokens = 50

        class Response:
            usage = Usage()

        inp, out = estimate_tokens_from_response(Response(), "gpt-4o")
        assert inp == 100
        assert out == 50

    def test_anthropic_sdk_style_object(self):
        class Usage:
            input_tokens = 200
            output_tokens = 80

        class Response:
            usage = Usage()

        inp, out = estimate_tokens_from_response(Response(), "claude-3-5-sonnet")
        assert inp == 200
        assert out == 80

    def test_dict_with_prompt_tokens(self):
        response = {"usage": {"prompt_tokens": 300, "completion_tokens": 120}}
        inp, out = estimate_tokens_from_response(response, "gpt-4o")
        assert inp == 300
        assert out == 120

    def test_dict_with_input_tokens(self):
        response = {"usage": {"input_tokens": 150, "output_tokens": 60}}
        inp, out = estimate_tokens_from_response(response, "claude-3-haiku")
        assert inp == 150
        assert out == 60

    def test_unknown_format_returns_zeros(self):
        inp, out = estimate_tokens_from_response({"data": "something"}, "gpt-4o")
        assert inp == 0
        assert out == 0

    def test_none_response_returns_zeros(self):
        inp, out = estimate_tokens_from_response(None, "gpt-4o")
        assert inp == 0
        assert out == 0
