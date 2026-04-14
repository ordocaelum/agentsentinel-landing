"""Local web dashboard server for AgentSentinel.

Zero external dependencies — built on :mod:`http.server` from the stdlib.

The dashboard exposes:

* ``GET /``        — the single-page Tailwind CSS dark-theme UI
* ``GET /api/stats`` — JSON snapshot of all audit events

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
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path to the bundled static HTML file
# ---------------------------------------------------------------------------
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_INDEX_HTML = os.path.join(_STATIC_DIR, "index.html")

_INF = float("inf")


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
    }


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

def _make_handler(guard: Any):  # type: ignore[return]
    """Return a BaseHTTPRequestHandler subclass bound to *guard*."""

    class _DashboardHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/index.html"):
                self._serve_index()
            elif self.path == "/api/stats":
                self._serve_stats()
            else:
                self.send_error(404, "Not Found")

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
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

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
