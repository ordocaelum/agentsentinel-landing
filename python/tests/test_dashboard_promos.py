# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Tests for the local promo-code API endpoints (dev mode only).

Strategy
--------
* The dashboard is started on an ephemeral port (port=0) with
  ``AGENTSENTINEL_DEV=1`` so the licence gate is bypassed.
* Each test hits the running server over HTTP and asserts the expected
  status code and JSON shape.
* A separate test verifies that all promo endpoints return 404 when
  *not* in dev mode.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Ensure dev mode is active for all tests in this module by default
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.usefixtures("_set_dev_mode")


@pytest.fixture(autouse=True)
def _set_dev_mode(monkeypatch):
    monkeypatch.setenv("AGENTSENTINEL_DEV", "1")


# ---------------------------------------------------------------------------
# Shared helpers
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
    # Reset in-memory promo store so each test starts clean.
    import agentsentinel.dashboard.server as srv
    with srv._promos_lock:
        srv._promos.clear()

    from agentsentinel.dashboard.server import start_dashboard

    guard = _make_guard()
    server = start_dashboard(guard, port=0, host="127.0.0.1", background=True)
    assert server is not None
    port = server._server.server_address[1]
    time.sleep(0.05)
    yield "127.0.0.1", port
    server.shutdown()


def _get(host: str, port: int, path: str) -> tuple[int, Any]:
    url = f"http://{host}:{port}{path}"
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


def _post(host: str, port: int, path: str, body: Dict | None = None) -> tuple[int, Any]:
    url = f"http://{host}:{port}{path}"
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _put(host: str, port: int, path: str, body: Dict) -> tuple[int, Any]:
    url = f"http://{host}:{port}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="PUT",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except Exception:
            return exc.code, {}


def _delete(host: str, port: int, path: str) -> tuple[int, Any]:
    url = f"http://{host}:{port}{path}"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except Exception:
            return exc.code, {}


# ---------------------------------------------------------------------------
# 1. List promos — seeded demo data
# ---------------------------------------------------------------------------


def test_list_promos_returns_200_and_array(live_server):
    """/api/promos returns 200 with a JSON array in dev mode."""
    host, port = live_server
    status, body = _get(host, port, "/api/promos")
    assert status == 200
    assert isinstance(body, list), f"Expected list, got {type(body)}: {body!r}"
    # Demo promos should be seeded
    assert len(body) >= 1


def test_list_promos_have_required_fields(live_server):
    """Each promo in the list has the fields the frontend expects."""
    host, port = live_server
    _, promos = _get(host, port, "/api/promos")
    for p in promos:
        for field in ("id", "code", "type", "value", "active", "used_count", "max_uses", "created_at"):
            assert field in p, f"Missing field {field!r} in promo {p.get('id')!r}"


# ---------------------------------------------------------------------------
# 2. Create promo
# ---------------------------------------------------------------------------


def test_create_promo_returns_201(live_server):
    """POST /api/promos returns 201 and the created promo object."""
    host, port = live_server
    status, body = _post(host, port, "/api/promos", {
        "code": "PYTEST10",
        "type": "discount_percent",
        "value": 10,
        "description": "pytest test promo",
    })
    assert status == 201, f"Expected 201, got {status}: {body}"
    assert body.get("ok") is True
    promo = body.get("promo", {})
    assert promo.get("code") == "PYTEST10"
    assert promo.get("type") == "discount_percent"
    assert promo.get("value") == 10.0
    assert "id" in promo


def test_create_promo_duplicate_code_returns_409(live_server):
    """Creating a promo with a duplicate code returns 409."""
    host, port = live_server
    _post(host, port, "/api/promos", {"code": "DUPCODE", "type": "discount_fixed", "value": 100})
    status, body = _post(host, port, "/api/promos", {"code": "DUPCODE", "type": "discount_fixed", "value": 100})
    assert status == 409
    assert body.get("ok") is False


def test_create_promo_missing_code_returns_400(live_server):
    """Creating a promo without 'code' returns 400."""
    host, port = live_server
    status, body = _post(host, port, "/api/promos", {"type": "discount_percent", "value": 10})
    assert status == 400
    assert body.get("ok") is False


def test_create_promo_invalid_type_returns_400(live_server):
    """Creating a promo with an unknown type returns 400."""
    host, port = live_server
    status, body = _post(host, port, "/api/promos", {
        "code": "BADTYPE", "type": "does_not_exist", "value": 5,
    })
    assert status == 400
    assert body.get("ok") is False


def test_create_promo_percent_over_100_returns_400(live_server):
    """discount_percent with value > 100 returns 400."""
    host, port = live_server
    status, body = _post(host, port, "/api/promos", {
        "code": "TOOMUCH", "type": "discount_percent", "value": 150,
    })
    assert status == 400
    assert body.get("ok") is False


# ---------------------------------------------------------------------------
# 3. Get single promo
# ---------------------------------------------------------------------------


def test_get_promo_by_id(live_server):
    """GET /api/promos/{id} returns the promo."""
    host, port = live_server
    _, promos = _get(host, port, "/api/promos")
    promo_id = promos[0]["id"]
    status, promo = _get(host, port, f"/api/promos/{promo_id}")
    assert status == 200
    assert promo["id"] == promo_id


