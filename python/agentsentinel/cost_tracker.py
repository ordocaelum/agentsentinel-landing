"""Cost tracking and token counting for AgentSentinel."""

from __future__ import annotations

import fnmatch
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from .pricing import calculate_cost, get_model_pricing


@dataclass
class ModelUsage:
    """Track usage for a specific model."""

    model_name: str
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    call_count: int = 0
    first_call: Optional[float] = None
    last_call: Optional[float] = None


@dataclass
class CostTrackerConfig:
    """Configuration for cost tracking."""

    enabled: bool = True
    track_tokens: bool = True
    track_by_model: bool = True
    track_by_tool: bool = True

    # Per-model budget limits (e.g., {"gpt-4o": 5.0, "claude-*": 3.0})
    model_budgets: Dict[str, float] = field(default_factory=dict)

    # Custom token counter (for models not using tiktoken)
    custom_token_counter: Optional[Callable[[str, str], int]] = None


class CostTracker:
    """Tracks costs across all model calls."""

    def __init__(self, config: Optional[CostTrackerConfig] = None) -> None:
        self.config = config or CostTrackerConfig()
        self._model_usage: Dict[str, ModelUsage] = {}
        self._tool_costs: Dict[str, float] = {}
        self._daily_costs: Dict[str, float] = {}  # date -> cost
        self._total_cost: float = 0.0
        self._start_time: float = time.time()

    def record_usage(
        self,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        tool_name: Optional[str] = None,
    ) -> float:
        """Record token usage and return the cost."""
        cost = calculate_cost(model_name, input_tokens, output_tokens)
        now = time.time()

        # Track by model
        if model_name not in self._model_usage:
            self._model_usage[model_name] = ModelUsage(model_name=model_name)

        usage = self._model_usage[model_name]
        usage.total_input_tokens += input_tokens
        usage.total_output_tokens += output_tokens
        usage.total_cost += cost
        usage.call_count += 1
        if usage.first_call is None:
            usage.first_call = now
        usage.last_call = now

        # Track by tool
        if tool_name and self.config.track_by_tool:
            self._tool_costs[tool_name] = self._tool_costs.get(tool_name, 0.0) + cost

        # Track daily
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._daily_costs[today] = self._daily_costs.get(today, 0.0) + cost

        self._total_cost += cost
        return cost

    def check_model_budget(self, model_name: str) -> tuple[bool, Optional[str]]:
        """Check if model is within budget. Returns (allowed, reason)."""
        for pattern, budget in self.config.model_budgets.items():
            if fnmatch.fnmatch(model_name.lower(), pattern.lower()):
                usage = self._model_usage.get(model_name)
                if usage and usage.total_cost >= budget:
                    return (
                        False,
                        f"Model {model_name} exceeded budget: "
                        f"${usage.total_cost:.4f} >= ${budget:.2f}",
                    )

        return True, None

    def get_model_usage(self, model_name: str) -> Optional[ModelUsage]:
        """Get usage stats for a specific model."""
        return self._model_usage.get(model_name)

    def get_all_usage(self) -> Dict[str, ModelUsage]:
        """Get usage stats for all models."""
        return self._model_usage.copy()

    def get_today_cost(self) -> float:
        """Get total cost for today."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._daily_costs.get(today, 0.0)

    def get_total_cost(self) -> float:
        """Get total cost since tracking started."""
        return self._total_cost

    def get_cost_by_tool(self) -> Dict[str, float]:
        """Get costs broken down by tool."""
        return self._tool_costs.copy()

    def get_stats(self) -> dict:
        """Get comprehensive stats for dashboard."""
        return {
            "total_cost": self._total_cost,
            "today_cost": self.get_today_cost(),
            "models": {
                name: {
                    "input_tokens": u.total_input_tokens,
                    "output_tokens": u.total_output_tokens,
                    "cost": u.total_cost,
                    "calls": u.call_count,
                }
                for name, u in self._model_usage.items()
            },
            "tools": self._tool_costs,
            "daily": self._daily_costs,
        }

    def reset(self) -> None:
        """Reset all tracking."""
        self._model_usage.clear()
        self._tool_costs.clear()
        self._daily_costs.clear()
        self._total_cost = 0.0
        self._start_time = time.time()


# ═══════════════════════════════════════════════════════════════════════════════
# Token Counting
# ═══════════════════════════════════════════════════════════════════════════════

def count_tokens(text: str, model_name: str = "gpt-4o") -> int:
    """
    Count tokens for a given text and model.

    Uses tiktoken for OpenAI models when available, falls back to a
    character-based estimate (~4 chars per token) for other models.
    """
    if not text:
        return 0

    # Try tiktoken for OpenAI models
    try:
        import tiktoken

        if "gpt-4o" in model_name or "gpt-4-turbo" in model_name:
            enc = tiktoken.get_encoding("o200k_base")
        elif "gpt-4" in model_name or "gpt-3.5" in model_name:
            enc = tiktoken.get_encoding("cl100k_base")
        else:
            enc = tiktoken.get_encoding("cl100k_base")

        return len(enc.encode(text))
    except ImportError:
        pass

    # Fallback: estimate based on characters (~4 chars per token for English)
    return len(text) // 4


def estimate_tokens_from_response(response: Any, model_name: str) -> tuple[int, int]:
    """
    Try to extract token counts from an API response.

    Returns (input_tokens, output_tokens).
    """
    # OpenAI / dict format
    if isinstance(response, dict):
        usage = response.get("usage", {})
        if usage:
            return (
                usage.get("prompt_tokens", usage.get("input_tokens", 0)),
                usage.get("completion_tokens", usage.get("output_tokens", 0)),
            )

    # Object with .usage attribute (OpenAI SDK or Anthropic SDK)
    if hasattr(response, "usage"):
        usage = response.usage
        # OpenAI SDK
        if hasattr(usage, "prompt_tokens") and hasattr(usage, "completion_tokens"):
            return usage.prompt_tokens, usage.completion_tokens
        # Anthropic SDK
        if hasattr(usage, "input_tokens") and hasattr(usage, "output_tokens"):
            return usage.input_tokens, usage.output_tokens

    return 0, 0
