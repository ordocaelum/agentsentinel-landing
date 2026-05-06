# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""AutoGen integration for AgentSentinel.

Wraps AutoGen function maps (and individual callables) with
:class:`.AgentGuard` policy enforcement — budget caps, rate limits,
approval gates, PII detection, and audit logging.

Usage::

    from autogen import AssistantAgent, UserProxyAgent
    from agentsentinel import AgentGuard, AgentPolicy
    from agentsentinel.integrations.autogen import AutoGenGuard

    policy = AgentPolicy(daily_budget=5.0, require_approval=["execute_code"])
    ag_guard = AutoGenGuard(AgentGuard(policy))

    # Decorate individual functions
    @ag_guard.register_function(tool_name="run_sql", cost=0.01)
    def run_sql(query: str) -> str:
        ...

    # Or wrap an existing function_map in one call
    protected_map = ag_guard.protect_function_map(
        {"run_sql": run_sql, "send_email": send_email}
    )

.. note::
    This module does **not** import ``autogen`` at the module level, so
    ``agentsentinel`` has no hard dependency on AutoGen.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Dict, Optional

from ..guard import AgentGuard
from ..policy import AgentPolicy

# ---------------------------------------------------------------------------
# Core guard class
# ---------------------------------------------------------------------------

class AutoGenGuard:
    """Wraps AutoGen callables / function-maps with :class:`.AgentGuard`.

    Parameters
    ----------
    guard:
        A pre-configured :class:`.AgentGuard` instance.

    Example
    -------
    ::

        from agentsentinel import AgentGuard, AgentPolicy
        from agentsentinel.integrations.autogen import AutoGenGuard

        policy   = AgentPolicy(daily_budget=2.0, rate_limits={"*": "20/min"})
        ag_guard = AutoGenGuard(AgentGuard(policy))

        @ag_guard.register_function(cost=0.05)
        def search_web(query: str) -> str:
            return f"Results for {query}"

        function_map = ag_guard.protect_function_map(
            {"search_web": search_web, "send_email": send_email}
        )
    """

    def __init__(self, guard: AgentGuard) -> None:
        from agentsentinel.licensing import require_feature
        require_feature("integrations")
        self.guard = guard

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_function(
        self,
        func: Optional[Callable] = None,
        *,
        tool_name: Optional[str] = None,
        cost: Optional[float] = None,
    ) -> Callable:
        """Decorator that wraps a callable with full policy enforcement.

        Can be used with or without arguments::

            @ag_guard.register_function
            def my_tool(x: str) -> str: ...

            @ag_guard.register_function(tool_name="my_tool", cost=0.02)
            def my_tool(x: str) -> str: ...

        Parameters
        ----------
        func:
            The callable to protect (when used without parentheses).
        tool_name:
            Override the name used for policy matching.  Defaults to
            ``func.__name__``.
        cost:
            Explicit cost per call (USD).
        """
        def decorator(fn: Callable) -> Callable:
            protected = self.guard.protect(fn, tool_name=tool_name, cost=cost)

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return protected(*args, **kwargs)

            return wrapper

        if func is not None:
            return decorator(func)
        return decorator

    def protect_function_map(
        self,
        function_map: Dict[str, Callable],
        *,
        cost_map: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Callable]:
        """Return a new function-map with every callable wrapped.

        Parameters
        ----------
        function_map:
            AutoGen-style ``{name: callable}`` dict (e.g. from
            ``UserProxyAgent(function_map=...)``.
        cost_map:
            Optional per-tool cost overrides ``{tool_name: cost_usd}``.
            Tools not in *cost_map* default to ``0.0``.

        Returns
        -------
        A new ``dict`` with the same keys but guarded callables as values.
        """
        cost_map = cost_map or {}
        protected: Dict[str, Callable] = {}
        for name, fn in function_map.items():
            cost = cost_map.get(name)
            protected[name] = self.guard.protect(fn, tool_name=name, cost=cost)
        return protected


# ---------------------------------------------------------------------------
# Convenience one-liner
# ---------------------------------------------------------------------------

def protect_function_map(
    function_map: Dict[str, Callable],
    guard: Optional[AgentGuard] = None,
    *,
    policy: Optional[AgentPolicy] = None,
    cost_map: Optional[Dict[str, float]] = None,
) -> Dict[str, Callable]:
    """One-liner: wrap every callable in *function_map* with policy enforcement.

    Parameters
    ----------
    function_map:
        AutoGen-style ``{name: callable}`` dict.
    guard:
        Pre-configured :class:`.AgentGuard`.  If ``None``, *policy* must be
        supplied and a new guard is created automatically.
    policy:
        :class:`.AgentPolicy` used to create a guard when *guard* is ``None``.
        Ignored when *guard* is provided.
    cost_map:
        Optional ``{tool_name: cost_usd}`` overrides.

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
        from agentsentinel.integrations.autogen import protect_function_map

        safe_map = protect_function_map(
            {"run_sql": run_sql, "send_email": send_email},
            policy=AgentPolicy(daily_budget=5.0),
        )
    """
    if guard is None:
        if policy is None:
            raise ValueError("Supply either 'guard' or 'policy'.")
        guard = AgentGuard(policy=policy)

    ag_guard = AutoGenGuard(guard)
    return ag_guard.protect_function_map(function_map, cost_map=cost_map)
