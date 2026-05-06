# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""AgentSentinel Python SDK — developer preview."""

from .approval import ApprovalHandler, DenyAllApprover, InMemoryApprover
from .audit import AuditEvent, AuditLogger, ConsoleAuditSink, InMemoryAuditSink
from .cost_tracker import (
    CostTracker,
    CostTrackerConfig,
    ModelUsage,
    count_tokens,
    estimate_tokens_from_response,
)
from .errors import (
    AgentSentinelError,
    ApprovalRequiredError,
    BudgetExceededError,
    ContentInspectionError,
    ModelBudgetExceededError,
    NetworkPolicyViolationError,
    PIIDetectedError,
    RateLimitExceededError,
    ToolBlockedError,
)
from .guard import AgentGuard
from .inspector import ContentInspector, InspectionReport, InspectionResult, InspectorConfig
from .licensing import (
    FeatureNotAvailableError,
    LicenseError,
    LicenseInfo,
    LicenseManager,
    LicenseTier,
    UsageLimitExceededError,
    get_license_info,
    get_license_manager,
    is_feature_available,
    require_feature,
    set_license_key,
)
from .network import NetworkGuard, NetworkPolicy
from .pii import PIIConfig, PIIMatch, PIIScanner, PIIType, luhn_check
from .policy import AgentPolicy
from .pricing import (
    MODEL_PRICING,
    ModelPricing,
    ModelProvider,
    calculate_cost,
    get_model_pricing,
    list_all_providers,
    list_models_by_provider,
)
from .rate_limit import RateLimiter
from .security import SecurityConfig, is_tool_blocked, redact_sensitive

__version__ = "1.2.0"

__all__ = [
    # Policy
    "AgentPolicy",
    # Guard
    "AgentGuard",
    # Errors
    "AgentSentinelError",
    "BudgetExceededError",
    "ModelBudgetExceededError",
    "ApprovalRequiredError",
    "RateLimitExceededError",
    "ToolBlockedError",
    "PIIDetectedError",
    "NetworkPolicyViolationError",
    "ContentInspectionError",
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
    # PII detection
    "PIIConfig",
    "PIIMatch",
    "PIIScanner",
    "PIIType",
    "luhn_check",
    # Network security
    "NetworkPolicy",
    "NetworkGuard",
    # Content inspection
    "InspectorConfig",
    "ContentInspector",
    "InspectionResult",
    "InspectionReport",
    # Pricing
    "MODEL_PRICING",
    "ModelPricing",
    "ModelProvider",
    "calculate_cost",
    "get_model_pricing",
    "list_all_providers",
    "list_models_by_provider",
    # Cost tracking
    "CostTracker",
    "CostTrackerConfig",
    "ModelUsage",
    "count_tokens",
    "estimate_tokens_from_response",
    # Licensing
    "LicenseError",
    "LicenseInfo",
    "LicenseManager",
    "LicenseTier",
    "FeatureNotAvailableError",
    "UsageLimitExceededError",
    "get_license_info",
    "get_license_manager",
    "is_feature_available",
    "require_feature",
    "set_license_key",
    # Optional integrations (imported lazily to avoid hard framework deps)
    # from agentsentinel.integrations.langchain import LangChainGuard, protect_langchain_agent
    # from agentsentinel.integrations.autogen  import AutoGenGuard, protect_function_map
    # Optional handlers
    # from agentsentinel.handlers.slack import SlackApprover, SlackConfig
    # Dashboard (stdlib only — no extra deps)
    # from agentsentinel.dashboard import DashboardServer, start_dashboard
]
