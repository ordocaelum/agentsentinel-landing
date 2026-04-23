# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Smoke tests for the admin dashboard CLI entry point.

These tests verify that the CLI can be imported, parsed, and that
``DashboardServer`` can be constructed and torn down without binding to a
real port in a way that lingers.

Strategy
--------
* Argument parsing and module imports are tested without touching the network.
* The ``DashboardServer`` construction test uses port ``0`` (ephemeral) so the
  OS assigns a free port; the server is shut down immediately after starting.
* ``AGENTSENTINEL_DEV=1`` is set for all tests so the licence gate is bypassed.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure dev mode is active for all tests in this module
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.usefixtures("_set_dev_mode")


@pytest.fixture(autouse=True)
def _set_dev_mode(monkeypatch):
    """Set AGENTSENTINEL_DEV=1 for every test in this module."""
    monkeypatch.setenv("AGENTSENTINEL_DEV", "1")


# ---------------------------------------------------------------------------
# 1. Module imports succeed
# ---------------------------------------------------------------------------


def test_dashboard_module_importable():
    """``agentsentinel.dashboard`` must be importable without error."""
    import agentsentinel.dashboard  # noqa: F401


def test_dashboard_main_importable():
    """The CLI entry-point module must be importable without error."""
    import agentsentinel.dashboard.__main__  # noqa: F401


def test_dashboard_server_importable():
    """``agentsentinel.dashboard.server`` must be importable without error."""
    import agentsentinel.dashboard.server  # noqa: F401


# ---------------------------------------------------------------------------
# 2. CLI argument parsing
# ---------------------------------------------------------------------------


def test_cli_parser_defaults():
    """Default CLI args resolve to port=None, host=None, background=False."""
    from agentsentinel.dashboard.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args([])
    assert args.port is None
    assert args.host is None
    assert args.background is False


def test_cli_parser_explicit_port_and_host():
    """Explicit --port and --host flags are parsed correctly."""
    from agentsentinel.dashboard.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["--port", "8080", "--host", "localhost"])
    assert args.port == 8080
    assert args.host == "localhost"


def test_cli_parser_background_flag():
    """--background flag sets background=True."""
    from agentsentinel.dashboard.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["--background"])
    assert args.background is True


# ---------------------------------------------------------------------------
# 3. main() resolves env vars without binding sockets
# ---------------------------------------------------------------------------


def test_main_defaults_port_8080(monkeypatch):
    """main() defaults to port 8080 and host localhost."""
    monkeypatch.delenv("AGENTSENTINEL_DASHBOARD_PORT", raising=False)
    monkeypatch.delenv("AGENTSENTINEL_DASHBOARD_HOST", raising=False)

    from agentsentinel.dashboard.__main__ import main

    mock_start = MagicMock(return_value=MagicMock())
    with patch("agentsentinel.dashboard.__main__.start_dashboard", mock_start), \
         patch.object(sys, "argv", ["python -m agentsentinel.dashboard"]):
        main()

    _, kwargs = mock_start.call_args
    assert kwargs["port"] == 8080
    assert kwargs["host"] == "localhost"


def test_main_explicit_port_and_host(monkeypatch):
    """main() passes --port and --host through to start_dashboard."""
    monkeypatch.delenv("AGENTSENTINEL_DASHBOARD_PORT", raising=False)
    monkeypatch.delenv("AGENTSENTINEL_DASHBOARD_HOST", raising=False)

    from agentsentinel.dashboard.__main__ import main

    mock_start = MagicMock(return_value=MagicMock())
    with patch("agentsentinel.dashboard.__main__.start_dashboard", mock_start), \
         patch.object(sys, "argv",
                      ["python -m agentsentinel.dashboard", "--port", "9090",
                       "--host", "127.0.0.1"]):
        main()

    _, kwargs = mock_start.call_args
    assert kwargs["port"] == 9090
    assert kwargs["host"] == "127.0.0.1"


# ---------------------------------------------------------------------------
# 4. Dev-mode detection
# ---------------------------------------------------------------------------


def test_is_dev_mode_true_when_set(monkeypatch):
    """_is_dev_mode() returns True when AGENTSENTINEL_DEV=1."""
    monkeypatch.setenv("AGENTSENTINEL_DEV", "1")
    from agentsentinel.dashboard.server import _is_dev_mode

    assert _is_dev_mode() is True


