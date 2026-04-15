# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

import hashlib
import hmac
import importlib
import json
import time
from unittest.mock import Mock

from agentsentinel.dashboard import license_api
from agentsentinel.dashboard.stripe_webhook import handle_stripe_webhook
from agentsentinel.licensing import LicenseManager, LicenseTier
from agentsentinel.utils.keygen import generate_license_key


def test_offline_validation_does_not_trust_key_format():
    mgr = LicenseManager()
    mgr._reset()
    mgr._license_key = "as_enterprise_anything"
    info = mgr._offline_validate()
    assert info.tier == LicenseTier.FREE
    assert info.is_valid is False


def test_offline_validation_accepts_signed_key(monkeypatch):
    monkeypatch.setenv("AGENTSENTINEL_LICENSE_SIGNING_SECRET", "test-signing-secret")
    key = generate_license_key("team", valid_days=1)
    mgr = LicenseManager()
    mgr._reset()
    mgr._license_key = key
    info = mgr._offline_validate()
    assert info.tier == LicenseTier.TEAM
    assert info.is_valid is True
    assert info.valid_until is not None and info.valid_until > time.time()


def test_dev_license_requires_dev_mode(monkeypatch):
    monkeypatch.delenv("AGENTSENTINEL_DEV_MODE", raising=False)
    result = license_api.validate_license_local("as_pro_devtest123")
    assert result["valid"] is False
    assert "disabled" in result["error"].lower()


def test_dev_license_allows_explicit_dev_mode(monkeypatch):
    monkeypatch.setenv("AGENTSENTINEL_DEV_MODE", "true")
    result = license_api.validate_license_local("as_team_devtest456", client_ip="127.0.0.1")
    assert result["valid"] is True
    assert result["tier"] == "team"


def test_dev_license_rate_limit(monkeypatch):
    monkeypatch.setenv("AGENTSENTINEL_DEV_MODE", "true")
    importlib.reload(license_api)
    for _ in range(10):
        license_api.validate_license_local("not-a-real-key", client_ip="10.1.2.3")
    limited = license_api.validate_license_local("not-a-real-key", client_ip="10.1.2.3")
    assert limited["valid"] is False
    assert "retry later" in limited["error"].lower()


def test_stripe_webhook_signature_and_idempotency():
    secret = "whsec_test_secret"
    payload_obj = {
        "id": "evt_123",
        "type": "checkout.session.completed",
        "data": {"object": {"customer": "cus_123"}},
    }
    payload = json.dumps(payload_obj, separators=(",", ":")).encode("utf-8")
    ts = str(int(time.time()))

    signed = f"{ts}.{payload.decode('utf-8')}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    header = f"t={ts},v1={sig}"

    callback = Mock()
    code, body = handle_stripe_webhook(
        payload,
        header,
        webhook_secret=secret,
        on_checkout_completed=callback,
    )
    assert code == 200
    assert body["status"] == "ok"
    callback.assert_called_once()

    code2, body2 = handle_stripe_webhook(
        payload,
        header,
        webhook_secret=secret,
        on_checkout_completed=callback,
    )
    assert code2 == 200
    assert body2["status"] == "duplicate_ignored"


def test_stripe_webhook_rejects_invalid_signature():
    payload = b'{"id":"evt_bad","type":"invoice.payment_failed","data":{"object":{}}}'
    code, body = handle_stripe_webhook(
        payload,
        "t=1,v1=invalid",
        webhook_secret="whsec_test_secret",
    )
    assert code == 400
    assert "signature" in body["error"].lower()
