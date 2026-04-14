# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""AgentSentinel exception hierarchy."""

from __future__ import annotations

from typing import List, Optional


class AgentSentinelError(Exception):
    """Base class for all AgentSentinel errors."""


class BudgetExceededError(AgentSentinelError):
    """Raised when an agent exceeds its configured spend budget."""

    def __init__(self, message: str = "Budget limit exceeded", *, budget: float = 0.0, spent: float = 0.0):
        super().__init__(message)
        self.budget = budget
        self.spent = spent


class ApprovalRequiredError(AgentSentinelError):
    """Raised when a tool invocation requires human approval before proceeding."""

    def __init__(self, message: str = "Human approval required", *, tool_name: str = ""):
        super().__init__(message)
        self.tool_name = tool_name


class RateLimitExceededError(AgentSentinelError):
    """Raised when a tool has been called more times than its configured rate limit allows."""

    def __init__(self, message: str = "Rate limit exceeded", *, tool_name: str = "", limit: str = ""):
        super().__init__(message)
        self.tool_name = tool_name
        self.limit = limit


class ToolBlockedError(AgentSentinelError):
    """Raised when a tool is permanently blocked by the security policy.

    This differs from :class:`ApprovalRequiredError` in that there is no
    approval pathway — the tool is hard-blocked and will never execute.
    """

    def __init__(self, message: str = "Tool is blocked by security policy", *, tool_name: str = ""):
        super().__init__(message)
        self.tool_name = tool_name


class PIIDetectedError(AgentSentinelError):
    """Raised when PII is detected in outbound data and blocking is enabled."""

    def __init__(
        self,
        message: str = "PII detected in data",
        *,
        pii_types: Optional[List[str]] = None,
        tool_name: str = "",
    ):
        super().__init__(message)
        self.pii_types = pii_types or []
        self.tool_name = tool_name


class NetworkPolicyViolationError(AgentSentinelError):
    """Raised when an outbound request violates the network policy."""

    def __init__(
        self,
        message: str = "Network policy violation",
        *,
        url: str = "",
        reason: str = "",
    ):
        super().__init__(message)
        self.url = url
        self.reason = reason


class ContentInspectionError(AgentSentinelError):
    """Raised when content inspection fails or detects a policy violation."""

    def __init__(
        self,
        message: str = "Content inspection failed",
        *,
        tool_name: str = "",
        reason: str = "",
    ):
        super().__init__(message)
        self.tool_name = tool_name
        self.reason = reason


class ModelBudgetExceededError(AgentSentinelError):
    """Raised when a model's per-model budget limit is exceeded."""

    def __init__(self, model: str, spent: float, budget: float) -> None:
        self.model = model
        self.spent = spent
        self.budget = budget
        super().__init__(
            f"Model '{model}' budget exceeded: ${spent:.4f} >= ${budget:.2f}"
        )
