"""LlamaIndex integration for AgentSentinel.

LlamaIndex is a data framework for LLM applications with tools, agents, and RAG.
This integration wraps LlamaIndex tools and query engines with AgentSentinel protection.

Usage::

    from llama_index.core.tools import FunctionTool
    from llama_index.core.agent import ReActAgent
    from agentsentinel import AgentPolicy, AgentGuard
    from agentsentinel.integrations.llamaindex import protect_agent, LlamaIndexGuard

    policy = AgentPolicy(daily_budget=10.0)
    guard = AgentGuard(policy)

    # Option 1: Protect an agent
    agent = ReActAgent.from_tools(tools, llm=llm)
    protected_agent = protect_agent(agent, guard=guard)

    # Option 2: Protect individual tools
    llama_guard = LlamaIndexGuard(guard)

    @llama_guard.tool
    def query_database(query: str) -> str:
        return db.query(query)

    # Option 3: Wrap existing FunctionTool
    tool = FunctionTool.from_defaults(fn=my_func)
    protected_tool = llama_guard.wrap_tool(tool)

.. note::
    This module does **not** import ``llama_index`` at the module level, so
    ``agentsentinel`` has no hard dependency on LlamaIndex.
"""

from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable, List, Optional, TypeVar, Union

from ..guard import AgentGuard
from ..policy import AgentPolicy

F = TypeVar("F", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# Core guard class
# ---------------------------------------------------------------------------


class LlamaIndexGuard:
    """Wraps LlamaIndex tools and agents with :class:`.AgentGuard` policy enforcement.

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
        from agentsentinel.integrations.llamaindex import LlamaIndexGuard

        policy = AgentPolicy(daily_budget=10.0, model_budgets={"gpt-4o": 5.0})
        llama_guard = LlamaIndexGuard(AgentGuard(policy))

        @llama_guard.tool(model="gpt-4o")
        def query_knowledge_base(query: str) -> str:
            return kb.query(query)
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
        """Decorator to protect a function used as a LlamaIndex tool.

        Can be used with or without arguments::

            @llama_guard.tool
            def search_web(query: str) -> str:
                return search(query)

            @llama_guard.tool(model="gpt-4o", cost=0.02)
            def summarize(text: str) -> str:
                return summarize(text)

        Parameters
        ----------
        func:
            The function to protect (when used without parentheses).
        name:
            Override tool name (defaults to function name).
        cost:
            Fixed cost per call (USD).
        model:
            Model name for per-model budget tracking.
        """
        def decorator(f: F) -> F:
            tool_name = name or f.__name__
            return self._guard.protect(f, tool_name=tool_name, cost=cost, model=model)  # type: ignore[return-value]

        if func is not None:
            return decorator(func)
        return decorator

    def wrap_tool(self, tool: Any, name: Optional[str] = None) -> Any:
        """Wrap a LlamaIndex tool (``FunctionTool``, ``QueryEngineTool``, etc.).

        Parameters
        ----------
        tool:
            A LlamaIndex ``BaseTool`` instance.
        name:
            Override tool name (defaults to ``tool.metadata.name``).

        Returns
        -------
        The same tool object with its ``call`` (and ``acall``) patched.
        """
        try:
            from llama_index.core.tools import BaseTool  # type: ignore[import]
        except ImportError:
            return tool

        if not isinstance(tool, BaseTool):
            return tool

        tool_name = name or getattr(getattr(tool, "metadata", None), "name", None) or tool.__class__.__name__
        original_call = tool.call

        @functools.wraps(original_call)
        def protected_call(*args: Any, **kwargs: Any) -> Any:
            protected = self._guard.protect(
                lambda *a, **kw: original_call(*a, **kw),
                tool_name=tool_name,
            )
            return protected(*args, **kwargs)

        tool.call = protected_call  # type: ignore[method-assign]

        # Wrap async variant if present.
        if hasattr(tool, "acall"):
            original_acall = tool.acall

            @functools.wraps(original_acall)
            async def protected_acall(*args: Any, **kwargs: Any) -> Any:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None,
                    lambda: protected_call(*args, **kwargs),
                )

            tool.acall = protected_acall  # type: ignore[method-assign]

        return tool

    def wrap_tools(self, tools: List[Any]) -> List[Any]:
        """Wrap multiple LlamaIndex tools.

        Parameters
        ----------
        tools:
            List of LlamaIndex ``BaseTool`` instances.

        Returns
        -------
        The same list with each tool wrapped.
        """
        return [self.wrap_tool(t) for t in tools]

    def wrap_query_engine(self, engine: Any, name: str = "query_engine") -> Any:
        """Wrap a LlamaIndex ``QueryEngine`` with protection.

        Parameters
        ----------
        engine:
            A LlamaIndex query engine instance.
        name:
            Tool name for policy matching and audit logs.

        Returns
        -------
        The same engine with its ``query`` (and ``aquery``) method patched.
        """
        original_query = engine.query

        @functools.wraps(original_query)
        def protected_query(*args: Any, **kwargs: Any) -> Any:
            protected = self._guard.protect(
                lambda *a, **kw: original_query(*a, **kw),
                tool_name=name,
            )
            return protected(*args, **kwargs)

        engine.query = protected_query  # type: ignore[method-assign]

        if hasattr(engine, "aquery"):
            original_aquery = engine.aquery

            @functools.wraps(original_aquery)
            async def protected_aquery(*args: Any, **kwargs: Any) -> Any:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None,
                    lambda: protected_query(*args, **kwargs),
                )

            engine.aquery = protected_aquery  # type: ignore[method-assign]

        return engine


# ---------------------------------------------------------------------------
# Convenience one-liners
# ---------------------------------------------------------------------------


def protect_agent(
    agent: Any,
    *,
    guard: Optional[AgentGuard] = None,
    policy: Optional[AgentPolicy] = None,
) -> Any:
    """Protect a LlamaIndex agent (``ReActAgent``, ``OpenAIAgent``, etc.).

    Parameters
    ----------
    agent:
        A LlamaIndex agent instance.
    guard:
        Pre-configured :class:`.AgentGuard`.
    policy:
        :class:`.AgentPolicy` used to create a guard when *guard* is ``None``.

    Returns
    -------
    The same agent with its tools wrapped.
    """
    llama_guard = LlamaIndexGuard(guard=guard, policy=policy)

    if hasattr(agent, "_tools"):
        agent._tools = llama_guard.wrap_tools(agent._tools)
    elif hasattr(agent, "tools"):
        agent.tools = llama_guard.wrap_tools(agent.tools)

    return agent


def protect_query_engine(
    engine: Any,
    *,
    guard: Optional[AgentGuard] = None,
    policy: Optional[AgentPolicy] = None,
    name: str = "query_engine",
) -> Any:
    """Protect a LlamaIndex ``QueryEngine``.

    Parameters
    ----------
    engine:
        A LlamaIndex query engine instance.
    guard:
        Pre-configured :class:`.AgentGuard`.
    policy:
        :class:`.AgentPolicy` used to create a guard when *guard* is ``None``.
    name:
        Tool name for policy matching and audit logs.

    Returns
    -------
    The same engine with its ``query`` method wrapped.
    """
    llama_guard = LlamaIndexGuard(guard=guard, policy=policy)
    return llama_guard.wrap_query_engine(engine, name=name)
