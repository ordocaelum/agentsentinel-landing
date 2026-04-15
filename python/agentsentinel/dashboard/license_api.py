# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Local license API mock for development/testing."""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from threading import Lock
from typing import Any, Deque, Dict, cast

# In-memory license database (for development)
_DEV_LICENSES: Dict[str, Dict[str, Any]] = {
    "as_pro_devtest123": {
        "tier": "pro",
        "customer_name": "Development",
        "valid": True,
        "expires_at": 1798675199.0,  # 2026-12-30T23:59:59Z
    },
    "as_team_devtest456": {
        "tier": "team",
        "customer_name": "Development Team",
        "valid": True,
        "expires_at": 1798675199.0,  # 2026-12-30T23:59:59Z
    },
    "as_enterprise_devtest789": {
        "tier": "enterprise",
        "customer_name": "Development Enterprise",
        "valid": True,
        "expires_at": 1798675199.0,  # 2026-12-30T23:59:59Z
    },
}

_logger = logging.getLogger(__name__)
_rate_limit_lock = Lock()
_RATE_LIMIT_WINDOW_SECONDS = 60
_MAX_ATTEMPTS_PER_IP_PER_WINDOW = 10
_MAX_BACKOFF_SECONDS = 32
_RATE_LIMIT_STATE: Dict[str, Dict[str, Any]] = {}


def _is_dev_mode_enabled() -> bool:
    return os.environ.get("AGENTSENTINEL_DEV_MODE", "").strip().lower() == "true"


def _get_ip_state(client_ip: str) -> Dict[str, Any]:
    state = _RATE_LIMIT_STATE.get(client_ip)
    if state is None:
        state = {
            "attempts": deque(),
            "failures": 0,
            "backoff_until": 0.0,
        }
        _RATE_LIMIT_STATE[client_ip] = state
    return state


def validate_license_local(license_key: str, client_ip: str = "unknown") -> Dict[str, Any]:
    """Validate a license key locally (for development)."""
    now = time.time()
    with _rate_limit_lock:
        state = _get_ip_state(client_ip)
        attempts = cast(Deque[float], state["attempts"])
        while attempts and now - attempts[0] > _RATE_LIMIT_WINDOW_SECONDS:
            attempts.popleft()

        if now < state["backoff_until"]:
            retry_after = max(int(state["backoff_until"] - now), 1)
            return {
                "valid": False,
                "error": "Too many failed validation attempts. Retry later.",
                "retry_after": retry_after,
            }

        if len(attempts) >= _MAX_ATTEMPTS_PER_IP_PER_WINDOW:
            _logger.warning(
                "License API rate limit exceeded for IP %s (%s attempts in %ss)",
                client_ip,
                len(attempts),
                _RATE_LIMIT_WINDOW_SECONDS,
            )
            return {
                "valid": False,
                "error": "Rate limit exceeded. Too many validation attempts.",
                "retry_after": _RATE_LIMIT_WINDOW_SECONDS,
            }
        attempts.append(now)

    if not _is_dev_mode_enabled():
        return {
            "valid": False,
            "error": "Development license validation disabled",
        }

    info = _DEV_LICENSES.get(license_key)
    if info:
        expires_at = float(info.get("expires_at", 0.0))
        if expires_at <= now:
            return {
                "valid": False,
                "error": "Development license expired",
            }
        _logger.warning(
            "Development license key used for local validation (tier=%s, ip=%s)",
            info["tier"],
            client_ip,
        )
        with _rate_limit_lock:
            state = _get_ip_state(client_ip)
            state["failures"] = 0
            state["backoff_until"] = 0.0
        return {
            "valid": True,
            "tier": info["tier"],
            "customer_name": info["customer_name"],
            "valid_until": expires_at,
        }

    with _rate_limit_lock:
        state = _get_ip_state(client_ip)
        state["failures"] += 1
        delay = min(2 ** (state["failures"] - 1), _MAX_BACKOFF_SECONDS)
        state["backoff_until"] = time.time() + delay
        if state["failures"] >= 5:
            _logger.warning(
                "Suspicious repeated invalid license attempts from IP %s (failures=%s)",
                client_ip,
                state["failures"],
            )

    return {
        "valid": False,
        "error": "Invalid license key",
    }
