# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Tests for agentsentinel.config_check.

Feeds known-good and known-bad .env strings to the validator and asserts
correct classification of each variable.
"""

from __future__ import annotations

import sys
from io import StringIO
from typing import Dict, Optional
from unittest.mock import patch

import pytest

from agentsentinel.config_check import (
    _is_dev,
    _load_env_file,
    run_check,
    main,
    VARS,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse(text: str) -> Dict[str, str]:
    """Parse a multi-line .env string into a dict (mimics _load_env_file)."""
    result: Dict[str, str] = {}
    for raw_line in text.strip().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        result[key.strip()] = val
    return result


# ── minimum prod env ─────────────────────────────────────────────────────────

GOOD_PROD_ENV = """
AGENTSENTINEL_LICENSE_SIGNING_SECRET=a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6a7b8c9d0e1f2a3b4c5d6a7b8c9d0e1f2
ADMIN_API_SECRET=deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef
SUPABASE_URL=https://xxxxxxxxxxxxxxxxxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.longtoken
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.anontoken
STRIPE_SECRET_KEY=sk_live_abc123
STRIPE_PUBLISHABLE_KEY=pk_live_abc123
STRIPE_WEBHOOK_SECRET=whsec_abc123
STRIPE_PRICE_STARTER=price_1ABC
STRIPE_PRICE_PRO=price_1DEF
STRIPE_PRICE_PRO_TEAM=price_1GHI
STRIPE_PRICE_ENTERPRISE=price_1JKL
STRIPE_PRICE_PRO_TEAM_BASE=price_1MNO
STRIPE_PRICE_PRO_TEAM_SEAT=price_1PQR
RESEND_API_KEY=re_abc123
SITE_BASE_URL=https://agentsentinel.net
"""

GOOD_DEV_ENV = """
AGENTSENTINEL_LICENSE_SIGNING_SECRET=a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6a7b8c9d0e1f2a3b4c5d6a7b8c9d0e1f2
ADMIN_API_SECRET=deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef
AGENTSENTINEL_DEV=1
"""


# ─────────────────────────────────────────────────────────────────────────────
# 1. _load_env_file
# ─────────────────────────────────────────────────────────────────────────────

def test_load_env_file_basic(tmp_path):
    """_load_env_file parses a simple .env file correctly."""
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=bar\nBAZ=qux\n", encoding="utf-8")
    result = _load_env_file(env_file)
    assert result == {"FOO": "bar", "BAZ": "qux"}


def test_load_env_file_quoted_values(tmp_path):
    """_load_env_file strips surrounding quotes."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        'DOUBLE="double_val"\nSINGLE=\'single_val\'\n', encoding="utf-8"
    )
    result = _load_env_file(env_file)
    assert result["DOUBLE"] == "double_val"
    assert result["SINGLE"] == "single_val"


def test_load_env_file_ignores_comments_and_blanks(tmp_path):
    """_load_env_file ignores comment lines and blank lines."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# This is a comment\n\nKEY=value\n", encoding="utf-8"
    )
    result = _load_env_file(env_file)
    assert result == {"KEY": "value"}


def test_load_env_file_missing_file(tmp_path):
    """_load_env_file returns empty dict when file does not exist."""
    result = _load_env_file(tmp_path / "nonexistent.env")
    assert result == {}


def test_load_env_file_empty_value(tmp_path):
    """_load_env_file handles empty values."""
    env_file = tmp_path / ".env"
    env_file.write_text("EMPTY=\n", encoding="utf-8")
    result = _load_env_file(env_file)
    assert result["EMPTY"] == ""


# ─────────────────────────────────────────────────────────────────────────────
# 2. _is_dev
# ─────────────────────────────────────────────────────────────────────────────

def test_is_dev_via_agentsentinel_dev():
    assert _is_dev({"AGENTSENTINEL_DEV": "1"}) is True


def test_is_dev_via_dev_mode():
    assert _is_dev({"AGENTSENTINEL_DEV_MODE": "true"}) is True


def test_is_dev_false_when_unset():
    assert _is_dev({}) is False


def test_is_dev_false_when_dev_mode_false():
    assert _is_dev({"AGENTSENTINEL_DEV_MODE": "false"}) is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. run_check — known-good environments
# ─────────────────────────────────────────────────────────────────────────────

def test_run_check_good_prod_passes(capsys):
    """A fully-filled prod .env should return 0 failures."""
    env = _parse(GOOD_PROD_ENV)
    failures = run_check(env, dev_mode=False)
    assert failures == 0


def test_run_check_good_dev_passes(capsys):
    """A minimal dev .env (only required-in-dev vars set) should return 0 failures."""
    env = _parse(GOOD_DEV_ENV)
    failures = run_check(env, dev_mode=True)
    assert failures == 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. run_check — known-bad environments
# ─────────────────────────────────────────────────────────────────────────────

def test_run_check_missing_signing_secret_fails_in_dev(capsys):
    """Missing AGENTSENTINEL_LICENSE_SIGNING_SECRET fails even in dev mode."""
    env = _parse(GOOD_DEV_ENV)
    del env["AGENTSENTINEL_LICENSE_SIGNING_SECRET"]
    failures = run_check(env, dev_mode=True)
    assert failures >= 1


def test_run_check_short_signing_secret_fails(capsys):
    """A signing secret shorter than 32 chars should fail validation."""
    env = _parse(GOOD_PROD_ENV)
    env["AGENTSENTINEL_LICENSE_SIGNING_SECRET"] = "tooshort"
    failures = run_check(env, dev_mode=False)
    assert failures >= 1


def test_run_check_missing_admin_secret_fails_in_dev(capsys):
    """Missing ADMIN_API_SECRET fails even in dev mode."""
    env = _parse(GOOD_DEV_ENV)
    del env["ADMIN_API_SECRET"]
    failures = run_check(env, dev_mode=True)
    assert failures >= 1


def test_run_check_bad_stripe_key_fails(capsys):
    """A Stripe secret key that doesn't start with sk_live_ or sk_test_ should fail."""
    env = _parse(GOOD_PROD_ENV)
    env["STRIPE_SECRET_KEY"] = "wrong_prefix_123"
    failures = run_check(env, dev_mode=False)
    assert failures >= 1


