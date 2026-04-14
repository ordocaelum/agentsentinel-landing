"""AgentPolicy — configuration dataclass for agent safety controls."""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


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
    """

    daily_budget: float = float("inf")
    hourly_budget: float = float("inf")
    require_approval: List[str] = field(default_factory=list)
    rate_limits: Dict[str, str] = field(default_factory=dict)
    audit_log: bool = True
    alert_channel: str = "console"
    cost_estimator: Optional[Callable[[str, dict], float]] = None