def test_get_promo_unknown_id_returns_404(live_server):
    """GET /api/promos/nonexistent returns 404."""
    host, port = live_server
    url = f"http://{host}:{port}/api/promos/nonexistent-id"
    req = urllib.request.Request(url)
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req, timeout=5)
    assert exc_info.value.code == 404


# ---------------------------------------------------------------------------
# 4. Update promo
# ---------------------------------------------------------------------------


def test_update_promo_returns_200(live_server):
    """PUT /api/promos/{id} updates a promo and returns 200."""
    host, port = live_server
    _, create_body = _post(host, port, "/api/promos", {
        "code": "UPDATEME", "type": "trial_extension", "value": 7,
    })
    promo_id = create_body["promo"]["id"]

    status, body = _put(host, port, f"/api/promos/{promo_id}", {
        "description": "updated description",
        "active": False,
    })
    assert status == 200, f"Expected 200, got {status}: {body}"
    assert body.get("ok") is True
    updated = body.get("promo", {})
    assert updated.get("description") == "updated description"
    assert updated.get("active") is False


def test_update_promo_unknown_id_returns_404(live_server):
    """PUT /api/promos/nonexistent returns 404."""
    host, port = live_server
    status, body = _put(host, port, "/api/promos/nonexistent", {"description": "x"})
    assert status == 404


# ---------------------------------------------------------------------------
# 5. Delete promo
# ---------------------------------------------------------------------------


def test_delete_promo_returns_200(live_server):
    """DELETE /api/promos/{id} removes the promo and returns 200."""
    host, port = live_server
    _, create_body = _post(host, port, "/api/promos", {
        "code": "DELETEME", "type": "discount_fixed", "value": 200,
    })
    promo_id = create_body["promo"]["id"]

    status, body = _delete(host, port, f"/api/promos/{promo_id}")
    assert status == 200, f"Expected 200, got {status}: {body}"
    assert body.get("ok") is True

    # Should be gone from list
    _, promos = _get(host, port, "/api/promos")
    ids = [p["id"] for p in promos]
    assert promo_id not in ids


def test_delete_promo_unknown_id_returns_404(live_server):
    """DELETE /api/promos/nonexistent returns 404."""
    host, port = live_server
    status, body = _delete(host, port, "/api/promos/nonexistent")
    assert status == 404


# ---------------------------------------------------------------------------
# 6. Enable / Disable
# ---------------------------------------------------------------------------


def test_disable_promo(live_server):
    """POST /api/promos/{id}/disable sets active=False."""
    host, port = live_server
    _, create_body = _post(host, port, "/api/promos", {
        "code": "DISABLEME", "type": "discount_percent", "value": 5, "active": True,
    })
    promo_id = create_body["promo"]["id"]

    status, body = _post(host, port, f"/api/promos/{promo_id}/disable")
    assert status == 200, f"Expected 200, got {status}: {body}"
    assert body.get("ok") is True
    assert body["promo"]["active"] is False


def test_enable_promo(live_server):
    """POST /api/promos/{id}/enable sets active=True."""
    host, port = live_server
    _, create_body = _post(host, port, "/api/promos", {
        "code": "ENABLEME", "type": "discount_percent", "value": 5, "active": False,
    })
    promo_id = create_body["promo"]["id"]

    status, body = _post(host, port, f"/api/promos/{promo_id}/enable")
    assert status == 200
    assert body.get("ok") is True
    assert body["promo"]["active"] is True


# ---------------------------------------------------------------------------
# 7. Stats endpoint
# ---------------------------------------------------------------------------


def test_promo_stats_returns_200(live_server):
    """GET /api/promos/stats returns aggregate stats."""
    host, port = live_server
    status, body = _get(host, port, "/api/promos/stats")
    assert status == 200
    for field in ("total", "active", "inactive", "total_uses", "by_type"):
        assert field in body, f"Missing field {field!r} in stats"


# ---------------------------------------------------------------------------
# 8. 404 outside dev mode
# ---------------------------------------------------------------------------


def test_promos_endpoints_return_404_outside_dev_mode(monkeypatch):
    """All /api/promos* endpoints return 404 when AGENTSENTINEL_DEV is not 1."""
    monkeypatch.delenv("AGENTSENTINEL_DEV", raising=False)

    import agentsentinel.dashboard.server as srv
    with srv._promos_lock:
        srv._promos.clear()

    from agentsentinel.dashboard.server import start_dashboard

    guard = _make_guard()
    server = start_dashboard(guard, port=0, host="127.0.0.1", background=True)
    assert server is not None
    port = server._server.server_address[1]
    host = "127.0.0.1"
    time.sleep(0.05)

    try:
        for path in ("/api/promos", "/api/promos/some-id", "/api/promos/stats"):
            url = f"http://{host}:{port}{path}"
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(url, timeout=5)
            assert exc_info.value.code == 404, f"Expected 404 for {path}, got {exc_info.value.code}"
    finally:
        server.shutdown()
