# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Anthropic Claude Tools integration for AgentSentinel.

Wraps Anthropic's ``tool_use`` feature with AgentSentinel protection.

Usage::

    import anthropic
    from agentsentinel import AgentPolicy, AgentGuard
    from agentsentinel.integrations.anthropic_tools import (
        AnthropicToolsGuard,
        protect_tool_handlers,
    )

    client = anthropic.Anthropic()
    policy = AgentPolicy(daily_budget=10.0, model_budgets={"claude-3-5-sonnet": 5.0})
    guard = AgentGuard(policy)

    # Define tool handlers
    def get_weather(location: str) -> str:
        return f"Weather in {location}: Sunny, 72°F"

    def search_web(query: str) -> str:
        return f"Search results for: {query}"

    # Protect handlers
    handlers = protect_tool_handlers(
        {"get_weather": get_weather, "search_web": search_web},
        guard=guard,
        model="claude-3-5-sonnet",
    )

    # In your message loop, handle tool_use blocks:
    for block in response.content:
        if block.type == "tool_use":
            result = handlers[block.name](**block.input)

.. note::
    This module does **not** import ``anthropic`` at the module level, so
    ``agentsentinel`` has no hard dependency on the Anthropic SDK.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, TypeVar

from ..guard import AgentGuard
from ..policy import AgentPolicy

F = TypeVar("F", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# Core guard class
# ---------------------------------------------------------------------------


class AnthropicToolsGuard:
    """Wraps Anthropic Claude ``tool_use`` handlers with :class:`.AgentGuard`.

    Parameters
    ----------
    guard:
        A pre-configured :class:`.AgentGuard` instance.
    policy:
        :class:`.AgentPolicy` used to create a guard when *guard* is ``None``.
        Ignored when *guard* is provided.
    default_model:
        Default Claude model name used for cost tracking.

    Example
    -------
    ::

        from agentsentinel import AgentGuard, AgentPolicy
        from agentsentinel.integrations.anthropic_tools import AnthropicToolsGuard

        policy = AgentPolicy(daily_budget=15.0, model_budgets={"claude-3-5-sonnet": 10.0})
        anthropic_guard = AnthropicToolsGuard(AgentGuard(policy), default_model="claude-3-5-sonnet")

        protected = anthropic_guard.protect_handlers(
            {"get_weather": get_weather, "search_web": search_web}
        )
    """

    def __init__(
        self,
        guard: Optional[AgentGuard] = None,
        policy: Optional[AgentPolicy] = None,
        default_model: str = "claude-3-5-sonnet",
    ) -> None:
        from agentsentinel.licensing import require_feature
        require_feature("integrations")
        if guard is not None:
            self._guard = guard
        elif policy is not None:
            self._guard = AgentGuard(policy)
        else:
            self._guard = AgentGuard(AgentPolicy())
        self._default_model = default_model

    @property
    def guard(self) -> AgentGuard:
        """Access the underlying :class:`.AgentGuard`."""
        return self._guard

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def protect_handler(
        self,
        func: F,
        name: Optional[str] = None,
        cost: Optional[float] = None,
        model: Optional[str] = None,
    ) -> F:
        """Protect a single tool handler function.

        Parameters
        ----------
        func:
            The handler callable to protect.
        name:
            Override the tool name (defaults to ``func.__name__``).
        cost:
            Explicit cost per invocation (USD).
        model:
            Model name for per-model budget tracking.

        Returns
        -------
        Protected callable with the same signature.
        """
        tool_name = name or func.__name__
        model_name = model or self._default_model
        return self._guard.protect(func, tool_name=tool_name, cost=cost, model=model_name)  # type: ignore[return-value]

    def protect_handlers(
        self,
        handlers: Dict[str, Callable[..., Any]],
        costs: Optional[Dict[str, float]] = None,
        models: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Callable[..., Any]]:
        """Return a new dict with every handler protected.

        Parameters
        ----------
        handlers:
            Mapping of tool names to handler callables.
        costs:
            Optional per-tool cost overrides ``{name: cost_usd}``.
        models:
            Optional per-tool model name overrides.

        Returns
        -------
        A **new** dict with the same keys but guarded callables as values.
        """
        costs = costs or {}
        models = models or {}

        protected: Dict[str, Callable[..., Any]] = {}
        for tool_name, func in handlers.items():
            protected[tool_name] = self.protect_handler(
                func,
                name=tool_name,
                cost=costs.get(tool_name),
                model=models.get(tool_name, self._default_model),
            )
        return protected

    def handle_tool_use(
        self,
        tool_use_block: Any,
        handlers: Dict[str, Callable[..., Any]],
    ) -> Dict[str, Any]:
        """Handle a single ``tool_use`` block from Claude's response.

        Parameters
        ----------
        tool_use_block:
            A ``tool_use`` content block from the API response.
        handlers:
            Protected handler functions (output of :meth:`protect_handlers`).

        Returns
        -------
        A ``tool_result`` dict for use in the next ``messages`` request.
        """
        tool_name = tool_use_block.name
        tool_input = tool_use_block.input
        tool_use_id = tool_use_block.id

        try:
            if tool_name in handlers:
                result = handlers[tool_name](**tool_input)
                is_error = False
            else:
                result = f"Unknown tool: {tool_name}"
                is_error = True
        except Exception as exc:
            result = str(exc)
            is_error = True

        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": str(result),
            "is_error": is_error,
        }

    def handle_tool_uses(
        self,
        response: Any,
        handlers: Dict[str, Callable[..., Any]],
    ) -> List[Dict[str, Any]]:
        """Handle all ``tool_use`` blocks in an Anthropic API response.

        Parameters
        ----------
        response:
            Full API response from ``client.messages.create()``.
        handlers:
            Protected handler functions.

        Returns
        -------
        List of ``tool_result`` dicts for the next ``messages`` request.
        """
        results: List[Dict[str, Any]] = []
        for block in response.content:
            if hasattr(block, "type") and block.type == "tool_use":
                results.append(self.handle_tool_use(block, handlers))
        return results


