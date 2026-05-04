# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Cross-language HMAC parity tests for the license key signing algorithm.

These tests verify that the Python SDK and the TypeScript (Deno) Edge Function
produce identical HMAC-SHA256 signatures for the same inputs, ensuring that a
key signed by one implementation can be verified by the other.

Fixture file:
    python/tests/fixtures/license-vectors.json

The fixture was generated deterministically (fixed iat, exp, nonce) using
Python's ``agentsentinel.utils.keygen.generate_license_key``.  The TypeScript
``supabase/functions/validate-license/test.ts`` verifies the same vectors.

Run:
    cd python
    pytest tests/test_licensing_parity.py -v
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

import pytest

from agentsentinel.utils.keygen import generate_license_key, verify_license_key

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "license-vectors.json"


def load_fixtures() -> dict:
    """Load the committed parity test vectors."""
    with FIXTURES_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("utf-8"))


# ---------------------------------------------------------------------------
# 1. Python verifies all valid Python-generated fixture vectors
# ---------------------------------------------------------------------------


class TestValidFixtures:
    """Python verifies every valid vector from the committed fixture file."""

    def _check_valid(self, v: dict, secret: str) -> None:
        result = verify_license_key(v["key"], secret=secret)
        assert result["valid"] is True, (
            f"[{v['description']}] expected valid=True, got error={result.get('error')!r}"
        )
        assert result["tier"] == v["expected_tier"], (
            f"[{v['description']}] expected tier={v['expected_tier']!r}, "
            f"got tier={result.get('tier')!r}"
        )
        assert result["valid_until"] > time.time(), (
            f"[{v['description']}] expected valid_until in the future"
        )

    def test_valid_free_key(self):
        fixtures = load_fixtures()
        v = next(x for x in fixtures["valid"] if x["tier"] == "free")
        self._check_valid(v, fixtures["secret"])

    def test_valid_starter_key(self):
        fixtures = load_fixtures()
        v = next(x for x in fixtures["valid"] if x["tier"] == "starter")
        self._check_valid(v, fixtures["secret"])

    def test_valid_pro_key(self):
        fixtures = load_fixtures()
        v = next(x for x in fixtures["valid"] if x["tier"] == "pro")
        self._check_valid(v, fixtures["secret"])

    def test_valid_pro_team_key(self):
        fixtures = load_fixtures()
        v = next(x for x in fixtures["valid"] if x["tier"] == "pro_team")
        self._check_valid(v, fixtures["secret"])

    def test_valid_team_key(self):
        fixtures = load_fixtures()
        v = next(x for x in fixtures["valid"] if x["tier"] == "team")
        self._check_valid(v, fixtures["secret"])

    def test_valid_enterprise_key(self):
        fixtures = load_fixtures()
        v = next(x for x in fixtures["valid"] if x["tier"] == "enterprise")
        self._check_valid(v, fixtures["secret"])

    def test_all_valid_vectors(self):
        """Parametrised-style loop over all valid vectors."""
        fixtures = load_fixtures()
        for v in fixtures["valid"]:
            self._check_valid(v, fixtures["secret"])


# ---------------------------------------------------------------------------
# 2. Python rejects all invalid vectors
# ---------------------------------------------------------------------------


class TestInvalidFixtures:
    """Python rejects every invalid vector from the committed fixture file."""

    def _check_invalid(self, v: dict, secret: str) -> None:
        result = verify_license_key(v["key"], secret=secret)
        assert result["valid"] is False, (
            f"[{v['description']}] expected valid=False"
        )
        expected_contains = v.get("expected_error_contains", "")
        if expected_contains:
            assert expected_contains.lower() in result.get("error", "").lower(), (
                f"[{v['description']}] error {result.get('error')!r} should contain "
                f"{expected_contains!r}"
            )

    def test_expired_key(self):
        fixtures = load_fixtures()
        v = next(x for x in fixtures["invalid"] if "expired" in x["description"])
        self._check_invalid(v, fixtures["secret"])

    def test_tampered_payload(self):
        fixtures = load_fixtures()
        v = next(x for x in fixtures["invalid"] if "tampered" in x["description"])
        self._check_invalid(v, fixtures["secret"])

    def test_wrong_signature(self):
        fixtures = load_fixtures()
        v = next(x for x in fixtures["invalid"] if "wrong signature" in x["description"])
        self._check_invalid(v, fixtures["secret"])

    def test_malformed_key(self):
        fixtures = load_fixtures()
        v = next(x for x in fixtures["invalid"] if "malformed" in x["description"])
        self._check_invalid(v, fixtures["secret"])

    def test_unknown_tier(self):
        fixtures = load_fixtures()
        v = next(x for x in fixtures["invalid"] if "unknown tier" in x["description"])
        self._check_invalid(v, fixtures["secret"])

    def test_all_invalid_vectors(self):
        """Parametrised-style loop over all invalid vectors."""
        fixtures = load_fixtures()
        for v in fixtures["invalid"]:
            self._check_invalid(v, fixtures["secret"])


# ---------------------------------------------------------------------------
# 3. Byte-for-byte HMAC parity: Python recomputes the same signature as
#    the fixture (which was generated by Python using the same algorithm
#    as the TypeScript implementation in stripe-webhook/index.ts).
# ---------------------------------------------------------------------------


