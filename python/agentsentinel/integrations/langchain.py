# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""LangChain integration for AgentSentinel.

Wraps every tool in a LangChain ``AgentExecutor`` (or a bare list of tools)
with :class:`.AgentGuard` policy enforcement — budget caps, rate limits,
approval gates, PII detection, and audit logging.

Usage::

    from langchain.agents import AgentExecutor, create_openai_tools_agent
    from agentsentinel import AgentGuard, AgentPolicy
    from agentsentinel.integrations.langchain import protect_langchain_agent

    policy = AgentPolicy(daily_budget=5.0, require_approval=["send_email"])
    guard  = AgentGuard(policy=policy)

    executor = create_openai_tools_agent(llm, tools, prompt)
    protected = protect_langchain_agent(executor, guard)
    protected.invoke({"input": "..."})

.. note::
    This module imports from ``langchain`` at call-time so that
    ``agentsentinel`` itself has **no hard dependency** on LangChain.
    Import errors surface only when you actually try to use the integration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

from ..guard import AgentGuard
from ..policy import AgentPolicy

if TYPE_CHECKING:  # pragma: no cover
    # Keep type hints available without a hard runtime dep on langchain.
    from langchain.tools import BaseTool


# ---------------------------------------------------------------------------
# Core guard class
# ---------------------------------------------------------------------------

class LangChainGuard:
    """Wraps every tool in a LangChain agent / tool-list with :class:`.AgentGuard`.

    Parameters
    ----------
    guard:
        A pre-configured :class:`.AgentGuard` instance.  Create one with
        :class:`.AgentPolicy` to set budgets, rate limits, etc.

    Example
    -------
    ::

        from agentsentinel import AgentGuard, AgentPolicy
        from agentsentinel.integrations.langchain import LangChainGuard

        policy = AgentPolicy(daily_budget=5.0)
        lc_guard = LangChainGuard(AgentGuard(policy))

        # Wrap a list of LangChain tools
        protected_tools = lc_guard.wrap_tools(my_tools)

        # Or wrap an entire AgentExecutor in-place
        lc_guard.protect_executor(executor)
    """

    def __init__(self, guard: AgentGuard) -> None:
        from agentsentinel.licensing import require_feature
        require_feature("integrations")
        self.guard = guard

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def wrap_tools(self, tools: List["BaseTool"]) -> List["BaseTool"]:
        """Return *tools* with every tool's ``run`` / ``arun`` wrapped.

        The original tool objects are **mutated in-place** and also returned
        for convenience.  Use :meth:`protect_executor` to wrap all tools
        attached to an :class:`~langchain.agents.AgentExecutor`.
        """
        for tool in tools:
            self._wrap_single_tool(tool)
        return tools

    def protect_executor(self, executor: Any) -> Any:
        """Wrap every tool inside a LangChain ``AgentExecutor`` in-place.

        Parameters
        ----------
        executor:
            A ``langchain.agents.AgentExecutor`` instance.

        Returns
        -------
        The same executor object (mutated in-place) for chaining.
        """
        tool_list = getattr(executor, "tools", None)
        if tool_list is None:
            raise TypeError(
                "Expected an AgentExecutor with a .tools attribute. "
                f"Got: {type(executor).__name__}"
            )
        self.wrap_tools(tool_list)
        return executor

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _wrap_single_tool(self, tool: "BaseTool") -> None:
        """Patch *tool*.run and *tool*.arun with guard wrappers."""
        original_run = tool.run  # bound method

        guarded_run = self.guard.protect(
            lambda *a, **kw: original_run(*a, **kw),
            tool_name=tool.name,
        )

        # Patch synchronous run
        tool.run = guarded_run  # type: ignore[method-assign]

        # Patch async run if present
        _orig_arun = getattr(tool, "arun", None)
        if _orig_arun is not None:
            import asyncio

            async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
                # Run the (now-guarded) sync version inside the running loop.
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None,
                    lambda: guarded_run(*args, **kwargs),
                )

            tool.arun = _async_wrapper  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Convenience one-liner
# ---------------------------------------------------------------------------

def protect_langchain_agent(
    executor_or_tools: Any,
    guard: Optional[AgentGuard] = None,
    *,
    policy: Optional[AgentPolicy] = None,
) -> Any:
    """One-liner: wrap every tool in *executor_or_tools* with policy enforcement.

    Parameters
    ----------
    executor_or_tools:
        Either a ``langchain.agents.AgentExecutor`` **or** a plain
        ``list`` of ``BaseTool`` instances.
    guard:
        Pre-configured :class:`.AgentGuard`.  If ``None``, *policy* must be
        supplied and a new guard is created automatically.
    policy:
        :class:`.AgentPolicy` used to create a guard when *guard* is ``None``.
        Ignored when *guard* is provided.

    Returns
    -------
    The same object passed in (mutated in-place) for easy chaining::

        executor = protect_langchain_agent(executor, policy=AgentPolicy(daily_budget=5.0))
        executor.invoke({"input": "..."})

    Raises
    ------
    ValueError:
        When neither *guard* nor *policy* is supplied.
    """
    if guard is None:
        if policy is None:
            raise ValueError("Supply either 'guard' or 'policy'.")
        guard = AgentGuard(policy=policy)

    lc_guard = LangChainGuard(guard)

    if isinstance(executor_or_tools, list):
        return lc_guard.wrap_tools(executor_or_tools)
    return lc_guard.protect_executor(executor_or_tools)
