"""AgentPolicy — configuration dataclass for agent safety controls."""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .inspector import InspectorConfig
from .network import NetworkPolicy
from .pii import PIIConfig
from .security import SecurityConfig


@dataclass
class AgentPolicy:
    """Configuration for agent safety controls.

    Parameters
    ----------
    daily_budget:
        Maximum cumulative cost (USD) allowed per calendar day.
        Defaults to unlimited (``float('inf')``).
    hourly_budget:
        Maximum cumulative cost (USD) allowed per rolling hour.
        Defaults to unlimited (``float('inf')``).
    require_approval:
        List of tool name patterns that require explicit human approval
        before execution.  Supports exact names and ``fnmatch``-style
        wildcards, e.g. ``["delete_*", "send_email"]``.
    rate_limits:
        Per-tool rate limit strings.  Keys are tool name patterns
        (wildcards supported); values are strings like ``"10/min"`` or
        ``"100/hour"``.
    audit_log:
        When ``True`` (the default) every tool invocation is recorded by
        the configured audit sinks.
    alert_channel:
        Where to send real-time alerts.  Currently ``"console"`` (default)
        is supported; future versions will add ``"slack"`` / webhook.
    cost_estimator:
        Optional callable ``(tool_name, kwargs) -> float`` that returns an
        estimated cost for a given tool invocation.  Used when no explicit
        ``cost`` is passed to :meth:`AgentGuard.protect`.
    security:
        Fine-grained security settings: blocked-tools kill-list, sensitive
        tools that always require approval, secrets redaction patterns, and
        parameter log controls.
    sandbox_mode:
        When ``True``, applies extra restrictions suited for untrusted or
        experimental agents: all :attr:`.SecurityConfig.sensitive_tools`
        are implicitly added to the approval list, and blocked-tool
        violations raise immediately without any fallback.
    """

    daily_budget: float = float("inf")
    hourly_budget: float = float("inf")
    require_approval: List[str] = field(default_factory=list)
    rate_limits: Dict[str, str] = field(default_factory=dict)
    audit_log: bool = True
    alert_channel: str = "console"
    cost_estimator: Optional[Callable[[str, dict], float]] = None

    # Security settings
    security: SecurityConfig = field(default_factory=SecurityConfig)

    # Sandbox mode — extra restrictions for untrusted agents
    sandbox_mode: bool = False

    # PII Protection
    pii_config: PIIConfig = field(default_factory=PIIConfig)

    # Network Security
    network_policy: NetworkPolicy = field(default_factory=NetworkPolicy)

    # Content Inspection
    inspector_config: InspectorConfig = field(default_factory=InspectorConfig)

    # Data Loss Prevention
    dlp_enabled: bool = True
    dlp_block_on_violation: bool = True
