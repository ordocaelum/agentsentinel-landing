# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Pytest configuration: reset the license manager singleton between tests."""

import gc
import pytest

from agentsentinel.licensing import get_license_manager, LicenseTier, LicenseInfo, TIER_LIMITS


@pytest.fixture(autouse=True)
def reset_license_manager():
    """Reset the LicenseManager singleton before and after each test.

    This prevents state bleed between tests (registered agents, event counts)
    and ensures every test starts with an enterprise-tier license so that all
    integration and guard features are available without interference from
    license enforcement.
    """
    mgr = get_license_manager()
    # Set enterprise license so all features are available in tests
    mgr._reset()
    mgr._license_info = LicenseInfo(
        tier=LicenseTier.ENTERPRISE,
        limits=TIER_LIMITS[LicenseTier.ENTERPRISE],
        is_valid=True,
    )
    mgr._last_validation = float("inf")  # Never re-validate during tests

    yield

    # Force garbage collection to invoke __del__ on any lingering AgentGuard objects
    gc.collect()
    mgr._reset()
