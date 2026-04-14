"""CrewAI integration for AgentSentinel.

CrewAI is a framework for orchestrating role-playing AI agents.
This integration wraps CrewAI tools and agent actions with AgentSentinel protection.

Usage::

    from crewai import Agent, Task, Crew
    from agentsentinel import AgentPolicy, AgentGuard
    from agentsentinel.integrations.crewai import protect_crew, CrewAIGuard

    policy = AgentPolicy(daily_budget=10.0, require_approval=["send_email"])
    guard = AgentGuard(policy)

    # Option 1: Protect an entire Crew
    crew = Crew(agents=[...], tasks=[...])
    protected_crew = protect_crew(crew, guard=guard)
    result = protected_crew.kickoff()

    # Option 2: Protect individual tools
    crewai_guard = CrewAIGuard(guard)

    @crewai_guard.tool
    def search_database(query: str) -> str:
        return db.search(query)

.. note::
    This module does **not** import ``crewai`` at the module level, so
    ``agentsentinel`` has no hard dependency on CrewAI.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

from ..guard import AgentGuard
from ..policy import AgentPolicy

F = TypeVar("F", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# Core guard class
# ---------------------------------------------------------------------------


class CrewAIGuard:
    """Wraps CrewAI tools and agents with :class:`.AgentGuard` policy enforcement.

    Parameters
    ----------
    guard:
        A pre-configured :class:`.AgentGuard` instance.
    policy:
        :class:`.AgentPolicy` used to create a guard when *guard* is ``None``.
        Ignored when *guard* is provided.

    Example
    -------
    ::

        from agentsentinel import AgentGuard, AgentPolicy
        from agentsentinel.integrations.crewai import CrewAIGuard

        policy = AgentPolicy(daily_budget=5.0, require_approval=["send_email"])
        crewai_guard = CrewAIGuard(AgentGuard(policy))

        @crewai_guard.tool(cost=0.01)
        def search_web(query: str) -> str:
            return f"Results for {query}"
    """

    def __init__(
        self,
        guard: Optional[AgentGuard] = None,
        policy: Optional[AgentPolicy] = None,
    ) -> None:
        if guard is not None:
            self._guard = guard
        elif policy is not None:
            self._guard = AgentGuard(policy)
        else:
            self._guard = AgentGuard(AgentPolicy())

    @property
    def guard(self) -> AgentGuard:
        """Access the underlying :class:`.AgentGuard`."""
        return self._guard

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tool(
        self,
        func: Optional[F] = None,
        *,
        name: Optional[str] = None,
        cost: Optional[float] = None,
        model: Optional[str] = None,
    ) -> Union[F, Callable[[F], F]]:
        """Decorator to protect a CrewAI tool function.

        Can be used with or without arguments::

            @crewai_guard.tool
            def search_web(query: str) -> str:
                return search(query)

            @crewai_guard.tool(cost=0.05, model="gpt-4o")
            def analyze_data(data: str) -> str:
                return analyze(data)

        Parameters
        ----------
        func:
            The tool function to protect (when used without parentheses).
        name:
            Override tool name (defaults to function name).
        cost:
            Fixed cost for this tool (USD).
        model:
            Model name for cost tracking.

        Returns
        -------
        Protected tool function.
        """
        def decorator(f: F) -> F:
            tool_name = name or f.__name__
            return self._guard.protect(f, tool_name=tool_name, cost=cost, model=model)  # type: ignore[return-value]

        if func is not None:
            return decorator(func)
        return decorator

    def protect_tools(self, tools: List[Any]) -> List[Any]:
        """Protect a list of CrewAI tool objects.

        Parameters
        ----------
        tools:
            List of CrewAI ``BaseTool`` instances.

        Returns
        -------
        The same list with each tool's ``_run`` method wrapped.
        """
        return [self._wrap_tool(tool) for tool in tools]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _wrap_tool(self, tool: Any) -> Any:
        """Wrap a single CrewAI tool's ``_run`` method."""
        try:
            from crewai.tools import BaseTool  # type: ignore[import]
        except ImportError:
            # CrewAI not installed — return as-is.
            return tool

        if not isinstance(tool, BaseTool):
            return tool

        original_run = tool._run
        tool_name = getattr(tool, "name", tool.__class__.__name__)

        @functools.wraps(original_run)
        def protected_run(*args: Any, **kwargs: Any) -> Any:
            protected = self._guard.protect(
                lambda *a, **kw: original_run(*a, **kw),
                tool_name=tool_name,
            )
            return protected(*args, **kwargs)

        tool._run = protected_run
        return tool


# ---------------------------------------------------------------------------
# Convenience one-liners
# ---------------------------------------------------------------------------


def protect_crew(
    crew: Any,
    *,
    guard: Optional[AgentGuard] = None,
    policy: Optional[AgentPolicy] = None,
) -> Any:
    """Protect an entire CrewAI ``Crew`` by wrapping all agent tools.

    Parameters
    ----------
    crew:
        A ``crewai.Crew`` instance.
    guard:
        Pre-configured :class:`.AgentGuard`.
    policy:
        :class:`.AgentPolicy` used to create a guard when *guard* is ``None``.

    Returns
    -------
    The same ``Crew`` instance with every agent's tools wrapped.

    Example
    -------
    ::

        from agentsentinel import AgentPolicy
        from agentsentinel.integrations.crewai import protect_crew

        crew = Crew(agents=[researcher, writer], tasks=[research_task, write_task])
        protected_crew = protect_crew(crew, policy=AgentPolicy(daily_budget=5.0))
        result = protected_crew.kickoff()
    """
    crewai_guard = CrewAIGuard(guard=guard, policy=policy)

    for agent in getattr(crew, "agents", []):
        if hasattr(agent, "tools") and agent.tools:
            agent.tools = crewai_guard.protect_tools(agent.tools)

    return crew


def protect_agent(
    agent: Any,
    *,
    guard: Optional[AgentGuard] = None,
    policy: Optional[AgentPolicy] = None,
) -> Any:
    """Protect a single CrewAI ``Agent`` by wrapping its tools.

    Parameters
    ----------
    agent:
        A ``crewai.Agent`` instance.
    guard:
        Pre-configured :class:`.AgentGuard`.
    policy:
        :class:`.AgentPolicy` used to create a guard when *guard* is ``None``.

    Returns
    -------
    The same ``Agent`` with its tools wrapped.
    """
    crewai_guard = CrewAIGuard(guard=guard, policy=policy)

    if hasattr(agent, "tools") and agent.tools:
        agent.tools = crewai_guard.protect_tools(agent.tools)

    return agent