def test_run_check_bad_stripe_publishable_key_fails(capsys):
    """A Stripe publishable key that doesn't start with pk_ should fail."""
    env = _parse(GOOD_PROD_ENV)
    env["STRIPE_PUBLISHABLE_KEY"] = "not_a_pk_key"
    failures = run_check(env, dev_mode=False)
    assert failures >= 1


def test_run_check_bad_webhook_secret_fails(capsys):
    """A webhook secret that doesn't start with whsec_ should fail."""
    env = _parse(GOOD_PROD_ENV)
    env["STRIPE_WEBHOOK_SECRET"] = "bad_secret"
    failures = run_check(env, dev_mode=False)
    assert failures >= 1


def test_run_check_bad_supabase_url_fails(capsys):
    """A Supabase URL that doesn't start with https:// should fail."""
    env = _parse(GOOD_PROD_ENV)
    env["SUPABASE_URL"] = "not-a-url"
    failures = run_check(env, dev_mode=False)
    assert failures >= 1


def test_run_check_bad_resend_key_fails(capsys):
    """A Resend API key that doesn't start with re_ should fail."""
    env = _parse(GOOD_PROD_ENV)
    env["RESEND_API_KEY"] = "bad_resend_key"
    failures = run_check(env, dev_mode=False)
    assert failures >= 1


def test_run_check_bad_price_ids_fail(capsys):
    """Stripe Price IDs that don't start with price_ should fail."""
    env = _parse(GOOD_PROD_ENV)
    env["STRIPE_PRICE_STARTER"] = "not_a_price_id"
    failures = run_check(env, dev_mode=False)
    assert failures >= 1


def test_run_check_empty_prod_env_fails(capsys):
    """An empty prod env should fail with multiple missing required vars."""
    failures = run_check({}, dev_mode=False)
    assert failures >= 5  # at least SIGNING_SECRET + ADMIN_API_SECRET + SUPABASE + Stripe


# ─────────────────────────────────────────────────────────────────────────────
# 5. run_check — optional vars in dev mode
# ─────────────────────────────────────────────────────────────────────────────

def test_optional_vars_do_not_fail_in_dev(capsys):
    """Prod-only vars (Stripe, Supabase) should not cause failures in dev mode."""
    # Only the two dev-required vars are set
    env = {
        "AGENTSENTINEL_LICENSE_SIGNING_SECRET": "a" * 32,
        "ADMIN_API_SECRET": "b" * 32,
        "AGENTSENTINEL_DEV": "1",
    }
    failures = run_check(env, dev_mode=True)
    assert failures == 0


# ─────────────────────────────────────────────────────────────────────────────
# 6. main() CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def test_main_exits_0_for_good_env(tmp_path):
    """main() exits 0 when .env contains all required prod vars."""
    env_file = tmp_path / ".env"
    env_file.write_text(GOOD_PROD_ENV, encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main(["--env-file", str(env_file), "--mode", "prod"])
    assert exc_info.value.code == 0


def test_main_exits_1_for_bad_env(tmp_path):
    """main() exits 1 when required prod vars are missing."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AGENTSENTINEL_DEV=1\n",  # only dev flag, nothing else
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as exc_info:
        main(["--env-file", str(env_file), "--mode", "prod"])
    assert exc_info.value.code == 1


def test_main_exits_1_no_env_file(tmp_path, monkeypatch):
    """main() exits 1 when no .env file exists and env is empty."""
    monkeypatch.chdir(tmp_path)
    # Remove any keys that might bleed in from the test environment
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("AGENTSENTINEL_LICENSE_SIGNING_SECRET", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main(["--mode", "prod"])
    assert exc_info.value.code == 1


def test_main_mode_dev_overrides_inference(tmp_path):
    """main() uses --mode dev even when AGENTSENTINEL_DEV is not set."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AGENTSENTINEL_LICENSE_SIGNING_SECRET=" + "x" * 32 + "\n"
        "ADMIN_API_SECRET=" + "y" * 32 + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as exc_info:
        main(["--env-file", str(env_file), "--mode", "dev"])
    assert exc_info.value.code == 0


# ─────────────────────────────────────────────────────────────────────────────
# 7. VARS registry completeness
# ─────────────────────────────────────────────────────────────────────────────

def test_vars_registry_has_required_keys():
    """The VARS registry must include all known critical variables."""
    names = {v.name for v in VARS}
    critical = {
        "AGENTSENTINEL_LICENSE_SIGNING_SECRET",
        "ADMIN_API_SECRET",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "AGENTSENTINEL_DEV",
        "AGENTSENTINEL_DASHBOARD_DEBUG",
    }
    missing = critical - names
    assert not missing, f"VARS registry is missing: {missing}"


def test_vars_registry_no_duplicate_names():
    """Each variable name should appear only once in the VARS registry."""
    names = [v.name for v in VARS]
    seen = set()
    duplicates = []
    for n in names:
        if n in seen:
            duplicates.append(n)
        seen.add(n)
    assert not duplicates, f"Duplicate entries in VARS: {duplicates}"