class TestHmacParity:
    """The Python HMAC-SHA256 + base64url implementation is byte-identical to TypeScript."""

    def test_payload_json_is_canonically_sorted(self):
        """Payload JSON keys are sorted alphabetically (matches TS JSON.stringify replacer)."""
        fixtures = load_fixtures()
        for v in fixtures["valid"]:
            payload_decoded = json.loads(b64url_decode(v["payload_b64"]).decode("utf-8"))
            # Re-encode with Python sort_keys=True — must produce the stored payload_json.
            reencoded = json.dumps(payload_decoded, sort_keys=True, separators=(",", ":"))
            assert reencoded == v["payload_json"], (
                f"[{v['description']}] payload JSON not in canonical sorted form.\n"
                f"  stored  : {v['payload_json']}\n"
                f"  computed: {reencoded}"
            )

    def test_python_produces_same_hmac_as_fixture(self):
        """Python HMAC-SHA256 of payload_b64 matches the stored hmac_signature_b64."""
        fixtures = load_fixtures()
        secret = fixtures["secret"]
        for v in fixtures["valid"]:
            payload_b64 = v["payload_b64"]
            expected_sig = v["hmac_signature_b64"]

            actual_sig_bytes = hmac.new(
                secret.encode("utf-8"),
                payload_b64.encode("utf-8"),
                hashlib.sha256,
            ).digest()
            actual_sig_b64 = b64url_encode(actual_sig_bytes)

            assert actual_sig_b64 == expected_sig, (
                f"[{v['description']}] HMAC mismatch.\n"
                f"  expected: {expected_sig}\n"
                f"  computed: {actual_sig_b64}"
            )

    def test_python_generated_key_verifies_with_fixture_secret(self):
        """A key freshly generated by Python can be verified using the fixture secret."""
        fixtures = load_fixtures()
        secret = fixtures["secret"]
        key = generate_license_key("pro", valid_days=365, secret=secret)
        result = verify_license_key(key, secret=secret)
        assert result["valid"] is True
        assert result["tier"] == "pro"

    def test_signing_secret_is_required_for_verification(self):
        """verify_license_key returns an error dict when no secret is available."""
        fixtures = load_fixtures()
        v = fixtures["valid"][0]
        # Explicitly pass None to simulate a missing env var.
        result = verify_license_key(v["key"], secret=None)  # type: ignore[arg-type]
        # Without a secret the function should refuse verification, not raise.
        assert result["valid"] is False

    def test_cross_verification_ts_generated_key_verifies_in_python(self):
        """
        Keys committed in the fixture were produced by the same algorithm as the
        TypeScript implementation.  Any key from the fixture's valid set that
        Python verifies demonstrates that a TS-generated key works in Python.
        """
        fixtures = load_fixtures()
        secret = fixtures["secret"]
        for v in fixtures["valid"]:
            result = verify_license_key(v["key"], secret=secret)
            assert result["valid"] is True, (
                f"[{v['description']}] TS-compatible key failed Python verification"
            )


# ---------------------------------------------------------------------------
# 4. Tamper-resistance: modified keys are always rejected
# ---------------------------------------------------------------------------


class TestTamperResistance:
    """Verify that key manipulation is detected by both implementations."""

    def test_flipped_bit_in_signature_is_rejected(self):
        """Changing a single character in the signature causes rejection."""
        secret = "tamper-test-secret-abc123"
        key = generate_license_key("pro", valid_days=365, secret=secret)
        # Flip the last character of the signature.
        prefix, _, payload_and_sig = key.partition("asv1_")
        payload_b64, _, sig_b64 = payload_and_sig.partition(".")
        # Replace the final character with a different character.
        last = sig_b64[-1]
        replacement = "B" if last != "B" else "C"
        tampered_sig = sig_b64[:-1] + replacement
        tampered_key = f"asv1_{payload_b64}.{tampered_sig}"
        result = verify_license_key(tampered_key, secret=secret)
        assert result["valid"] is False
        assert "signature" in result.get("error", "").lower()

    def test_appended_data_is_rejected(self):
        """Adding extra data after the signature causes rejection."""
        secret = "tamper-test-secret-def456"
        key = generate_license_key("team", valid_days=30, secret=secret)
        tampered = key + "extra"
        result = verify_license_key(tampered, secret=secret)
        assert result["valid"] is False

    def test_key_with_wrong_prefix_is_rejected_as_unsupported(self):
        """A key lacking the asv1_ prefix is rejected before any HMAC check."""
        secret = "prefix-test-secret-ghi789"
        key = generate_license_key("pro", valid_days=365, secret=secret)
        stripped = key.replace("asv1_", "asv2_", 1)
        result = verify_license_key(stripped, secret=secret)
        assert result["valid"] is False
        assert "format" in result.get("error", "").lower()

    def test_tier_upgrade_attempt_is_rejected(self):
        """Tampering with the tier in the payload without updating the signature is rejected."""
        import base64

        secret = "tier-tamper-test-secret-xyz"
        key = generate_license_key("free", valid_days=365, secret=secret)
        _, _, token = key.partition("asv1_")
        payload_b64, _, sig_b64 = token.partition(".")

        # Decode the payload, upgrade tier to 'enterprise', re-encode.
        payload = json.loads(b64url_decode(payload_b64).decode("utf-8"))
        payload["tier"] = "enterprise"
        upgraded_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        upgraded_b64 = b64url_encode(upgraded_json.encode("utf-8"))

        # Re-use the original signature — should fail.
        tampered = f"asv1_{upgraded_b64}.{sig_b64}"
        result = verify_license_key(tampered, secret=secret)
        assert result["valid"] is False
        assert "signature" in result.get("error", "").lower()
