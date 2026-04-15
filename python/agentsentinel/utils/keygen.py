# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Secure license key generation and verification helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Dict, Optional

SIGNING_SECRET_ENV = "AGENTSENTINEL_LICENSE_SIGNING_SECRET"
KEY_PREFIX = "asv1_"


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("utf-8"))


def _get_signing_secret(explicit_secret: Optional[str]) -> Optional[str]:
    return explicit_secret or os.environ.get(SIGNING_SECRET_ENV)


def generate_license_key(tier: str, valid_days: int = 365, secret: Optional[str] = None) -> str:
    """Generate an HMAC-signed license key with embedded tier and expiration."""
    signing_secret = _get_signing_secret(secret)
    if not signing_secret:
        raise ValueError(f"{SIGNING_SECRET_ENV} must be set to generate license keys")

    now = int(time.time())
    payload = {
        "tier": tier.lower(),
        "exp": now + (valid_days * 86400),
        "iat": now,
        "nonce": secrets.token_urlsafe(12),
    }
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64url_encode(payload_bytes)
    signature = hmac.new(
        signing_secret.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    )
    sig_b64 = _b64url_encode(signature.digest())
    return f"{KEY_PREFIX}{payload_b64}.{sig_b64}"


def verify_license_key(key: str, secret: Optional[str] = None) -> Dict[str, Any]:
    """Verify an HMAC-signed license key."""
    signing_secret = _get_signing_secret(secret)
    if not signing_secret:
        return {"valid": False, "error": "Signing secret unavailable"}

    if not key.startswith(KEY_PREFIX):
        return {"valid": False, "error": "Unsupported key format"}

    token = key[len(KEY_PREFIX) :]
    if "." not in token:
        return {"valid": False, "error": "Malformed key"}

    payload_b64, sig_b64 = token.split(".", 1)
    try:
        expected = hmac.new(
            signing_secret.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256,
        )
        expected_b64 = _b64url_encode(expected.digest())
        if not hmac.compare_digest(expected_b64, sig_b64):
            return {"valid": False, "error": "Invalid signature"}

        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        tier = str(payload.get("tier", "")).lower()
        if tier not in {"free", "pro", "team", "enterprise"}:
            return {"valid": False, "error": "Invalid tier"}

        expires_at = int(payload.get("exp", 0))
        if expires_at <= int(time.time()):
            return {"valid": False, "error": "License expired"}

        checksum = hashlib.sha256(payload_b64.encode("utf-8")).hexdigest()[:16]
        return {
            "valid": True,
            "tier": tier,
            "valid_until": float(expires_at),
            "checksum": checksum,
        }
    except Exception:
        return {"valid": False, "error": "Malformed key"}
