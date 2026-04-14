# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Approval handlers for human-in-the-loop gates."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Set

from .errors import ApprovalRequiredError


class ApprovalHandler(ABC):
    """Interface for deciding whether a tool invocation is approved."""

    @abstractmethod
    def request_approval(self, tool_name: str, **kwargs) -> bool:
        """Return ``True`` if the call is approved, ``False`` to deny.

        Implementations may also raise :class:`.ApprovalRequiredError`
        directly (e.g. to communicate that no synchronous decision is
        possible).

        Parameters
        ----------
        tool_name:
            Name of the tool requesting approval.
        **kwargs:
            The arguments the tool would be called with.
        """


class DenyAllApprover(ApprovalHandler):
    """Denies every approval request by raising :class:`.ApprovalRequiredError`.

    This is the **default** approval handler.  Swap it out with an
    :class:`InMemoryApprover` (or your own implementation) for testing.
    """

    def request_approval(self, tool_name: str, **kwargs) -> bool:
        raise ApprovalRequiredError(
            f"Tool '{tool_name}' requires human approval — no approver is configured.",
            tool_name=tool_name,
        )


class InMemoryApprover(ApprovalHandler):
    """Simple approver backed by an in-memory allow-list.

    Useful for demos and unit tests.

    Parameters
    ----------
    approved_tools:
        Set of tool names that are pre-approved.  All others are denied.

    Example
    -------
    ::

        approver = InMemoryApprover(approved_tools={"send_email"})
        guard = AgentGuard(policy=policy, approval_handler=approver)
    """

    def __init__(self, approved_tools: Set[str] | None = None) -> None:
        self._approved: Set[str] = set(approved_tools or [])

    def approve(self, tool_name: str) -> None:
        """Grant approval for *tool_name*."""
        self._approved.add(tool_name)

    def revoke(self, tool_name: str) -> None:
        """Revoke approval for *tool_name*."""
        self._approved.discard(tool_name)

    def request_approval(self, tool_name: str, **kwargs) -> bool:
        if tool_name in self._approved:
            return True
        raise ApprovalRequiredError(
            f"Tool '{tool_name}' is not in the pre-approved list.",
            tool_name=tool_name,
        )