def test_is_dev_mode_false_by_default(monkeypatch):
    """_is_dev_mode() returns False when AGENTSENTINEL_DEV is unset."""
    monkeypatch.delenv("AGENTSENTINEL_DEV", raising=False)
    from agentsentinel.dashboard.server import _is_dev_mode

    assert _is_dev_mode() is False


# ---------------------------------------------------------------------------
# 5. start_dashboard with port=0 (ephemeral) — no-socket-hang smoke test
# ---------------------------------------------------------------------------


def test_start_dashboard_ephemeral_port(monkeypatch):
    """start_dashboard(background=True) with port=0 binds, serves, and shuts down cleanly."""
    monkeypatch.setenv("AGENTSENTINEL_DEV", "1")
    from agentsentinel.dashboard.server import start_dashboard, DashboardServer

    guard = MagicMock()
    guard.daily_spent = 0.0
    guard.hourly_spent = 0.0
    guard.policy = MagicMock(daily_budget=float("inf"), hourly_budget=float("inf"))
    guard.audit_logger = MagicMock(_sinks=[])
    guard.cost_tracker = MagicMock(
        get_all_usage=MagicMock(return_value={}),
        config=MagicMock(model_budgets={}),
    )

    server = start_dashboard(guard, port=0, host="127.0.0.1", background=True)

    assert server is not None, (
        "start_dashboard must return a DashboardServer in background mode "
        "(is AGENTSENTINEL_DEV=1 set?)"
    )

    # Give the background thread a moment to start
    time.sleep(0.1)

    # Shut down cleanly
    server.shutdown()


# ---------------------------------------------------------------------------
# 6. Regression: root-path static assets return 200
# ---------------------------------------------------------------------------


def _make_guard() -> MagicMock:
    guard = MagicMock()
    guard.daily_spent = 0.0
    guard.hourly_spent = 0.0
    guard.policy = MagicMock(daily_budget=float("inf"), hourly_budget=float("inf"))
    guard.audit_logger = MagicMock(_sinks=[])
    guard.cost_tracker = MagicMock(
        get_all_usage=MagicMock(return_value={}),
        config=MagicMock(model_budgets={}),
    )
    return guard


@pytest.fixture()
def live_server(monkeypatch):
    """Start the dashboard on an ephemeral port and yield (host, port).

    Shuts the server down after the test.
    """
    monkeypatch.setenv("AGENTSENTINEL_DEV", "1")
    from agentsentinel.dashboard.server import start_dashboard

    guard = _make_guard()
    server = start_dashboard(guard, port=0, host="127.0.0.1", background=True)
    assert server is not None
    # The OS-assigned port is available via the internal HTTPServer socket.
    port = server._server.server_address[1]
    time.sleep(0.05)
    yield "127.0.0.1", port
    server.shutdown()


def _get(host: str, port: int, path: str):
    url = f"http://{host}:{port}{path}"
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, dict(resp.headers)


def test_admin_page_returns_200(live_server):
    """/admin must return HTTP 200 with text/html content."""
    host, port = live_server
    status, headers = _get(host, port, "/admin")
    assert status == 200
    assert "text/html" in headers.get("Content-Type", "")


def test_css_admin_returns_200(live_server):
    """/css/admin.css must return HTTP 200 with text/css content-type."""
    host, port = live_server
    status, headers = _get(host, port, "/css/admin.css")
    assert status == 200
    assert "text/css" in headers.get("Content-Type", "")


def test_js_app_returns_200(live_server):
    """/js/app.js must return HTTP 200 with application/javascript content-type."""
    host, port = live_server
    status, headers = _get(host, port, "/js/app.js")
    assert status == 200
    ct = headers.get("Content-Type", "")
    assert "javascript" in ct


def test_admin_css_via_admin_prefix_returns_200(live_server):
    """/admin/css/admin.css (original prefix route) must continue to return 200."""
    host, port = live_server
    status, headers = _get(host, port, "/admin/css/admin.css")
    assert status == 200
    assert "text/css" in headers.get("Content-Type", "")


def test_debug_static_status_in_dev_mode(live_server):
    """/api/debug/static-status returns 200 JSON in dev mode."""
    host, port = live_server
    url = f"http://{host}:{port}/api/debug/static-status"
    with urllib.request.urlopen(url, timeout=5) as resp:
        status = resp.status
        body = json.loads(resp.read())
    assert status == 200
    assert "_STATIC_DIR" in body
    assert "_ADMIN_DIR" in body
    assert "key_files" in body
    assert "admin_dir_listing" in body
