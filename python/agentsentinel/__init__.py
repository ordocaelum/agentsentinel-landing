"""AgentSentinel Python SDK — developer preview."""

from .approval import ApprovalHandler, DenyAllApprover, InMemoryApprover
from .audit import AuditEvent, AuditLogger, ConsoleAuditSink, InMemoryAuditSink
from .errors import (
    AgentSentinelError,
    ApprovalRequiredError,
    BudgetExceededError,
    RateLimitExceededError,
    ToolBlockedError,
)
from .guard import AgentGuard
from .policy import AgentPolicy
from .rate_limit import RateLimiter
from .security import SecurityConfig, is_tool_blocked, redact_sensitive

__version__ = "0.1.0-preview"

__all__ = [
    # Policy
    "AgentPolicy",
    # Guard
    "AgentGuard",
    # Errors
    "AgentSentinelError",
    "BudgetExceededError",
    "ApprovalRequiredError",
    "RateLimitExceededError",
    "ToolBlockedError",
    # Audit
    "AuditEvent",
    "AuditLogger",
    "ConsoleAuditSink",
    "InMemoryAuditSink",
    # Approval
    "ApprovalHandler",
    "DenyAllApprover",
    "InMemoryApprover",
    # Rate limiting
    "RateLimiter",
    # Security
    "SecurityConfig",
    "is_tool_blocked",
    "redact_sensitive",
]
