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
# 6. Admin dashboard static asset routes (no 404s)
# ---------------------------------------------------------------------------


def _make_guard():
    """Return a minimal mock guard suitable for DashboardServer."""
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


def _http_get(port, path, follow_redirects=True):
    """Perform a GET request against the ephemeral server and return (status, headers, body)."""
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    status = resp.status
    headers = dict(resp.getheaders())
    body = resp.read()
    conn.close()
    if follow_redirects and status in (301, 302, 303, 307, 308):
        location = headers.get("Location", "")
        if location.startswith("/"):
            return _http_get(port, location, follow_redirects=True)
    return status, headers, body


@pytest.fixture()
def live_server(monkeypatch):
    """Start a DashboardServer on an ephemeral port and yield (server, port)."""
    monkeypatch.setenv("AGENTSENTINEL_DEV", "1")
    from agentsentinel.dashboard.server import start_dashboard

    guard = _make_guard()
    server = start_dashboard(guard, port=0, host="127.0.0.1", background=True)
    assert server is not None
    time.sleep(0.15)  # let the background thread start accepting
    port = server._server.server_address[1]
    yield server, port
    server.shutdown()


def test_admin_root_redirects_to_slash(live_server):
    """/admin (no trailing slash) redirects to /admin/."""
    import http.client
    server, port = live_server
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/admin")
    resp = conn.getresponse()
    resp.read()
    conn.close()
    assert resp.status in (301, 302, 307, 308), (
        f"Expected redirect from /admin but got HTTP {resp.status}"
    )
    location = dict(resp.getheaders()).get("Location", "")
    assert location == "/admin/", f"Expected Location: /admin/ but got {location!r}"


def test_admin_slash_returns_html(live_server):
    """/admin/ returns HTTP 200 with HTML content."""
    server, port = live_server
    status, headers, body = _http_get(port, "/admin/", follow_redirects=False)
    assert status == 200, f"GET /admin/ returned HTTP {status}"
    ct = headers.get("Content-Type", "")
    assert "text/html" in ct, f"Expected text/html for /admin/, got {ct!r}"


def test_admin_css_returns_200_with_correct_mime(live_server):
    """/admin/css/admin.css returns 200 with Content-Type: text/css."""
    server, port = live_server
    status, headers, body = _http_get(port, "/admin/css/admin.css", follow_redirects=False)
    assert status == 200, f"GET /admin/css/admin.css returned HTTP {status}"
    ct = headers.get("Content-Type", "")
    assert "text/css" in ct, f"Expected text/css, got {ct!r}"


def test_admin_js_returns_200_with_correct_mime(live_server):
    """/admin/js/app.js returns 200 with Content-Type: application/javascript."""
    server, port = live_server
    status, headers, body = _http_get(port, "/admin/js/app.js", follow_redirects=False)
    assert status == 200, f"GET /admin/js/app.js returned HTTP {status}"
    ct = headers.get("Content-Type", "")
    assert "javascript" in ct, f"Expected application/javascript, got {ct!r}"


def test_admin_via_redirect_loads_assets(live_server):
    """GET /admin follows redirect and ultimately serves index.html."""
    server, port = live_server
    status, headers, body = _http_get(port, "/admin", follow_redirects=True)
    assert status == 200, f"GET /admin (after redirect) returned HTTP {status}"


def test_root_path_alias_css(live_server):
    """Root-path alias /css/admin.css is served from admin static bundle."""
    server, port = live_server
    status, headers, body = _http_get(port, "/css/admin.css", follow_redirects=False)
    assert status == 200, f"GET /css/admin.css (root alias) returned HTTP {status}"
    ct = headers.get("Content-Type", "")
    assert "text/css" in ct, f"Expected text/css for /css/admin.css, got {ct!r}"


def test_root_path_alias_js(live_server):
    """Root-path alias /js/app.js is served from admin static bundle."""
    server, port = live_server
    status, headers, body = _http_get(port, "/js/app.js", follow_redirects=False)
    assert status == 200, f"GET /js/app.js (root alias) returned HTTP {status}"
    ct = headers.get("Content-Type", "")
    assert "javascript" in ct, f"Expected application/javascript for /js/app.js, got {ct!r}"


def test_debug_static_status_dev_mode(live_server):
    """/api/debug/static-status returns 200 JSON in dev mode."""
    import json as _json
    server, port = live_server
    status, headers, body = _http_get(port, "/api/debug/static-status", follow_redirects=False)
    assert status == 200, f"GET /api/debug/static-status returned HTTP {status}"
    data = _json.loads(body)
    assert "admin_dir_exists" in data
    assert data["admin_dir_exists"] is True, "admin_dir_exists should be True"
    assert "key_files" in data
    key_files = {kf["path"].split(os.sep)[-1]: kf for kf in data["key_files"]}
    assert key_files.get("admin.css", {}).get("exists"), "admin.css should exist"
    assert key_files.get("app.js", {}).get("exists"), "app.js should exist"


def test_debug_static_status_blocked_outside_dev(monkeypatch):
    """/api/debug/static-status returns 403 when dev mode is off."""
    monkeypatch.setenv("AGENTSENTINEL_DEV", "1")  # needed for start_dashboard
    monkeypatch.delenv("AGENTSENTINEL_DASHBOARD_DEBUG", raising=False)

    from agentsentinel.dashboard.server import start_dashboard

    guard = _make_guard()
    server = start_dashboard(guard, port=0, host="127.0.0.1", background=True)
    assert server is not None
    time.sleep(0.15)
    port = server._server.server_address[1]

    # Now disable dev mode so the endpoint blocks
    monkeypatch.setenv("AGENTSENTINEL_DEV", "0")

    import http.client
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/debug/static-status")
        resp = conn.getresponse()
        resp.read()
        conn.close()
        assert resp.status == 403, (
            f"Expected 403 with dev mode off, got {resp.status}"
        )
    finally:
        server.shutdown()
