# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Local license API mock for development/testing."""

from typing import Dict, Any
import time

# In-memory license database (for development)
_DEV_LICENSES: Dict[str, Dict[str, Any]] = {
    "as_pro_devtest123": {
        "tier": "pro",
        "customer_name": "Development",
        "valid": True,
    },
    "as_team_devtest456": {
        "tier": "team",
        "customer_name": "Development Team",
        "valid": True,
    },
    "as_enterprise_devtest789": {
        "tier": "enterprise",
        "customer_name": "Development Enterprise",
        "valid": True,
    },
}


def validate_license_local(license_key: str) -> Dict[str, Any]:
    """Validate a license key locally (for development)."""
    if license_key in _DEV_LICENSES:
        info = _DEV_LICENSES[license_key]
        return {
            "valid": True,
            "tier": info["tier"],
            "customer_name": info["customer_name"],
            "valid_until": time.time() + 86400 * 365,  # 1 year
        }

    return {
        "valid": False,
        "error": "Invalid license key",
    }
