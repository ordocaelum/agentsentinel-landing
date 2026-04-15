# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""License validation and feature gating for AgentSentinel."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Set

from .utils.keygen import verify_license_key


class LicenseTier(Enum):
    """License tiers with associated limits."""
    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"


@dataclass
class LicenseLimits:
    """Limits for each license tier."""
    max_agents: int
    max_events_per_month: int
    dashboard_enabled: bool
    integrations_enabled: bool
    multi_agent_enabled: bool
    policy_editor: str  # "none", "basic", "full"
    watermark_required: bool


# Tier configurations
TIER_LIMITS: Dict[LicenseTier, LicenseLimits] = {
    LicenseTier.FREE: LicenseLimits(
        max_agents=1,
        max_events_per_month=1_000,
        dashboard_enabled=False,
        integrations_enabled=False,
        multi_agent_enabled=False,
        policy_editor="none",
        watermark_required=True,
    ),
    LicenseTier.PRO: LicenseLimits(
        max_agents=5,
        max_events_per_month=50_000,
        dashboard_enabled=True,
        integrations_enabled=True,
        multi_agent_enabled=False,
        policy_editor="basic",
        watermark_required=False,
    ),
    LicenseTier.TEAM: LicenseLimits(
        max_agents=20,
        max_events_per_month=500_000,
        dashboard_enabled=True,
        integrations_enabled=True,
        multi_agent_enabled=True,
        policy_editor="full",
        watermark_required=False,
    ),
    LicenseTier.ENTERPRISE: LicenseLimits(
        max_agents=999_999,  # Effectively unlimited
        max_events_per_month=999_999_999,
        dashboard_enabled=True,
        integrations_enabled=True,
        multi_agent_enabled=True,
        policy_editor="full",
        watermark_required=False,
    ),
}


@dataclass
class LicenseInfo:
    """Information about the current license."""
    tier: LicenseTier
    limits: LicenseLimits
    license_key: Optional[str] = None
    customer_name: Optional[str] = None
    valid_until: Optional[float] = None  # Unix timestamp
    is_valid: bool = True
    validation_error: Optional[str] = None


class LicenseError(Exception):
    """Raised when a license limit is exceeded or license is invalid."""
    pass


class FeatureNotAvailableError(LicenseError):
    """Raised when trying to use a feature not available in the current tier."""
    pass


class UsageLimitExceededError(LicenseError):
    """Raised when usage limits are exceeded."""
    pass


# License validation API endpoint
LICENSE_API_URL = os.environ.get(
    "AGENTSENTINEL_LICENSE_API",
    "https://api.agentsentinel.dev/v1/license/validate"
)

# Cache duration for license validation (1 hour)
LICENSE_CACHE_DURATION = 3600


