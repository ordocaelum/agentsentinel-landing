# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""CI guard: fail if any customer-facing HTML/JS stores license keys in localStorage.

Acceptance criteria (Phase 3.4):
  - No `localStorage.setItem` call whose key argument matches /licens|_key|license/i
    may appear in any *.html or *.js file under the customer portal paths.

Files in scope:
  - portal.html (customer portal)
  - python/agentsentinel/dashboard/static/js/license-manager.js (SDK dashboard widget)

Files explicitly out of scope (admin dashboard theme preferences etc.):
  - python/agentsentinel/dashboard/static/admin/
  - python/agentsentinel/dashboard/static/index.html  (theme/sound/pin prefs only)
  - python/agentsentinel/dashboard/static/js/theme-switcher.js

A match that is only in a comment is still a violation — we use a broad regex
intentionally so that any future developer who accidentally adds such a call
is caught by the test.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths to audit
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parents[2]

# Files / globs that MUST NOT contain localStorage license-key writes.
FILES_IN_SCOPE = [
    REPO_ROOT / "portal.html",
    REPO_ROOT / "python" / "agentsentinel" / "dashboard" / "static" / "js" / "license-manager.js",
]

# Pattern: localStorage.setItem( <quote> <key-matching-license-or-key> <quote>
# We intentionally keep this broad to catch variations like:
#   localStorage.setItem('license_key', ...)
#   localStorage.setItem("licenseKey", ...)
#   localStorage.setItem('as_key', ...)
LOCALSTORAGE_LICENSE_RE = re.compile(
    r"""localStorage\.setItem\s*\(\s*['"`][^'"`]*(?:licens|_key)[^'"`]*['"`]""",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filepath", FILES_IN_SCOPE)
def test_no_localstorage_license_key(filepath: Path):
    """Fail if the file stores a license-related value in localStorage."""
    if not filepath.exists():
        pytest.skip(f"File not found: {filepath}")

    content = filepath.read_text(encoding="utf-8")
    matches = list(LOCALSTORAGE_LICENSE_RE.finditer(content))

    if matches:
        lines = content.splitlines()
        offending = []
        for m in matches:
            # Compute line number for the match start.
            line_no = content[: m.start()].count("\n") + 1
            offending.append(f"  Line {line_no}: {lines[line_no - 1].strip()}")
        pytest.fail(
            f"{filepath.relative_to(REPO_ROOT)} stores a license key in localStorage "
            f"— use sessionStorage instead:\n" + "\n".join(offending)
        )
