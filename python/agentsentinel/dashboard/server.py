# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Local web dashboard server for AgentSentinel.

Zero external dependencies — built on :mod:`http.server` from the stdlib.

The dashboard exposes:

* ``GET /``                            — the single-page Tailwind CSS dark-theme UI
* ``GET /admin``                       — redirect to ``/admin/`` (301)
* ``GET /admin/``                      — admin SPA (index.html)
* ``GET /admin/*``                     — admin static assets
* ``GET /css/*``, ``/js/*``, ``/svg/*``, ``/assets/*`` — root-path aliases for admin assets
* ``GET /api/debug/static-status``     — (dev-only) JSON report on static-file locations
* ``GET /api/stats``                   — JSON snapshot of all audit events
* ``GET /api/stats/history``           — time-series data for charts
* ``GET /api/events``                  — paginated events with filtering
* ``GET /api/approvals``               — pending approval requests
* ``POST /api/approvals/{id}/approve`` — approve a request
* ``POST /api/approvals/{id}/reject``  — reject a request
* ``POST /api/approvals/approve-all``  — bulk approve all pending
* ``POST /api/approvals/reject-all``   — bulk reject all pending
* ``GET /api/approvals/settings``      — get approval settings
* ``POST /api/approvals/settings``     — update approval settings
* ``GET /api/alerts``                  — active alerts
* ``POST /api/alerts/{id}/dismiss``    — dismiss an alert
* ``GET /api/agents``                  — list all agents
* ``POST /api/agents``                 — register new agent
* ``GET /api/agents/{id}``             — get agent details
* ``DELETE /api/agents/{id}``          — remove agent
* ``POST /api/agents/{id}/nickname``   — set friendly name
* ``GET /api/agent/status``            — get agent runtime status
* ``POST /api/agent/pause``            — pause agent
* ``POST /api/agent/resume``           — resume agent
* ``POST /api/agent/stop``             — emergency stop
* ``POST /api/agent/reset``            — reset session counters
* ``POST /api/agent/lock``             — lock config
* ``POST /api/agent/unlock``           — unlock config
* ``GET /api/budget``                  — current budget status
* ``POST /api/budget/daily``           — set daily budget
* ``POST /api/budget/hourly``          — set hourly budget
* ``POST /api/budget/boost``           — add amount to budget
* ``POST /api/budget/lock``            — lock budget
* ``POST /api/budget/unlock``          — unlock budget
* ``GET /api/budget/forecast``         — spending projection
* ``POST /api/budget/thresholds``      — configure warning thresholds
* ``GET /api/tools``                   — list all tools with status
* ``POST /api/tools/{name}/enable``    — enable tool
* ``POST /api/tools/{name}/disable``   — disable tool
* ``POST /api/tools/{name}/block``     — permanently block tool
* ``POST /api/tools/{name}/require-approval`` — add to approval list
* ``POST /api/tools/{name}/remove-approval``  — remove from approval list
* ``POST /api/tools/{name}/rate-limit`` — set rate limit
* ``POST /api/tools/{name}/note``      — add note to tool
* ``GET /api/tools/{name}/history``    — tool call history
* ``GET /api/models``                  — list all models with status
* ``POST /api/models/{name}/enable``   — enable model
* ``POST /api/models/{name}/disable``  — disable model
* ``POST /api/models/{name}/budget``   — set per-model budget
* ``POST /api/models/{name}/reset``    — reset model spend
* ``GET /api/policy``                  — get current policy YAML/JSON
* ``POST /api/policy``                 — update policy
* ``POST /api/policy/validate``        — validate without applying
* ``GET /api/policy/history``          — version history
* ``POST /api/policy/lock``            — lock policy
* ``POST /api/policy/unlock``          — unlock policy
* ``POST /api/policy/presets/{name}``  — apply preset
* ``GET /api/notifications``           — list all notifications
* ``GET /api/notifications/unread``    — unread count
* ``POST /api/notifications/{id}/read``       — mark as read
* ``POST /api/notifications/read-all``        — mark all read
* ``POST /api/notifications/{id}/dismiss``    — dismiss
* ``POST /api/notifications/{id}/snooze``     — snooze
* ``GET /api/notifications/settings``         — get notification settings
* ``POST /api/notifications/settings``        — update notification settings

Usage::

    from agentsentinel import AgentGuard, AgentPolicy
    from agentsentinel.dashboard import start_dashboard

    guard = AgentGuard(policy=AgentPolicy(daily_budget=10.0))
    start_dashboard(guard, port=8080)   # blocks; Ctrl-C to stop

Or in the background::

    import threading
    from agentsentinel.dashboard import DashboardServer

    server = DashboardServer(guard, port=8080)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
"""

from __future__ import annotations

import fnmatch
import http.server
import json
import mimetypes
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------------------
# Path to the bundled static HTML file
# ---------------------------------------------------------------------------
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_INDEX_HTML = os.path.join(_STATIC_DIR, "index.html")
_ADMIN_DIR = os.path.join(_STATIC_DIR, "admin")

_INF = float("inf")

# ---------------------------------------------------------------------------
# MIME type fallback map — used when mimetypes.guess_type returns None.
# Python's mimetypes database varies by OS; JavaScript in particular is
# missing or wrong on some systems.
# ---------------------------------------------------------------------------
_MIME_FALLBACK: Dict[str, str] = {
    ".js":    "application/javascript",
    ".mjs":   "application/javascript",
    ".css":   "text/css",
    ".json":  "application/json",
    ".svg":   "image/svg+xml",
    ".woff":  "font/woff",
    ".woff2": "font/woff2",
    ".ttf":   "font/ttf",
    ".ico":   "image/x-icon",
    ".png":   "image/png",
    ".jpg":   "image/jpeg",
    ".jpeg":  "image/jpeg",
    ".webp":  "image/webp",
    ".html":  "text/html; charset=utf-8",
    ".txt":   "text/plain; charset=utf-8",
}

# Root-level path prefixes that are aliased into the admin static directory.
# When the browser requests e.g. /css/admin.css (because the HTML was loaded
# at /admin without a trailing slash, making relative URLs resolve to the site
# root), we transparently remap those requests to /admin/css/admin.css.
_ADMIN_STATIC_ROOT_PREFIXES = ("/css/", "/js/", "/svg/", "/assets/", "/fonts/", "/img/")
_ADMIN_STATIC_ROOT_FILES    = ("/admin.css", "/app.js")

# ---------------------------------------------------------------------------
# In-memory store for approvals and alerts (demo/mock data)
# ---------------------------------------------------------------------------
_approvals_lock = threading.Lock()
_approvals: Dict[str, Dict[str, Any]] = {}

_alerts_lock = threading.Lock()
_alerts: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Multi-agent registry
# ---------------------------------------------------------------------------
_agents_lock = threading.Lock()
_agents: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Agent runtime state
# ---------------------------------------------------------------------------
_agent_state_lock = threading.Lock()
_agent_state: Dict[str, Any] = {
    "status": "running",      # running / paused / stopped / error
    "locked": False,
    "uptime_start": time.time(),
    "last_activity": time.time(),
    "connection": "connected",
}

# ---------------------------------------------------------------------------
# Budget overrides (allows runtime adjustment beyond policy)
# ---------------------------------------------------------------------------
_budget_lock = threading.Lock()
_budget_state: Dict[str, Any] = {
    "daily_override": None,
    "hourly_override": None,
    "locked": False,
    "thresholds": [50, 75, 90, 95, 100],
    "boost_total": 0.0,
}

# ---------------------------------------------------------------------------
# Tool states (enable/disable/block/rate-limit)
# ---------------------------------------------------------------------------
_tools_lock = threading.Lock()
_tool_states: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Model states
# ---------------------------------------------------------------------------
_models_lock = threading.Lock()
_model_states: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Policy state
# ---------------------------------------------------------------------------
_policy_lock = threading.Lock()
_policy_state: Dict[str, Any] = {
    "locked": False,
    "version": 1,
    "preset": "balanced",
    "history": [],
    "yaml": (
        "# AgentSentinel Policy\n"
        "daily_budget: 10.0\n"
        "hourly_budget: 2.0\n"
        "require_approval_for:\n"
        "  - delete_file\n"
        "  - send_email\n"
        "  - execute_code\n"
        "blocked_tools: []\n"
        "rate_limits:\n"
        "  search_web: 20/min\n"
        "  read_file: 60/min\n"
        "security:\n"
        "  pii_detection: true\n"
        "  network_controls: true\n"
    ),
}

# ---------------------------------------------------------------------------
# Approval settings
# ---------------------------------------------------------------------------
_approval_settings_lock = threading.Lock()
_approval_settings: Dict[str, Any] = {
    "preset": "balanced",
    "timeout_seconds": 60,
    "sound_enabled": True,
    "push_notifications": False,
    "auto_reject_timeout": 60,
}

# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
_notifications_lock = threading.Lock()
_notifications: Dict[str, Dict[str, Any]] = {}
_notification_settings: Dict[str, Any] = {
    "approval_needed": True,
    "budget_warning": True,
    "rate_limit": True,
    "security_block": True,
    "info": True,
    "sound_enabled": True,
    "push_enabled": False,
    "email_digest": "off",
    "slack_enabled": False,
    "dnd_mode": False,
}


def _finite_or_none(value: float) -> "float | None":
    """Return *value* if finite, else ``None`` (for JSON serialisation)."""
    return value if value != _INF else None


def _collect_model_costs(guard: Any) -> List[Dict[str, Any]]:
    """Build a JSON-serialisable list of per-model cost stats from *guard*."""
    try:
        tracker = guard.cost_tracker
        all_usage = tracker.get_all_usage()
        budgets = tracker.config.model_budgets

        result = []
        for model_name, usage in all_usage.items():
            # Find matching budget if any
            budget = None
            for pattern, bud in budgets.items():
                if fnmatch.fnmatch(model_name.lower(), pattern.lower()):
                    budget = bud
                    break

            with _models_lock:
                mstate = _model_states.get(model_name, {})

            result.append({
                "model": model_name,
                "calls": usage.call_count,
                "input_tokens": usage.total_input_tokens,
                "output_tokens": usage.total_output_tokens,
                "cost": round(usage.total_cost, 6),
                "budget": budget,
                "enabled": mstate.get("enabled", True),
                "budget_override": mstate.get("budget_override"),
            })

        return sorted(result, key=lambda x: x["cost"], reverse=True)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Stats helper — reads events from the guard's InMemoryAuditSink (if any)
# ---------------------------------------------------------------------------

def _collect_stats(guard: Any) -> Dict[str, Any]:
    """Build a JSON-serialisable stats dict from *guard*."""
    events: List[Any] = []

    # Try to find an InMemoryAuditSink attached to the guard's audit logger.
    try:
        for sink in guard.audit_logger._sinks:
            if hasattr(sink, "events"):
                events = sink.events
                break
    except Exception:
        pass

    total = len(events)
    allowed = sum(1 for e in events if e.decision == "allowed")
    blocked = sum(1 for e in events if e.status == "blocked")
    total_cost = sum(e.cost for e in events)

    # Per-tool breakdown
    tool_counts: Dict[str, Dict[str, Any]] = {}
    for e in events:
        entry = tool_counts.setdefault(
            e.tool_name,
            {"name": e.tool_name, "calls": 0, "blocked": 0, "cost": 0.0},
        )
        entry["calls"] += 1
        if e.status == "blocked":
            entry["blocked"] += 1
        entry["cost"] += e.cost

    # Merge tool states into breakdown
    with _tools_lock:
        for tname, tdata in tool_counts.items():
            state = _tool_states.get(tname, {})
            tdata["enabled"] = state.get("enabled", True)
            tdata["blocked_perm"] = state.get("blocked", False)
            tdata["require_approval"] = state.get("require_approval", False)
            tdata["rate_limit"] = state.get("rate_limit", "unlimited")
            tdata["note"] = state.get("note", "")

    # Recent events (last 50, newest first)
    recent = []
    for e in reversed(events[-50:]):
        recent.append(
            {
                "timestamp": e.timestamp,
                "tool_name": e.tool_name,
                "status": e.status,
                "decision": e.decision,
                "cost": e.cost,
            }
        )

    # History & trends
    history = _collect_history(events)
    trends = _collect_trends(events)

    # Decision breakdown for pie chart
    decision_counts: Dict[str, int] = {}
    for e in events:
        decision_counts[e.decision] = decision_counts.get(e.decision, 0) + 1

    # Budget state
    with _budget_lock:
        daily_override = _budget_state.get("daily_override")
        hourly_override = _budget_state.get("hourly_override")
        budget_locked = _budget_state.get("locked", False)
        boost_total = _budget_state.get("boost_total", 0.0)

    daily_budget = daily_override if daily_override is not None else _finite_or_none(guard.policy.daily_budget)
    hourly_budget = hourly_override if hourly_override is not None else _finite_or_none(guard.policy.hourly_budget)

    # Agent state
    with _agent_state_lock:
        agent_status = _agent_state.get("status", "running")
        agent_locked = _agent_state.get("locked", False)
        uptime_start = _agent_state.get("uptime_start", time.time())
        last_activity = _agent_state.get("last_activity", time.time())

    return {
        "total": total,
        "allowed": allowed,
        "blocked": blocked,
        "total_cost": round(total_cost, 6),
        "daily_spent": round(getattr(guard, "daily_spent", 0.0), 6),
        "hourly_spent": round(getattr(guard, "hourly_spent", 0.0), 6),
        "daily_budget": daily_budget,
        "hourly_budget": hourly_budget,
        "budget_boost": boost_total,
        "budget_locked": budget_locked,
        "tools": list(tool_counts.values()),
        "recent_events": recent,
        "server_time": time.time(),
        "model_costs": _collect_model_costs(guard),
        "history": history,
        "trends": trends,
        "decision_breakdown": decision_counts,
        "agent_status": agent_status,
        "agent_locked": agent_locked,
        "agent_uptime": int(time.time() - uptime_start),
        "agent_last_activity": last_activity,
    }


def _collect_history(events: List[Any], buckets: int = 24) -> Dict[str, Any]:
    """Build time-series data bucketed by hour (last 24 h by default)."""
    now = time.time()
    window = buckets * 3600  # seconds
    start = now - window
    bucket_size = window / buckets

    timestamps: List[float] = []
    costs: List[float] = [0.0] * buckets
    allowed_counts: List[int] = [0] * buckets
    blocked_counts: List[int] = [0] * buckets

    for i in range(buckets):
        timestamps.append(start + i * bucket_size)

    for e in events:
        ts = getattr(e, "timestamp", 0)
        if ts < start:
            continue
        idx = int((ts - start) / bucket_size)
        if 0 <= idx < buckets:
            costs[idx] += e.cost
            if getattr(e, "status", "") == "blocked":
                blocked_counts[idx] += 1
            else:
                allowed_counts[idx] += 1

    # Token usage per model (last 24h)
    token_models: Dict[str, Dict[str, int]] = {}
    for e in events:
        ts = getattr(e, "timestamp", 0)
        if ts < start:
            continue
        model = getattr(e, "model", None) or "unknown"
        if model not in token_models:
            token_models[model] = {"input": 0, "output": 0}
        token_models[model]["input"] += getattr(e, "input_tokens", 0)
        token_models[model]["output"] += getattr(e, "output_tokens", 0)

    return {
        "timestamps": [round(t) for t in timestamps],
        "costs": [round(c, 6) for c in costs],
        "allowed_counts": allowed_counts,
        "blocked_counts": blocked_counts,
        "token_models": token_models,
    }


def _collect_trends(events: List[Any]) -> Dict[str, Any]:
    """Compute trend metrics."""
    now = time.time()
    recent_window = 300  # 5 minutes

    recent_events = [e for e in events if getattr(e, "timestamp", 0) > now - recent_window]
    event_rate = len(recent_events) / (recent_window / 60) if recent_events else 0.0

    total = len(events)
    blocked = sum(1 for e in events if e.status == "blocked")
    block_rate = (blocked / total * 100) if total else 0.0

    # Cost change % — compare last hour vs previous hour
    last_hour_cost = sum(e.cost for e in events if getattr(e, "timestamp", 0) > now - 3600)
    prev_hour_cost = sum(
        e.cost for e in events
        if now - 7200 < getattr(e, "timestamp", 0) <= now - 3600
    )
    cost_change_pct = 0.0
    if prev_hour_cost > 0:
        cost_change_pct = round(((last_hour_cost - prev_hour_cost) / prev_hour_cost) * 100, 1)

    # Cost per minute
    cost_per_min = (last_hour_cost / 60) if last_hour_cost else 0.0

    return {
        "cost_change_pct": cost_change_pct,
        "event_rate_per_min": round(event_rate, 1),
        "block_rate_pct": round(block_rate, 1),
        "cost_per_min": round(cost_per_min, 6),
    }


def _collect_events_page(
    events: List[Any],
    page: int = 1,
    page_size: int = 50,
    search: str = "",
    tool_filter: str = "",
    decision_filter: str = "",
    status_filter: str = "",
    sort_by: str = "time",
    sort_dir: str = "desc",
) -> Dict[str, Any]:
    """Return a paginated, filtered, sorted slice of audit events."""
    filtered = []
    for e in events:
        if tool_filter and getattr(e, "tool_name", "") != tool_filter:
            continue
        if decision_filter and getattr(e, "decision", "") != decision_filter:
            continue
        if status_filter and getattr(e, "status", "") != status_filter:
            continue
        if search:
            sl = search.lower()
            if (
                sl not in getattr(e, "tool_name", "").lower()
                and sl not in getattr(e, "decision", "").lower()
                and sl not in getattr(e, "status", "").lower()
            ):
                continue
        filtered.append(e)

    # Sort
    reverse = sort_dir == "desc"
    if sort_by == "cost":
        filtered.sort(key=lambda x: x.cost, reverse=reverse)
    elif sort_by == "tool":
        filtered.sort(key=lambda x: x.tool_name, reverse=reverse)
    else:
        filtered.sort(key=lambda x: getattr(x, "timestamp", 0), reverse=reverse)

    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    page_events = filtered[start:end]

    rows = []
    for e in page_events:
        rows.append({
            "timestamp": getattr(e, "timestamp", 0),
            "tool_name": getattr(e, "tool_name", ""),
            "status": getattr(e, "status", ""),
            "decision": getattr(e, "decision", ""),
            "cost": getattr(e, "cost", 0.0),
            "model": getattr(e, "model", None),
        })

    return {
        "events": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


def _seed_demo_alerts(guard: Any) -> None:
    """Populate demo alerts based on current guard state."""
    with _alerts_lock:
        if _alerts:
            return  # already seeded

        spent = getattr(guard, "daily_spent", 0.0)
        budget = _finite_or_none(guard.policy.daily_budget)

        if budget and spent / budget >= 0.8:
            aid = str(uuid.uuid4())[:8]
            _alerts[aid] = {
                "id": aid,
                "type": "budget_warning",
                "severity": "high",
                "title": "Budget Warning",
                "message": f"Daily budget {round(spent / budget * 100)}% used (${spent:.4f} / ${budget:.2f})",
                "timestamp": time.time(),
                "dismissed": False,
                "snoozed": False,
            }

        rate_limit_aid = str(uuid.uuid4())[:8]
        _alerts[rate_limit_aid] = {
            "id": rate_limit_aid,
            "type": "rate_limit_breach",
            "severity": "medium",
            "title": "Rate Limit Breach",
            "message": "Tool 'search_web' hit its rate limit (20/min). Some requests blocked.",
            "timestamp": time.time() - 120,
            "dismissed": False,
            "snoozed": False,
        }


def _seed_demo_approvals(guard: Any) -> None:
    """Populate demo approval requests."""
    with _approvals_lock:
        if _approvals:
            return  # already seeded

        for tool, action, cost_est in [
            ("delete_file", "delete: /data/report-archive.csv", 0.0),
            ("send_email", "Email: Board summary to all@company.com", 0.002),
            ("execute_code", "run: data_analysis_script.py", 0.005),
        ]:
            aid = str(uuid.uuid4())[:8]
            _approvals[aid] = {
                "id": aid,
                "tool_name": tool,
                "action": action,
                "args": {"command": action},
                "agent_id": "agent-1",
                "timestamp": time.time() - 30,
                "status": "pending",
                "cost_estimate": cost_est,
            }


def _seed_demo_agents() -> None:
    """Populate demo agents."""
    with _agents_lock:
        if _agents:
            return

        for agent_id, nickname, status in [
            ("agent-1", "Primary Agent", "active"),
            ("agent-2", "Research Bot", "idle"),
            ("agent-3", "Code Assistant", "error"),
        ]:
            _agents[agent_id] = {
                "id": agent_id,
                "nickname": nickname,
                "status": status,
                "connected": status != "error",
                "registered": time.time() - 3600,
                "last_seen": time.time() - (0 if status == "active" else 300),
                "unread": 0 if status == "idle" else (3 if status == "active" else 1),
                "pinned": agent_id == "agent-1",
            }


def _seed_demo_notifications() -> None:
    """Populate demo notifications."""
    with _notifications_lock:
        if _notifications:
            return

        items = [
            ("approval_needed", "yellow", "Approval Required", "Tool 'delete_file' needs your approval", 30),
            ("budget_warning", "red", "Budget Alert", "Daily budget 85% consumed ($8.50 / $10.00)", 120),
            ("rate_limit", "orange", "Rate Limit Hit", "search_web exceeded 20/min limit — 5 requests queued", 300),
            ("info", "gray", "Agent Connected", "agent-2 (Research Bot) connected successfully", 600),
            ("security_block", "red", "Security Block", "PII detected in tool arguments for 'send_email'", 900),
        ]
        for ntype, _color, title, msg, age in items:
            nid = str(uuid.uuid4())[:8]
            _notifications[nid] = {
                "id": nid,
                "type": ntype,
                "title": title,
                "message": msg,
                "timestamp": time.time() - age,
                "read": age > 400,
                "dismissed": False,
                "snoozed_until": None,
            }


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

def _make_handler(guard: Any):  # type: ignore[return]
    """Return a BaseHTTPRequestHandler subclass bound to *guard*."""

    class _DashboardHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path in ("/", "/index.html"):
                self._serve_index()
            elif path == "/admin":
                # Redirect to the canonical URL with a trailing slash so that
                # relative asset references in index.html (e.g. ./css/admin.css)
                # resolve to /admin/css/admin.css instead of /css/admin.css.
                self.send_response(301)
                self.send_header("Location", "/admin/")
                self.send_header("Content-Length", "0")
                self._add_cors()
                self.end_headers()
            elif path in ("/admin/", "/admin/index.html"):
                self._serve_admin_index()
            elif path.startswith("/admin/"):
                self._serve_admin_static(path[len("/admin/"):])
            elif path == "/api/debug/static-status":
                self._serve_debug_static_status()
            elif path == "/api/stats":
                self._serve_stats()
            elif path == "/api/stats/history":
                self._serve_history(qs)
            elif path == "/api/events":
                self._serve_events(qs)
            elif path == "/api/approvals":
                self._serve_approvals()
            elif path == "/api/approvals/settings":
                self._serve_approval_settings()
            elif path == "/api/alerts":
                self._serve_alerts(guard)
            # Agents
            elif path == "/api/agents":
                self._serve_agents()
            elif path.startswith("/api/agents/"):
                parts = path.split("/")
                if len(parts) == 4:
                    self._serve_agent_detail(parts[3])
                elif len(parts) == 5 and parts[4] == "stats":
                    self._serve_agent_stats(parts[3])
                else:
                    self.send_error(404, "Not Found")
            # Agent runtime
            elif path == "/api/agent/status":
                self._serve_agent_status()
            # Budget
            elif path == "/api/budget":
                self._serve_budget(guard)
            elif path == "/api/budget/forecast":
                self._serve_budget_forecast(guard)
            # Tools
            elif path == "/api/tools":
                self._serve_tools(guard)
            elif path.startswith("/api/tools/") and path.endswith("/history"):
                parts = path.split("/")
                if len(parts) == 5:
                    self._serve_tool_history(parts[3])
            # Models
            elif path == "/api/models":
                self._serve_models(guard)
            # Policy
            elif path == "/api/policy":
                self._serve_policy()
            elif path == "/api/policy/history":
                self._serve_policy_history()
            elif path == "/api/policy/presets":
                self._serve_policy_presets()
            # Notifications
            elif path == "/api/notifications":
                self._serve_notifications()
            elif path == "/api/notifications/unread":
                self._serve_notifications_unread()
            elif path == "/api/notifications/settings":
                self._serve_notification_settings()
            elif path in _ADMIN_STATIC_ROOT_FILES or path.startswith(_ADMIN_STATIC_ROOT_PREFIXES):
                # Root-path alias: map /css/…, /js/…, etc. into the admin
                # static bundle.  This handles browsers that loaded the admin
                # page without a trailing slash and computed absolute paths.
                # Kept after all /api/ routes so API paths are never shadowed.
                self._serve_admin_static(path.lstrip("/"))
            else:
                self.send_error(404, "Not Found")

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            body = self._read_body()

            # Approvals
            if path == "/api/approvals/approve-all":
                self._handle_approve_all()
            elif path == "/api/approvals/reject-all":
                self._handle_reject_all()
            elif path == "/api/approvals/settings":
                self._handle_approval_settings(body)
            elif path.startswith("/api/approvals/"):
                parts = path.split("/")
                if len(parts) == 5 and parts[4] in ("approve", "reject"):
                    self._handle_approval(parts[3], parts[4], body)
                else:
                    self.send_error(404, "Not Found")
            # Alerts
            elif path.startswith("/api/alerts/"):
                parts = path.split("/")
                if len(parts) == 5 and parts[4] == "dismiss":
                    self._handle_alert_dismiss(parts[3])
                else:
                    self.send_error(404, "Not Found")
            # Agents
            elif path == "/api/agents":
                self._handle_add_agent(body)
            elif path.startswith("/api/agents/"):
                parts = path.split("/")
                if len(parts) == 5 and parts[4] == "nickname":
                    self._handle_agent_nickname(parts[3], body)
                else:
                    self.send_error(404, "Not Found")
            # Agent runtime controls
            elif path == "/api/agent/pause":
                self._handle_agent_control("pause")
            elif path == "/api/agent/resume":
                self._handle_agent_control("resume")
            elif path == "/api/agent/stop":
                self._handle_agent_control("stop")
            elif path == "/api/agent/reset":
                self._handle_agent_control("reset")
            elif path == "/api/agent/lock":
                self._handle_agent_control("lock")
            elif path == "/api/agent/unlock":
                self._handle_agent_control("unlock")
            # Budget controls
            elif path == "/api/budget/daily":
                self._handle_budget_set("daily", body)
            elif path == "/api/budget/hourly":
                self._handle_budget_set("hourly", body)
            elif path == "/api/budget/boost":
                self._handle_budget_boost(body)
            elif path == "/api/budget/lock":
                self._handle_budget_lock(True)
            elif path == "/api/budget/unlock":
                self._handle_budget_lock(False)
            elif path == "/api/budget/thresholds":
                self._handle_budget_thresholds(body)
            # Tool controls
            elif path.startswith("/api/tools/"):
                parts = path.split("/")
                if len(parts) == 5:
                    tool_name = parts[3]
                    action = parts[4]
                    self._handle_tool_action(tool_name, action, body)
                else:
                    self.send_error(404, "Not Found")
            # Model controls
            elif path.startswith("/api/models/"):
                parts = path.split("/")
                if len(parts) == 5:
                    model_name = parts[3]
                    action = parts[4]
                    self._handle_model_action(model_name, action, body)
                else:
                    self.send_error(404, "Not Found")
            # Policy
            elif path == "/api/policy":
                self._handle_policy_update(body)
            elif path == "/api/policy/validate":
                self._handle_policy_validate(body)
            elif path == "/api/policy/lock":
                self._handle_policy_lock(True)
            elif path == "/api/policy/unlock":
                self._handle_policy_lock(False)
            elif path.startswith("/api/policy/presets/"):
                parts = path.split("/")
                if len(parts) == 5:
                    self._handle_policy_preset(parts[4])
                else:
                    self.send_error(404, "Not Found")
            elif path.startswith("/api/policy/revert/"):
                parts = path.split("/")
                if len(parts) == 5:
                    self._handle_policy_revert(parts[4])
                else:
                    self.send_error(404, "Not Found")
            # Notifications
            elif path == "/api/notifications/read-all":
                self._handle_notifications_read_all()
            elif path == "/api/notifications/settings":
                self._handle_notification_settings_update(body)
            elif path.startswith("/api/notifications/"):
                parts = path.split("/")
                if len(parts) == 5:
                    nid = parts[3]
                    action = parts[4]
                    if action == "read":
                        self._handle_notification_read(nid)
                    elif action == "dismiss":
                        self._handle_notification_dismiss(nid)
                    elif action == "snooze":
                        self._handle_notification_snooze(nid, body)
                    else:
                        self.send_error(404, "Not Found")
                else:
                    self.send_error(404, "Not Found")
            else:
                self.send_error(404, "Not Found")

        def do_DELETE(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path.startswith("/api/agents/"):
                parts = path.split("/")
                if len(parts) == 4:
                    self._handle_remove_agent(parts[3])
                    return
            self.send_error(404, "Not Found")

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(200)
            self._add_cors()
            self.end_headers()

        # ------------------------------------------------------------------ #
        # Route handlers                                                       #
        # ------------------------------------------------------------------ #

        def _serve_index(self) -> None:
            try:
                with open(_INDEX_HTML, "rb") as fh:
                    content = fh.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_error(500, "Dashboard HTML not found")

        def _serve_admin_index(self) -> None:
            admin_html = os.path.join(_ADMIN_DIR, "index.html")
            try:
                with open(admin_html, "rb") as fh:
                    content = fh.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_error(404, "Admin dashboard not found")

        def _serve_admin_static(self, relative_path: str) -> None:
            # Guard against path-traversal attacks: resolve to a real path and
            # verify it sits strictly inside _ADMIN_DIR before opening anything.
            safe_base = os.path.realpath(_ADMIN_DIR)

            # Strip any leading separators that could anchor to the filesystem root.
            clean = relative_path.lstrip("/").lstrip("\\")
            requested = os.path.realpath(os.path.join(_ADMIN_DIR, clean))

            if not requested.startswith(safe_base + os.sep):
                self.send_error(403, "Forbidden")
                return

            try:
                with open(requested, "rb") as fh:
                    content = fh.read()
                # Derive MIME type from the *filename only* (not the full path)
                # to avoid leaking path information and to prevent header injection.
                basename = os.path.basename(requested)
                mime, _ = mimetypes.guess_type(basename)
                if mime is None:
                    _, ext = os.path.splitext(basename)
                    mime = _MIME_FALLBACK.get(ext.lower())
                safe_mime = (mime or "application/octet-stream").split("\n")[0].split("\r")[0]
                self.send_response(200)
                self.send_header("Content-Type", safe_mime)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_error(404, "Not Found")

        def _serve_debug_static_status(self) -> None:
            """Return a JSON summary of static-file locations and existence.

            Only active when ``AGENTSENTINEL_DEV=1`` or
            ``AGENTSENTINEL_DASHBOARD_DEBUG=1`` is set — **never** expose this
            in production as it leaks internal filesystem paths.
            """
            dev = (
                os.getenv("AGENTSENTINEL_DEV") == "1"
                or os.getenv("AGENTSENTINEL_DASHBOARD_DEBUG") == "1"
            )
            if not dev:
                self.send_error(
                    403,
                    "Forbidden - set AGENTSENTINEL_DEV=1 or "
                    "AGENTSENTINEL_DASHBOARD_DEBUG=1 to enable this endpoint",
                )
                return

            def _check(p: str) -> Dict[str, Any]:
                return {
                    "path": p,
                    "exists": os.path.exists(p),
                    "is_file": os.path.isfile(p),
                }

            admin_children: List[str] = []
            if os.path.isdir(_ADMIN_DIR):
                admin_children = sorted(os.listdir(_ADMIN_DIR))

            payload: Dict[str, Any] = {
                "_STATIC_DIR": _STATIC_DIR,
                "_ADMIN_DIR": _ADMIN_DIR,
                "static_dir_exists": os.path.isdir(_STATIC_DIR),
                "admin_dir_exists": os.path.isdir(_ADMIN_DIR),
                "key_files": [
                    _check(os.path.join(_ADMIN_DIR, "index.html")),
                    _check(os.path.join(_ADMIN_DIR, "css", "admin.css")),
                    _check(os.path.join(_ADMIN_DIR, "js", "app.js")),
                ],
                "admin_dir_children": admin_children,
            }
            data = json.dumps(payload, indent=2).encode()
            self._send_json(data)

        def _serve_stats(self) -> None:
            data = json.dumps(_collect_stats(guard), indent=2).encode()
            self._send_json(data)

        def _serve_history(self, qs: Dict[str, List[str]]) -> None:
            events: List[Any] = []
            try:
                for sink in guard.audit_logger._sinks:
                    if hasattr(sink, "events"):
                        events = sink.events
                        break
            except Exception:
                pass

            range_param = (qs.get("range") or ["24h"])[0]
            range_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}
            hours = range_map.get(range_param, 24)
            buckets = min(hours, 24) if hours <= 24 else 28

            data = json.dumps(_collect_history(events, buckets=buckets), indent=2).encode()
            self._send_json(data)

        def _serve_events(self, qs: Dict[str, List[str]]) -> None:
            events: List[Any] = []
            try:
                for sink in guard.audit_logger._sinks:
                    if hasattr(sink, "events"):
                        events = sink.events
                        break
            except Exception:
                pass

            page = int((qs.get("page") or ["1"])[0])
            page_size = min(200, int((qs.get("page_size") or ["50"])[0]))
            search = (qs.get("search") or [""])[0]
            tool_filter = (qs.get("tool") or [""])[0]
            decision_filter = (qs.get("decision") or [""])[0]
            status_filter = (qs.get("status") or [""])[0]
            sort_by = (qs.get("sort_by") or ["time"])[0]
            sort_dir = (qs.get("sort_dir") or ["desc"])[0]

            result = _collect_events_page(
                events,
                page=page,
                page_size=page_size,
                search=search,
                tool_filter=tool_filter,
                decision_filter=decision_filter,
                status_filter=status_filter,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
            data = json.dumps(result, indent=2).encode()
            self._send_json(data)

        def _serve_approvals(self) -> None:
            _seed_demo_approvals(guard)
            with _approvals_lock:
                pending = [a for a in _approvals.values() if a["status"] == "pending"]
            data = json.dumps({"approvals": pending}, indent=2).encode()
            self._send_json(data)

        def _serve_approval_settings(self) -> None:
            with _approval_settings_lock:
                data = json.dumps(_approval_settings, indent=2).encode()
            self._send_json(data)

        def _serve_alerts(self, g: Any) -> None:
            _seed_demo_alerts(g)
            with _alerts_lock:
                active = [a for a in _alerts.values() if not a.get("dismissed")]
            data = json.dumps({"alerts": active}, indent=2).encode()
            self._send_json(data)

        # --- Agents ---

        def _serve_agents(self) -> None:
            _seed_demo_agents()
            with _agents_lock:
                agents_list = list(_agents.values())
            data = json.dumps({"agents": agents_list}, indent=2).encode()
            self._send_json(data)

        def _serve_agent_detail(self, agent_id: str) -> None:
            _seed_demo_agents()
            with _agents_lock:
                agent = _agents.get(agent_id)
            if not agent:
                self.send_error(404, "Agent not found")
                return
            data = json.dumps(agent, indent=2).encode()
            self._send_json(data)

        def _serve_agent_stats(self, agent_id: str) -> None:
            _seed_demo_agents()
            stats = {
                "agent_id": agent_id,
                "total_calls": 142,
                "blocked_calls": 8,
                "total_cost": 1.234,
                "uptime_seconds": 3600,
                "approval_pending": 2,
            }
            data = json.dumps(stats, indent=2).encode()
            self._send_json(data)

        # --- Agent runtime status ---

        def _serve_agent_status(self) -> None:
            with _agent_state_lock:
                status = dict(_agent_state)
                status["uptime_seconds"] = int(time.time() - status.get("uptime_start", time.time()))
            data = json.dumps(status, indent=2).encode()
            self._send_json(data)

        # --- Budget ---

        def _serve_budget(self, g: Any) -> None:
            with _budget_lock:
                bs = dict(_budget_state)
            spent = getattr(g, "daily_spent", 0.0)
            hourly_spent = getattr(g, "hourly_spent", 0.0)
            daily_budget = bs.get("daily_override") or _finite_or_none(g.policy.daily_budget)
            hourly_budget = bs.get("hourly_override") or _finite_or_none(g.policy.hourly_budget)
            result = {
                "daily_spent": round(spent, 6),
                "hourly_spent": round(hourly_spent, 6),
                "daily_budget": daily_budget,
                "hourly_budget": hourly_budget,
                "locked": bs.get("locked", False),
                "thresholds": bs.get("thresholds", [50, 75, 90, 95, 100]),
                "boost_total": bs.get("boost_total", 0.0),
            }
            data = json.dumps(result, indent=2).encode()
            self._send_json(data)

        def _serve_budget_forecast(self, g: Any) -> None:
            spent = getattr(g, "daily_spent", 0.0)
            with _budget_lock:
                daily_budget = _budget_state.get("daily_override") or _finite_or_none(g.policy.daily_budget)
            # Simple linear forecast based on hourly spend
            hourly_spent = getattr(g, "hourly_spent", 0.0)
            forecast_daily = hourly_spent * 24
            exhausted_in = None
            if daily_budget and hourly_spent > 0:
                remaining = daily_budget - spent
                exhausted_in = int((remaining / hourly_spent) * 3600)
            data = json.dumps({
                "projected_daily_total": round(forecast_daily, 4),
                "exhausted_in_seconds": exhausted_in,
                "current_rate_per_hour": round(hourly_spent, 6),
            }, indent=2).encode()
            self._send_json(data)

        # --- Tools ---

        def _serve_tools(self, g: Any) -> None:
            """List all tools with their states."""
            # Gather tools from audit events
            events: List[Any] = []
            try:
                for sink in g.audit_logger._sinks:
                    if hasattr(sink, "events"):
                        events = sink.events
                        break
            except Exception:
                pass

            tool_map: Dict[str, Dict[str, Any]] = {}
            for e in events:
                tname = getattr(e, "tool_name", "")
                if not tname:
                    continue
                entry = tool_map.setdefault(tname, {"name": tname, "calls": 0, "blocked": 0, "cost": 0.0})
                entry["calls"] += 1
                if getattr(e, "status", "") == "blocked":
                    entry["blocked"] += 1
                entry["cost"] += getattr(e, "cost", 0.0)

            with _tools_lock:
                for tname, tdata in tool_map.items():
                    state = _tool_states.get(tname, {})
                    tdata["enabled"] = state.get("enabled", True)
                    tdata["blocked_perm"] = state.get("blocked", False)
                    tdata["require_approval"] = state.get("require_approval", False)
                    tdata["rate_limit"] = state.get("rate_limit", "unlimited")
                    tdata["note"] = state.get("note", "")
                # Also include tools that have states but no events yet
                for tname, state in _tool_states.items():
                    if tname not in tool_map:
                        tool_map[tname] = {
                            "name": tname,
                            "calls": 0,
                            "blocked": 0,
                            "cost": 0.0,
                            "enabled": state.get("enabled", True),
                            "blocked_perm": state.get("blocked", False),
                            "require_approval": state.get("require_approval", False),
                            "rate_limit": state.get("rate_limit", "unlimited"),
                            "note": state.get("note", ""),
                        }

            result = list(tool_map.values())
            result.sort(key=lambda x: x["calls"], reverse=True)
            data = json.dumps({"tools": result}, indent=2).encode()
            self._send_json(data)

        def _serve_tool_history(self, tool_name: str) -> None:
            # Return mock history for the tool
            data = json.dumps({
                "tool": tool_name,
                "history": [
                    {"ts": time.time() - i * 300, "calls": max(0, 5 - i % 3), "blocked": i % 4 == 0}
                    for i in range(24)
                ],
            }, indent=2).encode()
            self._send_json(data)

        # --- Models ---

        def _serve_models(self, g: Any) -> None:
            models = _collect_model_costs(g)
            data = json.dumps({"models": models}, indent=2).encode()
            self._send_json(data)

        # --- Policy ---

        def _serve_policy(self) -> None:
            with _policy_lock:
                data = json.dumps({
                    "yaml": _policy_state["yaml"],
                    "locked": _policy_state["locked"],
                    "version": _policy_state["version"],
                    "preset": _policy_state["preset"],
                }, indent=2).encode()
            self._send_json(data)

        def _serve_policy_history(self) -> None:
            with _policy_lock:
                data = json.dumps({"history": _policy_state["history"]}, indent=2).encode()
            self._send_json(data)

        def _serve_policy_presets(self) -> None:
            presets = {
                "permissive": {
                    "name": "Permissive",
                    "description": "Auto-approve all except blocked tools",
                    "yaml": "daily_budget: 50.0\nhourly_budget: 10.0\nrequire_approval_for: []\nblocked_tools: []\nsecurity:\n  pii_detection: false\n",
                },
                "balanced": {
                    "name": "Balanced",
                    "description": "Approve known tools, require approval for new",
                    "yaml": "daily_budget: 10.0\nhourly_budget: 2.0\nrequire_approval_for:\n  - delete_file\n  - send_email\n  - execute_code\nblocked_tools: []\nrate_limits:\n  search_web: 20/min\nsecurity:\n  pii_detection: true\n",
                },
                "strict": {
                    "name": "Strict",
                    "description": "Require approval for ALL tool calls",
                    "yaml": "daily_budget: 5.0\nhourly_budget: 1.0\nrequire_approval_for: ['*']\nblocked_tools: []\nrate_limits:\n  '*': 5/min\nsecurity:\n  pii_detection: true\n  network_controls: true\n",
                },
                "paranoid": {
                    "name": "Paranoid",
                    "description": "Require approval + full args + double confirm",
                    "yaml": "daily_budget: 2.0\nhourly_budget: 0.5\nrequire_approval_for: ['*']\nblocked_tools: []\nrate_limits:\n  '*': 1/min\nsecurity:\n  pii_detection: true\n  network_controls: true\n  double_confirm: true\n",
                },
            }
            data = json.dumps(presets, indent=2).encode()
            self._send_json(data)

        # --- Notifications ---

        def _serve_notifications(self) -> None:
            _seed_demo_notifications()
            with _notifications_lock:
                notifs = [
                    n for n in _notifications.values()
                    if not n.get("dismissed")
                    and (not n.get("snoozed_until") or n["snoozed_until"] < time.time())
                ]
            notifs.sort(key=lambda n: n["timestamp"], reverse=True)
            data = json.dumps({"notifications": notifs}, indent=2).encode()
            self._send_json(data)

        def _serve_notifications_unread(self) -> None:
            _seed_demo_notifications()
            with _notifications_lock:
                unread = sum(
                    1 for n in _notifications.values()
                    if not n.get("read") and not n.get("dismissed")
                )
            data = json.dumps({"unread": unread}, indent=2).encode()
            self._send_json(data)

        def _serve_notification_settings(self) -> None:
            data = json.dumps(_notification_settings, indent=2).encode()
            self._send_json(data)

        # ------------------------------------------------------------------ #
        # POST handlers                                                        #
        # ------------------------------------------------------------------ #

        def _handle_approval(self, approval_id: str, action: str, body: Dict[str, Any]) -> None:
            with _approvals_lock:
                if approval_id not in _approvals:
                    self.send_error(404, "Approval not found")
                    return
                _approvals[approval_id]["status"] = action + "d"  # approved / rejected
                if action == "reject" and "reason" in body:
                    _approvals[approval_id]["reject_reason"] = body["reason"]
                if action == "approve" and "duration" in body:
                    _approvals[approval_id]["approve_duration"] = body["duration"]
            # Add notification
            self._add_notification(
                "info",
                f"Request {action}d",
                f"Tool '{_approvals[approval_id]['tool_name']}' {action}d",
            )
            data = json.dumps({"ok": True, "id": approval_id, "action": action}).encode()
            self._send_json(data)

        def _handle_approve_all(self) -> None:
            count = 0
            with _approvals_lock:
                for a in _approvals.values():
                    if a["status"] == "pending":
                        a["status"] = "approved"
                        count += 1
            data = json.dumps({"ok": True, "approved": count}).encode()
            self._send_json(data)

        def _handle_reject_all(self) -> None:
            count = 0
            with _approvals_lock:
                for a in _approvals.values():
                    if a["status"] == "pending":
                        a["status"] = "rejected"
                        count += 1
            data = json.dumps({"ok": True, "rejected": count}).encode()
            self._send_json(data)

        def _handle_approval_settings(self, body: Dict[str, Any]) -> None:
            with _approval_settings_lock:
                _approval_settings.update(body)
            data = json.dumps({"ok": True, "settings": _approval_settings}).encode()
            self._send_json(data)

        def _handle_alert_dismiss(self, alert_id: str) -> None:
            with _alerts_lock:
                if alert_id not in _alerts:
                    self.send_error(404, "Alert not found")
                    return
                _alerts[alert_id]["dismissed"] = True
            data = json.dumps({"ok": True, "id": alert_id}).encode()
            self._send_json(data)

        # --- Agents ---

        def _handle_add_agent(self, body: Dict[str, Any]) -> None:
            agent_id = body.get("id") or ("agent-" + str(uuid.uuid4())[:6])
            nickname = body.get("nickname", f"Agent {agent_id}")
            with _agents_lock:
                _agents[agent_id] = {
                    "id": agent_id,
                    "nickname": nickname,
                    "status": "idle",
                    "connected": True,
                    "registered": time.time(),
                    "last_seen": time.time(),
                    "unread": 0,
                    "pinned": False,
                }
            self._add_notification("info", "Agent Connected", f"{nickname} connected")
            data = json.dumps({"ok": True, "agent": _agents[agent_id]}).encode()
            self._send_json(data)

        def _handle_remove_agent(self, agent_id: str) -> None:
            with _agents_lock:
                if agent_id not in _agents:
                    self.send_error(404, "Agent not found")
                    return
                del _agents[agent_id]
            data = json.dumps({"ok": True, "removed": agent_id}).encode()
            self._send_json(data)

        def _handle_agent_nickname(self, agent_id: str, body: Dict[str, Any]) -> None:
            with _agents_lock:
                if agent_id not in _agents:
                    self.send_error(404, "Agent not found")
                    return
                _agents[agent_id]["nickname"] = body.get("nickname", agent_id)
            data = json.dumps({"ok": True}).encode()
            self._send_json(data)

        # --- Agent runtime controls ---

        def _handle_agent_control(self, action: str) -> None:
            with _agent_state_lock:
                if action == "pause":
                    _agent_state["status"] = "paused"
                elif action == "resume":
                    _agent_state["status"] = "running"
                elif action == "stop":
                    _agent_state["status"] = "stopped"
                elif action == "reset":
                    _agent_state["uptime_start"] = time.time()
                    _agent_state["last_activity"] = time.time()
                    _agent_state["status"] = "running"
                elif action == "lock":
                    _agent_state["locked"] = True
                elif action == "unlock":
                    _agent_state["locked"] = False
                _agent_state["last_activity"] = time.time()
                status = dict(_agent_state)

            msg_map = {
                "pause": "Agent paused",
                "resume": "Agent resumed",
                "stop": "EMERGENCY STOP activated",
                "reset": "Session reset",
                "lock": "Config locked",
                "unlock": "Config unlocked",
            }
            self._add_notification("info", msg_map.get(action, action.capitalize()), f"Action: {action}")
            data = json.dumps({"ok": True, "action": action, "status": status}).encode()
            self._send_json(data)

        # --- Budget ---

        def _handle_budget_set(self, budget_type: str, body: Dict[str, Any]) -> None:
            with _budget_lock:
                if _budget_state.get("locked"):
                    data = json.dumps({"ok": False, "error": "Budget is locked"}).encode()
                    self._send_json(data)
                    return
                amount = float(body.get("amount", 0))
                if budget_type == "daily":
                    _budget_state["daily_override"] = amount
                else:
                    _budget_state["hourly_override"] = amount
            data = json.dumps({"ok": True, "type": budget_type, "amount": amount}).encode()
            self._send_json(data)

        def _handle_budget_boost(self, body: Dict[str, Any]) -> None:
            with _budget_lock:
                if _budget_state.get("locked"):
                    data = json.dumps({"ok": False, "error": "Budget is locked"}).encode()
                    self._send_json(data)
                    return
                amount = float(body.get("amount", 5.0))
                _budget_state["boost_total"] = _budget_state.get("boost_total", 0.0) + amount
                if _budget_state.get("daily_override") is not None:
                    _budget_state["daily_override"] = (_budget_state["daily_override"] or 0) + amount
            self._add_notification("info", "Budget Boosted", f"Added ${amount:.2f} to budget")
            data = json.dumps({"ok": True, "boosted": amount, "boost_total": _budget_state["boost_total"]}).encode()
            self._send_json(data)

        def _handle_budget_lock(self, lock: bool) -> None:
            with _budget_lock:
                _budget_state["locked"] = lock
            data = json.dumps({"ok": True, "locked": lock}).encode()
            self._send_json(data)

        def _handle_budget_thresholds(self, body: Dict[str, Any]) -> None:
            with _budget_lock:
                _budget_state["thresholds"] = body.get("thresholds", [50, 75, 90, 95, 100])
            data = json.dumps({"ok": True}).encode()
            self._send_json(data)

        # --- Tools ---

        def _handle_tool_action(self, tool_name: str, action: str, body: Dict[str, Any]) -> None:
            with _tools_lock:
                state = _tool_states.setdefault(tool_name, {
                    "enabled": True, "blocked": False, "require_approval": False,
                    "rate_limit": "unlimited", "note": "",
                })
                if action == "enable":
                    state["enabled"] = True
                    state["blocked"] = False
                elif action == "disable":
                    state["enabled"] = False
                elif action == "block":
                    state["blocked"] = True
                    state["enabled"] = False
                elif action == "require-approval":
                    state["require_approval"] = True
                elif action == "remove-approval":
                    state["require_approval"] = False
                elif action == "rate-limit":
                    state["rate_limit"] = body.get("limit", "unlimited")
                elif action == "cost-override":
                    state["cost_override"] = float(body.get("cost", 0))
                elif action == "note":
                    state["note"] = body.get("note", "")
                else:
                    self.send_error(404, "Unknown tool action")
                    return

            data = json.dumps({"ok": True, "tool": tool_name, "action": action, "state": state}).encode()
            self._send_json(data)

        # --- Models ---

        def _handle_model_action(self, model_name: str, action: str, body: Dict[str, Any]) -> None:
            with _models_lock:
                state = _model_states.setdefault(model_name, {
                    "enabled": True, "budget_override": None,
                })
                if action == "enable":
                    state["enabled"] = True
                elif action == "disable":
                    state["enabled"] = False
                elif action == "budget":
                    state["budget_override"] = float(body.get("budget", 0))
                elif action == "pricing":
                    state["input_price"] = float(body.get("input_price", 0))
                    state["output_price"] = float(body.get("output_price", 0))
                elif action == "reset":
                    state["reset_at"] = time.time()
                else:
                    self.send_error(404, "Unknown model action")
                    return

            data = json.dumps({"ok": True, "model": model_name, "action": action}).encode()
            self._send_json(data)

        # --- Policy ---

        def _handle_policy_update(self, body: Dict[str, Any]) -> None:
            with _policy_lock:
                if _policy_state.get("locked"):
                    data = json.dumps({"ok": False, "error": "Policy is locked"}).encode()
                    self._send_json(data)
                    return
                old_yaml = _policy_state["yaml"]
                new_yaml = body.get("yaml", old_yaml)
                _policy_state["history"].insert(0, {
                    "version": _policy_state["version"],
                    "timestamp": time.time(),
                    "yaml": old_yaml,
                })
                _policy_state["history"] = _policy_state["history"][:20]
                _policy_state["yaml"] = new_yaml
                _policy_state["version"] += 1
            self._add_notification("info", "Policy Updated", f"Policy v{_policy_state['version']} applied")
            data = json.dumps({"ok": True, "version": _policy_state["version"]}).encode()
            self._send_json(data)

        def _handle_policy_validate(self, body: Dict[str, Any]) -> None:
            yaml_content = body.get("yaml", "")
            errors: List[str] = []
            # Prefer PyYAML for proper syntax checking
            try:
                import yaml  # type: ignore[import]
                try:
                    yaml.safe_load(yaml_content)
                except yaml.YAMLError as exc:
                    errors.append(str(exc))
            except ImportError:
                # Fallback: basic structural checks without PyYAML
                if yaml_content.strip() and not yaml_content.strip().startswith("#"):
                    for line in yaml_content.splitlines():
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#"):
                            if ":" not in stripped and not stripped.startswith("-"):
                                errors.append(f"Invalid YAML syntax near: {stripped[:40]!r}")
                                break
            # Type-check known numeric fields
            if not errors:
                for field in ("daily_budget", "hourly_budget"):
                    for line in yaml_content.splitlines():
                        if line.strip().startswith(f"{field}:"):
                            try:
                                float(line.split(":", 1)[1].strip())
                            except (ValueError, IndexError):
                                errors.append(f"Invalid numeric value for {field}")
            data = json.dumps({"valid": len(errors) == 0, "errors": errors}).encode()
            self._send_json(data)

        def _handle_policy_lock(self, lock: bool) -> None:
            with _policy_lock:
                _policy_state["locked"] = lock
            data = json.dumps({"ok": True, "locked": lock}).encode()
            self._send_json(data)

        def _handle_policy_preset(self, preset_name: str) -> None:
            presets: Dict[str, str] = {
                "permissive": "daily_budget: 50.0\nhourly_budget: 10.0\nrequire_approval_for: []\nblocked_tools: []\nsecurity:\n  pii_detection: false\n",
                "balanced": "daily_budget: 10.0\nhourly_budget: 2.0\nrequire_approval_for:\n  - delete_file\n  - send_email\n  - execute_code\nblocked_tools: []\nrate_limits:\n  search_web: 20/min\nsecurity:\n  pii_detection: true\n",
                "strict": "daily_budget: 5.0\nhourly_budget: 1.0\nrequire_approval_for: ['*']\nblocked_tools: []\nrate_limits:\n  '*': 5/min\nsecurity:\n  pii_detection: true\n  network_controls: true\n",
                "paranoid": "daily_budget: 2.0\nhourly_budget: 0.5\nrequire_approval_for: ['*']\nblocked_tools: []\nrate_limits:\n  '*': 1/min\nsecurity:\n  pii_detection: true\n  network_controls: true\n  double_confirm: true\n",
            }
            if preset_name not in presets:
                self.send_error(404, "Preset not found")
                return
            with _policy_lock:
                if _policy_state.get("locked"):
                    data = json.dumps({"ok": False, "error": "Policy is locked"}).encode()
                    self._send_json(data)
                    return
                _policy_state["yaml"] = presets[preset_name]
                _policy_state["preset"] = preset_name
                _policy_state["version"] += 1
            self._add_notification("info", "Preset Applied", f"Policy preset '{preset_name}' applied")
            data = json.dumps({"ok": True, "preset": preset_name}).encode()
            self._send_json(data)

        def _handle_policy_revert(self, version_str: str) -> None:
            with _policy_lock:
                try:
                    version = int(version_str)
                except ValueError:
                    self.send_error(400, "Invalid version")
                    return
                hist = _policy_state.get("history", [])
                match = next((h for h in hist if h.get("version") == version), None)
                if not match:
                    self.send_error(404, "Version not found")
                    return
                _policy_state["yaml"] = match["yaml"]
                _policy_state["version"] += 1
            data = json.dumps({"ok": True, "reverted_to": version}).encode()
            self._send_json(data)

        # --- Notifications ---

        def _handle_notification_read(self, nid: str) -> None:
            with _notifications_lock:
                if nid in _notifications:
                    _notifications[nid]["read"] = True
            data = json.dumps({"ok": True}).encode()
            self._send_json(data)

        def _handle_notifications_read_all(self) -> None:
            with _notifications_lock:
                for n in _notifications.values():
                    n["read"] = True
            data = json.dumps({"ok": True}).encode()
            self._send_json(data)

        def _handle_notification_dismiss(self, nid: str) -> None:
            with _notifications_lock:
                if nid in _notifications:
                    _notifications[nid]["dismissed"] = True
                    _notifications[nid]["read"] = True
            data = json.dumps({"ok": True}).encode()
            self._send_json(data)

        def _handle_notification_snooze(self, nid: str, body: Dict[str, Any]) -> None:
            minutes = int(body.get("minutes", 15))
            with _notifications_lock:
                if nid in _notifications:
                    _notifications[nid]["snoozed_until"] = time.time() + minutes * 60
                    _notifications[nid]["read"] = True
            data = json.dumps({"ok": True, "snoozed_until": time.time() + minutes * 60}).encode()
            self._send_json(data)

        def _handle_notification_settings_update(self, body: Dict[str, Any]) -> None:
            _notification_settings.update(body)
            data = json.dumps({"ok": True}).encode()
            self._send_json(data)

        # ------------------------------------------------------------------ #
        # Helpers                                                              #
        # ------------------------------------------------------------------ #

        def _add_notification(self, ntype: str, title: str, message: str) -> None:
            nid = str(uuid.uuid4())[:8]
            with _notifications_lock:
                _notifications[nid] = {
                    "id": nid,
                    "type": ntype,
                    "title": title,
                    "message": message,
                    "timestamp": time.time(),
                    "read": False,
                    "dismissed": False,
                    "snoozed_until": None,
                }

        def _read_body(self) -> Dict[str, Any]:
            """Read and parse JSON body, return empty dict on failure."""
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length > 0:
                    raw = self.rfile.read(length)
                    return json.loads(raw.decode("utf-8"))  # type: ignore[no-any-return]
            except json.JSONDecodeError as exc:
                import sys
                print(f"[AgentSentinel] JSON parse error in request body: {exc}", file=sys.stderr)
            except Exception as exc:
                import sys
                print(f"[AgentSentinel] Error reading request body: {exc}", file=sys.stderr)
            return {}

        def _send_json(self, data: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self._add_cors()
            self.end_headers()
            self.wfile.write(data)

        def _add_cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def log_message(self, *_args: object) -> None:
            pass  # suppress request logs to keep console clean

    return _DashboardHandler


# ---------------------------------------------------------------------------
# DashboardServer
# ---------------------------------------------------------------------------

class DashboardServer:
    """HTTP server that serves the AgentSentinel real-time dashboard.

    Parameters
    ----------
    guard:
        The :class:`.AgentGuard` instance to monitor.  The guard must have
        an :class:`.InMemoryAuditSink` attached to see live events.
    port:
        TCP port to bind.  Defaults to ``8080``.
    host:
        Interface to bind.  Defaults to ``"localhost"``.

    Example
    -------
    ::

        server = DashboardServer(guard, port=8080)
        # Serve in background:
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        print("Dashboard at http://localhost:8080")
        # … run your agent …
        server.shutdown()
    """

    def __init__(
        self,
        guard: Any,
        port: int = 8080,
        host: str = "localhost",
    ) -> None:
        self.guard = guard
        self.port = port
        self.host = host
        handler_class = _make_handler(guard)
        self._server = http.server.HTTPServer((host, port), handler_class)

    def serve_forever(self) -> None:
        """Block and serve requests until :meth:`shutdown` is called."""
        print(f"[AgentSentinel] Dashboard running at http://{self.host}:{self.port}")
        self._server.serve_forever()

    def shutdown(self) -> None:
        """Stop the server."""
        self._server.shutdown()

    def serve_in_background(self) -> threading.Thread:
        """Start serving in a daemon thread and return that thread."""
        t = threading.Thread(target=self.serve_forever, daemon=True)
        t.start()
        return t


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def _is_dev_mode() -> bool:
    """Return ``True`` when ``AGENTSENTINEL_DEV=1`` is set in the environment.

    This activates the local-development licence-gate bypass so that the
    dashboard can be started without a paid licence key.  It has **no effect**
    in production (i.e. when the environment variable is absent or set to any
    value other than ``"1"``).
    """
    return os.getenv("AGENTSENTINEL_DEV") == "1"


def start_dashboard(
    guard: Any,
    port: int = 8080,
    *,
    host: str = "localhost",
    background: bool = False,
) -> Optional[DashboardServer]:
    """Create and start the AgentSentinel dashboard.

    Parameters
    ----------
    guard:
        The :class:`.AgentGuard` to monitor.
    port:
        Port to bind.  Defaults to ``8080``.
    host:
        Interface to bind.  Defaults to ``"localhost"``.
    background:
        When ``True``, start the server in a daemon thread and return the
        :class:`DashboardServer` immediately (non-blocking).
        When ``False`` (the default), block until Ctrl-C.

    Returns
    -------
    :class:`DashboardServer` when *background* is ``True``, else ``None``
    (returns only when the server is stopped).

    Example
    -------
    ::

        # Blocking (use at end of script)
        start_dashboard(guard)

        # Non-blocking (continue running your agent in the same process)
        server = start_dashboard(guard, port=8080, background=True)
    """
    from agentsentinel.licensing import require_feature, FeatureNotAvailableError

    if _is_dev_mode():
        print(
            "\n⚠️  [AgentSentinel] DEV MODE ACTIVE — licence check bypassed "
            "(AGENTSENTINEL_DEV=1).  Do NOT use this setting in production.\n"
        )
    else:
        try:
            require_feature("dashboard")
        except FeatureNotAvailableError as e:
            print(f"\n⚠️  {e}\n")
            print("The dashboard is available in Pro, Team, and Enterprise plans.")
            print("Start your free trial at https://agentsentinel.net/pricing\n")
            return None

    server = DashboardServer(guard, port=port, host=host)
    if background:
        server.serve_in_background()
        return server
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[AgentSentinel] Dashboard stopped.")
    return None