# ---------------------------------------------------------------------------
# Convenience one-liner
# ---------------------------------------------------------------------------


def protect_tool_handlers(
    handlers: Dict[str, Callable[..., Any]],
    *,
    guard: Optional[AgentGuard] = None,
    policy: Optional[AgentPolicy] = None,
    costs: Optional[Dict[str, float]] = None,
    models: Optional[Dict[str, str]] = None,
    model: str = "claude-3-5-sonnet",
) -> Dict[str, Callable[..., Any]]:
    """One-liner: protect every handler in *handlers* for Anthropic tool_use.

    Parameters
    ----------
    handlers:
        Mapping of tool names to handler callables.
    guard:
        Pre-configured :class:`.AgentGuard`.  If ``None``, *policy* must be
        supplied and a new guard is created automatically.
    policy:
        :class:`.AgentPolicy` used to create a guard when *guard* is ``None``.
        Ignored when *guard* is provided.
    costs:
        Optional per-tool cost overrides.
    models:
        Optional per-tool model name overrides.
    model:
        Default model for cost tracking.

    Returns
    -------
    A **new** dict with the same keys but every callable wrapped.

    Raises
    ------
    ValueError:
        When neither *guard* nor *policy* is supplied.

    Example
    -------
    ::

        from agentsentinel import AgentPolicy
        from agentsentinel.integrations.anthropic_tools import protect_tool_handlers

        protected = protect_tool_handlers(
            {"get_weather": get_weather, "search_web": search_web},
            policy=AgentPolicy(daily_budget=15.0),
            model="claude-3-5-sonnet",
        )
    """
    if guard is None and policy is None:
        raise ValueError("Supply either 'guard' or 'policy'.")

    anthropic_guard = AnthropicToolsGuard(guard=guard, policy=policy, default_model=model)
    return anthropic_guard.protect_handlers(handlers, costs=costs, models=models)
