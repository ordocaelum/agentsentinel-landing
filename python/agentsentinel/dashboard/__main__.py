# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Entry point for ``python -m agentsentinel.dashboard``.

Starts the admin dashboard HTTP server so that the admin SPA is accessible
at ``http://localhost:<port>/admin``.  The admin SPA is self-contained and
communicates directly with Supabase from the browser; the Python server only
serves static files.

Usage::

    python -m agentsentinel.dashboard          # port 8000
    python -m agentsentinel.dashboard 9090     # custom port
"""

from __future__ import annotations

import sys

from .server import DashboardServer


class _StubPolicy:
    """Minimal policy stub — the admin SPA talks directly to Supabase."""

    daily_budget: float = float("inf")
    hourly_budget: float = float("inf")


class _StubGuard:
    """Minimal guard stub sufficient for ``DashboardServer`` to serve static files.

    All live-data API endpoints degrade gracefully when the real guard is
    absent because the server wraps every guard attribute access in a
    ``try/except`` or ``getattr(..., default)``.
    """

    daily_spent: float = 0.0
    hourly_spent: float = 0.0
    policy = _StubPolicy()

    class _StubAuditLogger:
        _sinks: list = []

    class _StubCostTracker:
        class _Config:
            model_budgets: dict = {}

        config = _Config()

        def get_all_usage(self) -> dict:  # noqa: D102
            return {}

    audit_logger = _StubAuditLogger()
    cost_tracker = _StubCostTracker()


def main() -> None:
    """Start the dashboard server and block until Ctrl-C."""
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"[AgentSentinel] Invalid port {sys.argv[1]!r} — using 8000.", file=sys.stderr)

    guard = _StubGuard()
    server = DashboardServer(guard, port=port, host="localhost")

    print(f"[AgentSentinel] Admin dashboard → http://localhost:{port}/admin")
    print("[AgentSentinel] Press Ctrl-C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[AgentSentinel] Dashboard stopped.")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
