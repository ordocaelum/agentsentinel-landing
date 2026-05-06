# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""AgentGuard — the main decorator/wrapper class."""

from __future__ import annotations

import fnmatch
import functools
import json
import queue
import threading
import time
import urllib.request
import uuid
import warnings
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .approval import ApprovalHandler, DenyAllApprover
from .audit import AuditEvent, AuditLogger, ConsoleAuditSink, InMemoryAuditSink
from .cost_tracker import CostTracker
from .errors import (
    BudgetExceededError,
    ContentInspectionError,
    ModelBudgetExceededError,
    PIIDetectedError,
)
from .inspector import ContentInspector, InspectionResult
from .licensing import (
    UsageLimitExceededError,
    get_license_manager,
)
from .network import NetworkGuard
from .policy import AgentPolicy
from .rate_limit import RateLimiter
from .security import SecurityConfig, is_tool_blocked, redact_sensitive


def _safe_error_str(message: str, sec: "SecurityConfig") -> str:
    """Return *message* with sensitive patterns redacted when logging errors."""
    if sec.log_full_params:
        return message
    return redact_sensitive(message, sec.redact_patterns)


class _EventStreamer:
    """Background thread that batches tool-decision events and POSTs them to
    the customer dashboard endpoint without blocking tool execution.

    Thread safety: :meth:`enqueue` is safe to call from any thread.
    The flusher thread is a daemon so it never prevents process exit.
    """

    def __init__(self, webhook_url: str, license_key: str, batch_size: int, interval: float) -> None:
        self._url = webhook_url
        self._key = license_key
        self._batch_size = max(1, batch_size)
        self._interval = max(0.1, interval)
        self._queue: queue.Queue[Dict[str, Any]] = queue.Queue(maxsize=5000)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="as-event-stream")
        self._thread.start()

    def enqueue(self, event: Dict[str, Any]) -> None:
        """Non-blocking enqueue.  Silently drops events when the queue is full."""
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            pass

    def _flush(self, events: List[Dict[str, Any]]) -> None:
        if not events:
            return
        payload = json.dumps({"events": events}).encode("utf-8")
        try:
            req = urllib.request.Request(
                self._url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10):  # noqa: S310
                pass
        except Exception:
            pass  # Best-effort: never raise from background thread

    def _run(self) -> None:
        while not self._stop_event.is_set():
            batch: List[Dict[str, Any]] = []
            deadline = time.monotonic() + self._interval
            while time.monotonic() < deadline and len(batch) < self._batch_size:
                remaining = deadline - time.monotonic()
                try:
                    ev = self._queue.get(timeout=max(0.05, remaining))
                    batch.append(ev)
                except queue.Empty:
                    break
            self._flush(batch)

    def stop(self) -> None:
        """Signal the flusher thread to exit and flush remaining events."""
        self._stop_event.set()
        # Drain remaining events
        remaining: List[Dict[str, Any]] = []
        while True:
            try:
                remaining.append(self._queue.get_nowait())
            except queue.Empty:
                break
        self._flush(remaining)


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
        license_key: Optional[str] = None,
    ) -> None:
        # Set license key if provided
        if license_key:
            from .licensing import set_license_key
            set_license_key(license_key)

        # Register this agent with the license manager
        self._agent_id = str(uuid.uuid4())
        get_license_manager().register_agent(self._agent_id)

        # Show watermark if required by license tier
        if get_license_manager().should_show_watermark():
            print("[Powered by AgentSentinel — https://agentsentinel.net]")

        self.policy = policy
        self.approval_handler: ApprovalHandler = approval_handler or DenyAllApprover()

        if audit_logger is not None:
            self.audit_logger = audit_logger
        else:
            if policy.audit_log:
                sinks = [ConsoleAuditSink(), InMemoryAuditSink()]
            else:
                sinks = []
            self.audit_logger = AuditLogger(sinks=sinks)

        self._rate_limiter = RateLimiter(policy.rate_limits)

        # PII / content inspection
        self._content_inspector = ContentInspector(policy.inspector_config)
        self._network_guard = NetworkGuard(policy.network_policy)

        # Cost accumulators — reset on each new day/hour in a real system;
        # here we reset at construction time for simplicity.
        # _spend_lock guards _daily_spent and _hourly_spent to prevent data
        # races when the guard is shared across threads.
        self._spend_lock = threading.Lock()
        self._daily_spent: float = 0.0
        self._hourly_spent: float = 0.0
        self._hourly_reset_at: float = time.time()

        # Per-model cost tracking
        # Merge model_budgets shortcut into the cost_tracking config
        tracker_config = policy.cost_tracking
        if policy.model_budgets:
            merged = {**tracker_config.model_budgets, **policy.model_budgets}
            from .cost_tracker import CostTrackerConfig
            tracker_config = CostTrackerConfig(
                enabled=tracker_config.enabled,
                track_tokens=tracker_config.track_tokens,
                track_by_model=tracker_config.track_by_model,
                track_by_tool=tracker_config.track_by_tool,
                model_budgets=merged,
                custom_token_counter=tracker_config.custom_token_counter,
            )
        self.cost_tracker = CostTracker(tracker_config)

        # ── Event streaming to customer dashboard ────────────────────────────
        self._streamer: Optional[_EventStreamer] = None
        if policy.webhook_url and policy.stream_events:
            key = policy.webhook_key or license_key or ""
            if key:
                self._streamer = _EventStreamer(
                    webhook_url=policy.webhook_url,
                    license_key=key,
                    batch_size=policy.stream_batch_size,
                    interval=policy.stream_interval,
                )

    def __del__(self) -> None:
        """Unregister this agent from the license manager when destroyed."""
        try:
            get_license_manager().unregister_agent(self._agent_id)
        except Exception:
            pass  # Never raise in __del__
        try:
            if self._streamer is not None:
                self._streamer.stop()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reset_hourly_if_needed(self) -> None:
        # Called while _spend_lock is held.
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
        model: Optional[str] = None,
    ) -> Callable:
        """Decorator that enforces all policy rules on *func*.

        Can be used with or without arguments::

            @guard.protect
            def my_tool(): ...

            @guard.protect(tool_name="my_tool", cost=0.05)
            def my_tool(): ...

            @guard.protect(model="gpt-4o")
            def call_llm(prompt: str) -> str: ...

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
        model:
            LLM model name (e.g. ``"gpt-4o"``).  When provided, the guard
            checks per-model budget limits before execution and records
            token-level costs via the :class:`.CostTracker`.
        """

        def decorator(fn: Callable) -> Callable:
            resolved_name = tool_name or fn.__name__
            resolved_model = model

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
                    self._stream_tool_event(resolved_name, "blocked", 0.0,
                                            {"reason": "tool_in_blocked_list"})
                    raise ToolBlockedError(
                        f"Tool '{resolved_name}' is permanently blocked by security policy.",
                        tool_name=resolved_name,
                    )

                # --- DLP: inspect tool arguments for PII ---
                if self.policy.dlp_enabled:
                    arg_report = self._content_inspector.inspect_args(resolved_name, args, kwargs)
                    if arg_report.result == InspectionResult.BLOCK:
                        pii_types = [m.pii_type.value for m in arg_report.pii_matches]
                        event = AuditEvent.now(
                            tool_name=resolved_name,
                            status="blocked",
                            cost=0.0,
                            decision="blocked_pii",
                            reason=arg_report.reason,
                        )
                        self.audit_logger.record(event)
                        if self.policy.dlp_block_on_violation:
                            raise PIIDetectedError(
                                f"PII detected in arguments for '{resolved_name}': {arg_report.reason}",
                                pii_types=pii_types,
                                tool_name=resolved_name,
                            )

                # --- Cost estimation ---
                invocation_cost = cost if cost is not None else self._estimate_cost(resolved_name, kwargs)

                # --- Budget checks (pre-execution) ---
                # Use _spend_lock to make the read-check sequence atomic;
                # otherwise two concurrent calls can both pass the check and
                # jointly exceed the budget.
                with self._spend_lock:
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

                # --- Per-model budget check ---
                if resolved_model and self.cost_tracker.config.enabled:
                    allowed, reason = self.cost_tracker.check_model_budget(resolved_model)
                    if not allowed:
                        usage = self.cost_tracker.get_model_usage(resolved_model)
                        spent_amount = usage.total_cost if usage else 0.0
                        budget_amount = 0.0
                        for pat, bud in self.cost_tracker.config.model_budgets.items():
                            if fnmatch.fnmatch(resolved_model.lower(), pat.lower()):
                                budget_amount = bud
                                break
                        event = AuditEvent.now(
                            tool_name=resolved_name,
                            status="blocked",
                            cost=0.0,
                            decision="blocked_budget",
                            reason="model_budget_exceeded",
                        )
                        self.audit_logger.record(event)
                        raise ModelBudgetExceededError(
                            model=resolved_model,
                            spent=spent_amount,
                            budget=budget_amount,
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

                # --- License: record event for usage tracking ---
                try:
                    get_license_manager().record_event()
                except UsageLimitExceededError as exc:
                    warnings.warn(str(exc), UserWarning, stacklevel=2)

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
                with self._spend_lock:
                    self._daily_spent += invocation_cost
                    self._hourly_spent += invocation_cost

                # Record per-model token/cost usage
                if resolved_model and self.cost_tracker.config.enabled:
                    self.cost_tracker.record_usage(
                        model_name=resolved_model,
                        input_tokens=0,
                        output_tokens=0,
                        tool_name=resolved_name,
                    )

                event = AuditEvent.now(
                    tool_name=resolved_name,
                    status="success",
                    cost=invocation_cost,
                    decision="allowed",
                )
                self.audit_logger.record(event)

                # --- Stream event to customer dashboard (non-blocking) ---
                self._stream_tool_event(
                    resolved_name,
                    "allowed",
                    invocation_cost,
                )

                return result

            return wrapper

        # Support both @guard.protect and @guard.protect(...)
        if func is not None:
            return decorator(func)
        return decorator

    def _stream_tool_event(
        self,
        tool_name: str,
        status: str,
        cost: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Enqueue a tool-decision event for background streaming.

        This is a no-op when :attr:`_streamer` is ``None`` (i.e. when
        ``policy.webhook_url`` is not set or ``policy.stream_events`` is
        ``False``).  It never blocks or raises.
        """
        if self._streamer is None:
            return
        key = self.policy.webhook_key or ""
        ev: Dict[str, Any] = {
            "license_key": key,
            "agent_id": self._agent_id,
            "tool_name": tool_name,
            "status": status,
            "cost": cost if cost else None,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
        if metadata:
            ev["metadata"] = metadata
        self._streamer.enqueue(ev)

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
        with self._spend_lock:
            self._daily_spent = 0.0
            self._hourly_spent = 0.0
            self._hourly_reset_at = time.time()
        self.cost_tracker.reset()
