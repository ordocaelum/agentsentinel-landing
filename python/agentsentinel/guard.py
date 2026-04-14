"""AgentGuard — the main decorator/wrapper class."""

from __future__ import annotations

import fnmatch
import functools
import time
from typing import Any, Callable, Dict, List, Optional

from .approval import ApprovalHandler, DenyAllApprover
from .audit import AuditEvent, AuditLogger, ConsoleAuditSink, InMemoryAuditSink
from .errors import BudgetExceededError, ContentInspectionError, PIIDetectedError
from .inspector import ContentInspector, InspectionResult
from .network import NetworkGuard
from .policy import AgentPolicy
from .rate_limit import RateLimiter
from .security import SecurityConfig, is_tool_blocked, redact_sensitive


def _safe_error_str(message: str, sec: "SecurityConfig") -> str:
    """Return *message* with sensitive patterns redacted when logging errors."""
    if sec.log_full_params:
        return message
    return redact_sensitive(message, sec.redact_patterns)

class AgentGuard:
    """Wraps agent tools with spend controls, approval gates, rate limiting,
    and audit logging — based on an :class:`.AgentPolicy`.

    Parameters
    ----------
    policy:
        The safety configuration to enforce.
    approval_handler:
        Handles approval requests for protected tools.  Defaults to
        :class:`.DenyAllApprover` (raises :class:`.ApprovalRequiredError`
        for any tool in ``policy.require_approval``).
    audit_logger:
        Custom audit logger.  If ``None``, a default logger is created
        whose sink depends on ``policy.alert_channel``.

    Example
    -------
    ::

        policy = AgentPolicy(daily_budget=10.0, require_approval=["send_email"])
        guard  = AgentGuard(policy=policy)

        @guard.protect(tool_name="search_web", cost=0.01)
        def search_web(query: str) -> str:
            return f"Results for: {query}"
    """

    def __init__(
        self,
        policy: AgentPolicy,
        approval_handler: Optional[ApprovalHandler] = None,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        self.policy = policy
        self.approval_handler: ApprovalHandler = approval_handler or DenyAllApprover()

        if audit_logger is not None:
            self.audit_logger = audit_logger
        else:
            sink = ConsoleAuditSink() if policy.alert_channel == "console" else ConsoleAuditSink()
            self.audit_logger = AuditLogger(sinks=[sink] if policy.audit_log else [])

        self._rate_limiter = RateLimiter(policy.rate_limits)

        # PII / content inspection
        self._content_inspector = ContentInspector(policy.inspector_config)
        self._network_guard = NetworkGuard(policy.network_policy)

        # Cost accumulators — reset on each new day/hour in a real system;
        # here we reset at construction time for simplicity.
        self._daily_spent: float = 0.0
        self._hourly_spent: float = 0.0
        self._hourly_reset_at: float = time.time()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reset_hourly_if_needed(self) -> None:
        if time.time() - self._hourly_reset_at >= 3600:
            self._hourly_spent = 0.0
            self._hourly_reset_at = time.time()

    def _requires_approval(self, tool_name: str) -> bool:
        # Explicit policy patterns
        for pattern in self.policy.require_approval:
            if tool_name == pattern or fnmatch.fnmatch(tool_name, pattern):
                return True
        # Sensitive tools always require approval (sandbox_mode or security config)
        sec = self.policy.security
        for pattern in sec.sensitive_tools:
            if tool_name == pattern or fnmatch.fnmatch(tool_name, pattern):
                return True
        return False

    def _estimate_cost(self, tool_name: str, kwargs: Dict[str, Any]) -> float:
        if self.policy.cost_estimator is not None:
            return self.policy.cost_estimator(tool_name, kwargs)
        return 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def protect(
        self,
        func: Optional[Callable] = None,
        *,
        tool_name: Optional[str] = None,
        cost: Optional[float] = None,
    ) -> Callable:
        """Decorator that enforces all policy rules on *func*.

        Can be used with or without arguments::

            @guard.protect
            def my_tool(): ...

            @guard.protect(tool_name="my_tool", cost=0.05)
            def my_tool(): ...

        Parameters
        ----------
        func:
            The callable to protect (when used without parentheses).
        tool_name:
            Override the name used for policy matching and audit logs.
            Defaults to ``func.__name__``.
        cost:
            Explicit cost per invocation (USD).  If not provided and no
            ``policy.cost_estimator`` is set, defaults to ``0.0``.
        """

        def decorator(fn: Callable) -> Callable:
            resolved_name = tool_name or fn.__name__

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                sec = self.policy.security

                # --- Security: blocked tools (hard stop, no exceptions) ---
                if is_tool_blocked(resolved_name, sec.blocked_tools):
                    event = AuditEvent.now(
                        tool_name=resolved_name,
                        status="blocked",
                        cost=0.0,
                        decision="blocked_security",
                        reason="tool_in_blocked_list",
                    )
                    self.audit_logger.record(event)
                    from .errors import ToolBlockedError
                    raise ToolBlockedError(
                        f"Tool '{resolved_name}' is permanently blocked by security policy.",
                        tool_name=resolved_name,
                    )

                # --- DLP: inspect tool arguments for PII ---
                if self.policy.dlp_enabled:
                    report = self._content_inspector.inspect_args(resolved_name, args, kwargs)
                    if report.result == InspectionResult.BLOCK:
                        pii_types = [m.pii_type.value for m in report.pii_matches]
                        event = AuditEvent.now(
                            tool_name=resolved_name,
                            status="blocked",
                            cost=0.0,
                            decision="blocked_pii",
                            reason=report.reason,
                        )
                        self.audit_logger.record(event)
                        if self.policy.dlp_block_on_violation:
                            raise PIIDetectedError(
                                f"PII detected in arguments for '{resolved_name}': {report.reason}",
                                pii_types=pii_types,
                                tool_name=resolved_name,
                            )

                # --- Cost estimation ---
                invocation_cost = cost if cost is not None else self._estimate_cost(resolved_name, kwargs)

                # --- Budget checks (pre-execution) ---
                self._reset_hourly_if_needed()

                if self._hourly_spent + invocation_cost > self.policy.hourly_budget:
                    event = AuditEvent.now(
                        tool_name=resolved_name,
                        status="blocked",
                        cost=invocation_cost,
                        decision="blocked_budget",
                        reason="hourly_budget_exceeded",
                    )
                    self.audit_logger.record(event)
                    raise BudgetExceededError(
                        f"Hourly budget exceeded for '{resolved_name}'. "
                        f"Budget: ${self.policy.hourly_budget:.2f}, "
                        f"spent this hour: ${self._hourly_spent:.2f}.",
                        budget=self.policy.hourly_budget,
                        spent=self._hourly_spent,
                    )

                if self._daily_spent + invocation_cost > self.policy.daily_budget:
                    event = AuditEvent.now(
                        tool_name=resolved_name,
                        status="blocked",
                        cost=invocation_cost,
                        decision="blocked_budget",
                        reason="daily_budget_exceeded",
                    )
                    self.audit_logger.record(event)
                    raise BudgetExceededError(
                        f"Daily budget exceeded for '{resolved_name}'. "
                        f"Budget: ${self.policy.daily_budget:.2f}, "
                        f"spent today: ${self._daily_spent:.2f}.",
                        budget=self.policy.daily_budget,
                        spent=self._daily_spent,
                    )

                # --- Rate-limit check ---
                self._rate_limiter.check(resolved_name)

                # --- Approval check (policy + sensitive tools) ---
                if self._requires_approval(resolved_name):
                    try:
                        approved = self.approval_handler.request_approval(resolved_name, **kwargs)
                    except Exception:
                        # Handler raised directly (e.g. DenyAllApprover / InMemoryApprover).
                        # Record the audit event before re-raising.
                        event = AuditEvent.now(
                            tool_name=resolved_name,
                            status="blocked",
                            cost=0.0,
                            decision="approval_required",
                        )
                        self.audit_logger.record(event)
                        raise

                    if not approved:
                        event = AuditEvent.now(
                            tool_name=resolved_name,
                            status="blocked",
                            cost=0.0,
                            decision="approval_required",
                        )
                        self.audit_logger.record(event)
                        from .errors import ApprovalRequiredError
                        raise ApprovalRequiredError(
                            f"Tool '{resolved_name}' was denied by the approval handler.",
                            tool_name=resolved_name,
                        )

                    # Approved — log and continue.
                    event = AuditEvent.now(
                        tool_name=resolved_name,
                        status="approved",
                        cost=invocation_cost,
                        decision="approved",
                    )
                    self.audit_logger.record(event)

                # --- Execute the tool ---
                try:
                    result = fn(*args, **kwargs)
                except Exception as exc:
                    event = AuditEvent.now(
                        tool_name=resolved_name,
                        status="error",
                        cost=0.0,
                        decision="error",
                        error=_safe_error_str(str(exc), sec),
                    )
                    self.audit_logger.record(event)
                    raise

                # --- DLP: inspect tool result for PII leakage ---
                if self.policy.dlp_enabled:
                    result_report = self._content_inspector.inspect_result(resolved_name, result)
                    if result_report.result == InspectionResult.BLOCK:
                        pii_types = [m.pii_type.value for m in result_report.pii_matches]
                        event = AuditEvent.now(
                            tool_name=resolved_name,
                            status="blocked",
                            cost=0.0,
                            decision="blocked_content",
                            reason=result_report.reason,
                        )
                        self.audit_logger.record(event)
                        if self.policy.dlp_block_on_violation:
                            raise ContentInspectionError(
                                f"PII detected in result of '{resolved_name}': {result_report.reason}",
                                tool_name=resolved_name,
                                reason=result_report.reason,
                            )

                # --- Post-execution: record cost + audit event ---
                self._daily_spent += invocation_cost
                self._hourly_spent += invocation_cost

                event = AuditEvent.now(
                    tool_name=resolved_name,
                    status="success",
                    cost=invocation_cost,
                    decision="allowed",
                )
                self.audit_logger.record(event)

                return result

            return wrapper

        # Support both @guard.protect and @guard.protect(...)
        if func is not None:
            return decorator(func)
        return decorator

    @property
    def daily_spent(self) -> float:
        """Cumulative cost spent today (USD)."""
        return self._daily_spent

    @property
    def hourly_spent(self) -> float:
        """Cumulative cost spent in the current hour (USD)."""
        return self._hourly_spent

    def reset_costs(self) -> None:
        """Reset all cost accumulators (useful for testing)."""
        self._daily_spent = 0.0
        self._hourly_spent = 0.0
        self._hourly_reset_at = time.time()
