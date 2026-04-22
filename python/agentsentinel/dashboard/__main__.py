# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Entry point for ``python -m agentsentinel.dashboard``.

Starts the admin dashboard HTTP server so that the admin SPA is accessible
at ``http://<host>:<port>/admin``.  The admin SPA is self-contained and
communicates directly with Supabase from the browser; the Python server only
serves static files.

Usage::

    python -m agentsentinel.dashboard                     # port 8080, host localhost
    python -m agentsentinel.dashboard --port 9090         # custom port
    python -m agentsentinel.dashboard --host 0.0.0.0      # listen on all interfaces
    python -m agentsentinel.dashboard --background        # non-blocking (returns immediately)

Environment variable overrides (useful for CI/CD)::

    AGENTSENTINEL_DASHBOARD_PORT   — default port when --port is not supplied
    AGENTSENTINEL_DASHBOARD_HOST   — default host when --host is not supplied
    AGENTSENTINEL_DEV=1            — bypass the paid-licence gate (dev mode only)
"""

from __future__ import annotations

import argparse
import os
import sys

from .server import start_dashboard


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


def _build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the dashboard CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m agentsentinel.dashboard",
        description="Start the AgentSentinel admin dashboard server.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=(
            "TCP port to bind (default: %(default)s).  "
            "Falls back to AGENTSENTINEL_DASHBOARD_PORT env var, then 8080."
        ),
    )
    parser.add_argument(
        "--host",
        default=None,
        help=(
            "Interface to bind (default: localhost).  "
            "Falls back to AGENTSENTINEL_DASHBOARD_HOST env var, then localhost."
        ),
    )
    parser.add_argument(
        "--background",
        action="store_true",
        default=False,
        help="Start the server in a background thread and return immediately.",
    )
    return parser


def main() -> None:
    """Parse CLI arguments and start the dashboard server."""
    parser = _build_parser()
    args = parser.parse_args()

    # Resolve port: CLI arg → env var → default 8080
    if args.port is not None:
        port = args.port
    else:
        env_port = os.getenv("AGENTSENTINEL_DASHBOARD_PORT")
        if env_port is not None:
            try:
                port = int(env_port)
            except ValueError:
                print(
                    f"[AgentSentinel] Invalid AGENTSENTINEL_DASHBOARD_PORT value "
                    f"{env_port!r} — using 8080.",
                    file=sys.stderr,
                )
                port = 8080
        else:
            port = 8080

    # Resolve host: CLI arg → env var → default localhost
    if args.host is not None:
        host = args.host
    else:
        host = os.getenv("AGENTSENTINEL_DASHBOARD_HOST", "localhost")

    guard = _StubGuard()

    print(f"[AgentSentinel] Starting admin dashboard at http://{host}:{port}/admin")
    print("[AgentSentinel] Press Ctrl-C to stop.")

    result = start_dashboard(guard, port=port, host=host, background=args.background)

    if result is None and not args.background:
        # start_dashboard returned None in blocking mode — either finished normally
        # (KeyboardInterrupt handled inside) or the licence gate rejected the call.
        pass
    elif args.background and result is None:
        # Licence gate rejected the call — exit with non-zero status.
        sys.exit(1)


if __name__ == "__main__":
    main()
