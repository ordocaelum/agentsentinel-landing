"""OpenAI Assistants API integration for AgentSentinel.

Wraps OpenAI's Assistants API function calling with AgentSentinel protection.

Usage::

    from openai import OpenAI
    from agentsentinel import AgentPolicy, AgentGuard
    from agentsentinel.integrations.openai_assistants import (
        OpenAIAssistantsGuard,
        protect_function_map,
    )

    client = OpenAI()
    policy = AgentPolicy(daily_budget=10.0, require_approval=["send_email"])
    guard = AgentGuard(policy)

    # Define your functions
    def get_weather(location: str) -> str:
        return f"Weather in {location}: Sunny, 72°F"

    def send_email(to: str, subject: str, body: str) -> str:
        # This will require approval due to policy
        return f"Email sent to {to}"

    # Protect the function map
    protected_functions = protect_function_map(
        {"get_weather": get_weather, "send_email": send_email},
        guard=guard,
    )

    # Use in your assistant run loop
    if run.required_action:
        tool_outputs = []
        for tool_call in run.required_action.submit_tool_outputs.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)

            # This call is now protected by AgentSentinel
            result = protected_functions[fn_name](**fn_args)
            tool_outputs.append({"tool_call_id": tool_call.id, "output": result})

.. note::
    This module does **not** import ``openai`` at the module level, so
    ``agentsentinel`` has no hard dependency on the OpenAI SDK.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, TypeVar

from ..guard import AgentGuard
from ..policy import AgentPolicy

F = TypeVar("F", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# Core guard class
# ---------------------------------------------------------------------------


class OpenAIAssistantsGuard:
    """Wraps OpenAI Assistants API function calls with :class:`.AgentGuard`.

    Parameters
    ----------
    guard:
        A pre-configured :class:`.AgentGuard` instance.
    policy:
        :class:`.AgentPolicy` used to create a guard when *guard* is ``None``.
        Ignored when *guard* is provided.
    default_model:
        Default model name used for cost tracking when not overridden per function.

    Example
    -------
    ::

        from agentsentinel import AgentGuard, AgentPolicy
        from agentsentinel.integrations.openai_assistants import OpenAIAssistantsGuard

        policy = AgentPolicy(daily_budget=20.0, model_budgets={"gpt-4o": 10.0})
        oai_guard = OpenAIAssistantsGuard(AgentGuard(policy), default_model="gpt-4o")

        protected = oai_guard.protect_function_map(
            {"get_weather": get_weather, "send_email": send_email}
        )
    """

    def __init__(
        self,
        guard: Optional[AgentGuard] = None,
        policy: Optional[AgentPolicy] = None,
        default_model: str = "gpt-4o",
    ) -> None:
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

    def protect_function(
        self,
        func: F,
        name: Optional[str] = None,
        cost: Optional[float] = None,
        model: Optional[str] = None,
    ) -> F:
        """Protect a single function for use with the Assistants API.

        Parameters
        ----------
        func:
            The callable to protect.
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

    def protect_function_map(
        self,
        functions: Dict[str, Callable[..., Any]],
        costs: Optional[Dict[str, float]] = None,
        models: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Callable[..., Any]]:
        """Return a new dict with every callable protected.

        Parameters
        ----------
        functions:
            Mapping of function names to callables.
        costs:
            Optional per-function cost overrides ``{name: cost_usd}``.
        models:
            Optional per-function model name overrides.

        Returns
        -------
        A **new** dict with the same keys but guarded callables as values.
        """
        costs = costs or {}
        models = models or {}

        protected: Dict[str, Callable[..., Any]] = {}
        for fn_name, func in functions.items():
            protected[fn_name] = self.protect_function(
                func,
                name=fn_name,
                cost=costs.get(fn_name),
                model=models.get(fn_name, self._default_model),
            )
        return protected

    def handle_tool_calls(
        self,
        tool_calls: List[Any],
        functions: Dict[str, Callable[..., Any]],
    ) -> List[Dict[str, str]]:
        """Handle tool calls from an Assistant run, returning tool outputs.

        Parameters
        ----------
        tool_calls:
            List of tool call objects from ``run.required_action.submit_tool_outputs.tool_calls``.
        functions:
            Protected function map (output of :meth:`protect_function_map`).

        Returns
        -------
        List of ``{"tool_call_id": ..., "output": ...}`` dicts ready for
        ``client.beta.threads.runs.submit_tool_outputs``.
        """
        outputs: List[Dict[str, str]] = []
        for tool_call in tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)

            try:
                if fn_name in functions:
                    result = functions[fn_name](**fn_args)
                else:
                    result = f"Error: Unknown function '{fn_name}'"
            except Exception as exc:
                result = f"Error: {exc}"

            outputs.append({
                "tool_call_id": tool_call.id,
                "output": str(result),
            })

        return outputs


# ---------------------------------------------------------------------------
# Convenience one-liner
# ---------------------------------------------------------------------------


def protect_function_map(
    functions: Dict[str, Callable[..., Any]],
    *,
    guard: Optional[AgentGuard] = None,
    policy: Optional[AgentPolicy] = None,
    costs: Optional[Dict[str, float]] = None,
    models: Optional[Dict[str, str]] = None,
    default_model: str = "gpt-4o",
) -> Dict[str, Callable[..., Any]]:
    """One-liner: protect every function in *functions* for the Assistants API.

    Parameters
    ----------
    functions:
        Mapping of function names to callables.
    guard:
        Pre-configured :class:`.AgentGuard`.  If ``None``, *policy* must be
        supplied and a new guard is created automatically.
    policy:
        :class:`.AgentPolicy` used to create a guard when *guard* is ``None``.
        Ignored when *guard* is provided.
    costs:
        Optional per-function cost overrides.
    models:
        Optional per-function model name overrides.
    default_model:
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
        from agentsentinel.integrations.openai_assistants import protect_function_map

        protected = protect_function_map(
            {"get_weather": get_weather, "send_email": send_email},
            policy=AgentPolicy(daily_budget=10.0, require_approval=["send_email"]),
        )
    """
    if guard is None and policy is None:
        raise ValueError("Supply either 'guard' or 'policy'.")

    oai_guard = OpenAIAssistantsGuard(guard=guard, policy=policy, default_model=default_model)
    return oai_guard.protect_function_map(functions, costs=costs, models=models)
