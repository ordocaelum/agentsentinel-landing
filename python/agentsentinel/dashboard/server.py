"""Local web dashboard server for AgentSentinel.

Zero external dependencies — built on :mod:`http.server` from the stdlib.

The dashboard exposes:

* ``GET /``                            — the single-page Tailwind CSS dark-theme UI
* ``GET /api/stats``                   — JSON snapshot of all audit events
* ``GET /api/stats/history``           — time-series data for charts
* ``GET /api/events``                  — paginated events with filtering
* ``GET /api/approvals``               — pending approval requests
* ``POST /api/approvals/{id}/approve`` — approve a request
* ``POST /api/approvals/{id}/reject``  — reject a request
* ``GET /api/alerts``                  — active alerts
* ``POST /api/alerts/{id}/dismiss``    — dismiss an alert

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

_INF = float("inf")

# ---------------------------------------------------------------------------
# In-memory store for approvals and alerts (demo/mock data)
# ---------------------------------------------------------------------------
_approvals_lock = threading.Lock()
_approvals: Dict[str, Dict[str, Any]] = {}

_alerts_lock = threading.Lock()
_alerts: Dict[str, Dict[str, Any]] = {}


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

            result.append({
                "model": model_name,
                "calls": usage.call_count,
                "input_tokens": usage.total_input_tokens,
                "output_tokens": usage.total_output_tokens,
                "cost": round(usage.total_cost, 6),
                "budget": budget,
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

    return {
        "total": total,
        "allowed": allowed,
        "blocked": blocked,
        "total_cost": round(total_cost, 6),
        "daily_spent": round(getattr(guard, "daily_spent", 0.0), 6),
        "hourly_spent": round(getattr(guard, "hourly_spent", 0.0), 6),
        "daily_budget": _finite_or_none(guard.policy.daily_budget),
        "hourly_budget": _finite_or_none(guard.policy.hourly_budget),
        "tools": list(tool_counts.values()),
        "recent_events": recent,
        "server_time": time.time(),
        "model_costs": _collect_model_costs(guard),
        "history": history,
        "trends": trends,
        "decision_breakdown": decision_counts,
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

        for tool, action in [
            ("delete_file", "rm /data/important.csv"),
            ("send_email", "Email: Board summary to all@company.com"),
            ("execute_code", "subprocess.run(['rm', '-rf', '/tmp'])"),
        ]:
            aid = str(uuid.uuid4())[:8]
            _approvals[aid] = {
                "id": aid,
                "tool_name": tool,
                "action": action,
                "agent_id": "agent-1",
                "timestamp": time.time() - 30,
                "status": "pending",
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
            elif path == "/api/stats":
                self._serve_stats()
            elif path == "/api/stats/history":
                self._serve_history(qs)
            elif path == "/api/events":
                self._serve_events(qs)
            elif path == "/api/approvals":
                self._serve_approvals()
            elif path == "/api/alerts":
                self._serve_alerts(guard)
            else:
                self.send_error(404, "Not Found")

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path

            if path.startswith("/api/approvals/"):
                parts = path.split("/")
                # /api/approvals/{id}/approve  or  /api/approvals/{id}/reject
                if len(parts) == 5 and parts[4] in ("approve", "reject"):
                    self._handle_approval(parts[3], parts[4])
                else:
                    self.send_error(404, "Not Found")
            elif path.startswith("/api/alerts/"):
                parts = path.split("/")
                # /api/alerts/{id}/dismiss
                if len(parts) == 5 and parts[4] == "dismiss":
                    self._handle_alert_dismiss(parts[3])
                else:
                    self.send_error(404, "Not Found")
            else:
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

        def _serve_alerts(self, g: Any) -> None:
            _seed_demo_alerts(g)
            with _alerts_lock:
                active = [a for a in _alerts.values() if not a.get("dismissed")]
            data = json.dumps({"alerts": active}, indent=2).encode()
            self._send_json(data)

        def _handle_approval(self, approval_id: str, action: str) -> None:
            with _approvals_lock:
                if approval_id not in _approvals:
                    self.send_error(404, "Approval not found")
                    return
                _approvals[approval_id]["status"] = action + "d"  # approved / rejected
            data = json.dumps({"ok": True, "id": approval_id, "action": action}).encode()
            self._send_json(data)

        def _handle_alert_dismiss(self, alert_id: str) -> None:
            with _alerts_lock:
                if alert_id not in _alerts:
                    self.send_error(404, "Alert not found")
                    return
                _alerts[alert_id]["dismissed"] = True
            data = json.dumps({"ok": True, "id": alert_id}).encode()
            self._send_json(data)

        # ------------------------------------------------------------------ #
        # Helpers                                                              #
        # ------------------------------------------------------------------ #

        def _send_json(self, data: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self._add_cors()
            self.end_headers()
            self.wfile.write(data)

        def _add_cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
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
    server = DashboardServer(guard, port=port, host=host)
    if background:
        server.serve_in_background()
        return server
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[AgentSentinel] Dashboard stopped.")
    return None
