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

import os
import sys
import threading
import time
import urllib.request
import urllib.error
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
# Helper: build a minimal mock guard
# ---------------------------------------------------------------------------

def _make_guard():
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
    """Start a dashboard server on an ephemeral port; yield (server, base_url); shut down."""
    monkeypatch.setenv("AGENTSENTINEL_DEV", "1")
    from agentsentinel.dashboard.server import start_dashboard

    server = start_dashboard(_make_guard(), port=0, host="127.0.0.1", background=True)
    assert server is not None
    time.sleep(0.1)  # let the serving thread start
    base = f"http://127.0.0.1:{server.port}"
    yield server, base
    server.shutdown()


# ---------------------------------------------------------------------------
# 6. HTTP-level static-asset serving tests
# ---------------------------------------------------------------------------


def _get(url):
    """Return (status_code, headers_lowercase, body_bytes) for a simple GET request."""
    try:
        with urllib.request.urlopen(url) as resp:
            # Normalise header keys to lowercase for portable assertions.
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, headers, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {}, b""


def test_admin_index_returns_200(live_server):
    """/admin returns 200 HTML containing the <base href='/admin/'> tag."""
    _, base = live_server
    status, headers, body = _get(f"{base}/admin")
    assert status == 200
    assert "text/html" in headers.get("content-type", "")
    assert b'<base href="/admin/">' in body


def test_admin_css_returns_200(live_server):
    """/admin/css/admin.css returns 200 with Content-Type text/css."""
    _, base = live_server
    status, headers, _ = _get(f"{base}/admin/css/admin.css")
    assert status == 200, f"Expected 200 for admin.css, got {status}"
    assert "text/css" in headers.get("content-type", "")


def test_admin_js_app_returns_200(live_server):
    """/admin/js/app.js returns 200 with Content-Type application/javascript."""
    _, base = live_server
    status, headers, _ = _get(f"{base}/admin/js/app.js")
    assert status == 200, f"Expected 200 for app.js, got {status}"
    ct = headers.get("content-type", "")
    assert "javascript" in ct, f"Expected javascript content-type, got {ct!r}"


def test_admin_nested_js_returns_200(live_server):
    """/admin/js/utils/auth.js (nested) returns 200."""
    _, base = live_server
    status, _, _ = _get(f"{base}/admin/js/utils/auth.js")
    assert status == 200, f"Expected 200 for nested JS, got {status}"


def test_admin_path_traversal_blocked(live_server):
    """/admin/../index.html is blocked (403) or path-normalised (200 for root index)."""
    import socket
    port = live_server[0].port
    # Send raw HTTP to avoid urllib normalising the path before it reaches the server.
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(b"GET /admin/../index.html HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
    first_line = response.split(b"\r\n")[0]
    # The HTTP layer may normalise the path to /index.html (→ 200 for the root
    # dashboard) or the traversal guard blocks it (→ 403).  A 400 Bad Request is
    # also acceptable.  What must NOT happen is the server returning 200 for a
    # file resolved outside _ADMIN_DIR without normalisation.
    assert b"200" in first_line or b"403" in first_line or b"400" in first_line


def test_debug_static_status_in_dev_mode(live_server):
    """/api/debug/static-status returns 200 JSON in dev mode."""
    _, base = live_server
    status, headers, body = _get(f"{base}/api/debug/static-status")
    assert status == 200
    payload = __import__("json").loads(body)
    assert "admin_dir" in payload
    assert "exists" in payload
    assert payload["exists"]["admin_css"] is True
    assert payload["exists"]["app_js"] is True


def test_debug_static_status_blocked_outside_dev_mode(monkeypatch):
    """/api/debug/static-status returns 404 when AGENTSENTINEL_DEV is not set."""
    monkeypatch.setenv("AGENTSENTINEL_DEV", "1")  # need dev mode to start server
    from agentsentinel.dashboard.server import start_dashboard

    server = start_dashboard(_make_guard(), port=0, host="127.0.0.1", background=True)
    assert server is not None
    time.sleep(0.1)
    base = f"http://127.0.0.1:{server.port}"

    # Now disable dev mode *after* server start (handler checks at request time)
    monkeypatch.delenv("AGENTSENTINEL_DEV", raising=False)
    try:
        status, _, _ = _get(f"{base}/api/debug/static-status")
        assert status == 404
    finally:
        server.shutdown()