class LicenseManager:
    """Manages license validation and feature gating."""

    _instance: Optional["LicenseManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "LicenseManager":
        """Singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        self._license_key: Optional[str] = None
        self._license_info: LicenseInfo = LicenseInfo(
            tier=LicenseTier.FREE,
            limits=TIER_LIMITS[LicenseTier.FREE],
        )
        self._last_validation: float = 0
        self._event_count: int = 0
        self._agent_count: int = 0
        self._registered_agents: Set[str] = set()
        self._validation_lock = threading.Lock()

        # Check for license key in environment
        env_key = os.environ.get("AGENTSENTINEL_LICENSE_KEY")
        if env_key:
            self.set_license_key(env_key)

    def set_license_key(self, key: str) -> LicenseInfo:
        """Set and validate a license key."""
        self._license_key = key
        return self._validate_license(force=True)

    def get_license_info(self) -> LicenseInfo:
        """Get current license information, revalidating if needed."""
        if time.time() - self._last_validation > LICENSE_CACHE_DURATION:
            self._validate_license()
        return self._license_info

    def _validate_license(self, force: bool = False) -> LicenseInfo:
        """Validate the license key against the API."""
        with self._validation_lock:
            # Skip if recently validated (unless forced)
            if not force and time.time() - self._last_validation < LICENSE_CACHE_DURATION:
                return self._license_info

            if not self._license_key:
                # No key = free tier
                self._license_info = LicenseInfo(
                    tier=LicenseTier.FREE,
                    limits=TIER_LIMITS[LicenseTier.FREE],
                )
                self._last_validation = time.time()
                return self._license_info

            # Validate against API
            try:
                self._license_info = self._call_license_api()
            except Exception as e:
                # On API failure, use cached/offline validation
                self._license_info = self._offline_validate()
                self._license_info.validation_error = str(e)

            self._last_validation = time.time()
            return self._license_info

    def _call_license_api(self) -> LicenseInfo:
        """Call the license validation API."""
        try:
            data = json.dumps({
                "license_key": self._license_key,
                "product": "agentsentinel",
                "version": "1.2.0",
            }).encode("utf-8")

            req = urllib.request.Request(
                LICENSE_API_URL,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            if not result.get("valid"):
                return LicenseInfo(
                    tier=LicenseTier.FREE,
                    limits=TIER_LIMITS[LicenseTier.FREE],
                    license_key=self._license_key,
                    is_valid=False,
                    validation_error=result.get("error", "Invalid license key"),
                )

            tier = LicenseTier(result.get("tier", "free"))
            return LicenseInfo(
                tier=tier,
                limits=TIER_LIMITS[tier],
                license_key=self._license_key,
                customer_name=result.get("customer_name"),
                valid_until=result.get("valid_until"),
                is_valid=True,
            )

        except urllib.error.URLError:
            # Network error — use offline validation
            return self._offline_validate()

    def _offline_validate(self) -> LicenseInfo:
        """Offline validation using cryptographic signature verification."""
        if not self._license_key:
            return LicenseInfo(
                tier=LicenseTier.FREE,
                limits=TIER_LIMITS[LicenseTier.FREE],
            )

        verification = verify_license_key(self._license_key)
        if verification.get("valid"):
            tier = LicenseTier(verification["tier"])
            return LicenseInfo(
                tier=tier,
                limits=TIER_LIMITS[tier],
                license_key=self._license_key,
                valid_until=verification.get("valid_until"),
                is_valid=True,
                validation_error="Offline validation (signed key)",
            )

        # API unavailable and key cannot be verified offline -> safest fallback is FREE.
        return LicenseInfo(
            tier=LicenseTier.FREE,
            limits=TIER_LIMITS[LicenseTier.FREE],
            license_key=self._license_key,
            is_valid=False,
            validation_error=verification.get("error", "Offline validation failed"),
        )

    # ─── Usage Tracking ───────────────────────────────────────────────────

    def register_agent(self, agent_id: str) -> None:
        """Register an agent and check limits."""
        limits = self.get_license_info().limits

        if agent_id in self._registered_agents:
            return

        if len(self._registered_agents) >= limits.max_agents:
            raise UsageLimitExceededError(
                f"Agent limit exceeded. Your {self._license_info.tier.value} plan "
                f"allows {limits.max_agents} agent(s). "
                f"Upgrade at https://agentsentinel.dev/pricing"
            )

        self._registered_agents.add(agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent (called when AgentGuard is destroyed)."""
        self._registered_agents.discard(agent_id)

    def _reset(self) -> None:
        """Reset all state (intended for testing only)."""
        self._license_key = None
        self._license_info = LicenseInfo(
            tier=LicenseTier.FREE,
            limits=TIER_LIMITS[LicenseTier.FREE],
        )
        self._last_validation = 0
        self._event_count = 0
        self._agent_count = 0
        self._registered_agents = set()

    def record_event(self) -> None:
        """Record an event and check limits."""
        self._event_count += 1
        limits = self.get_license_info().limits

        if self._event_count > limits.max_events_per_month:
            raise UsageLimitExceededError(
                f"Monthly event limit exceeded ({limits.max_events_per_month:,} events). "
                f"Upgrade at https://agentsentinel.dev/pricing"
            )

    def get_usage(self) -> Dict[str, Any]:
        """Get current usage statistics."""
        limits = self.get_license_info().limits
        return {
            "agents": {
                "current": len(self._registered_agents),
                "limit": limits.max_agents,
            },
            "events": {
                "current": self._event_count,
                "limit": limits.max_events_per_month,
            },
        }

    def reset_monthly_usage(self) -> None:
        """Reset monthly event counter (call on billing cycle)."""
        self._event_count = 0

    # ─── Feature Gating ───────────────────────────────────────────────────

    def require_feature(self, feature: str) -> None:
        """Check if a feature is available, raise if not."""
        limits = self.get_license_info().limits

        feature_checks = {
            "dashboard": limits.dashboard_enabled,
            "integrations": limits.integrations_enabled,
            "multi_agent": limits.multi_agent_enabled,
            "policy_editor_basic": limits.policy_editor in ("basic", "full"),
            "policy_editor_full": limits.policy_editor == "full",
        }

        if feature in feature_checks and not feature_checks[feature]:
            tier = self._license_info.tier.value
            raise FeatureNotAvailableError(
                f"The '{feature}' feature is not available in your {tier} plan. "
                f"Upgrade at https://agentsentinel.dev/pricing"
            )

    def is_feature_available(self, feature: str) -> bool:
        """Check if a feature is available without raising."""
        try:
            self.require_feature(feature)
            return True
        except FeatureNotAvailableError:
            return False

    def should_show_watermark(self) -> bool:
        """Check if watermark should be shown."""
        return self.get_license_info().limits.watermark_required


# Global instance
_license_manager: Optional[LicenseManager] = None


def get_license_manager() -> LicenseManager:
    """Get the global license manager instance."""
    global _license_manager
    if _license_manager is None:
        _license_manager = LicenseManager()
    return _license_manager


def set_license_key(key: str) -> LicenseInfo:
    """Set the license key for the SDK."""
    return get_license_manager().set_license_key(key)


def get_license_info() -> LicenseInfo:
    """Get current license information."""
    return get_license_manager().get_license_info()


def require_feature(feature: str) -> None:
    """Require a feature to be available."""
    get_license_manager().require_feature(feature)


def is_feature_available(feature: str) -> bool:
    """Check if a feature is available."""
    return get_license_manager().is_feature_available(feature)
