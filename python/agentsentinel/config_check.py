# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""
agentsentinel-config-check — validate .env configuration for AgentSentinel.

Reads .env (via stdlib dotenv parsing or python-dotenv if available), checks
each known variable for presence and basic shape, and prints a coloured
pass/fail table.

Exit codes:
  0  — all required variables are present and valid
  1  — one or more required variables are missing or invalid
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional


# ── variable descriptor ───────────────────────────────────────────────────────

class VarSpec(NamedTuple):
    name: str
    required_dev: bool
    required_prod: bool
    description: str
    # callable(value) -> error string or None
    validator: Optional[object] = None


# ── validators ────────────────────────────────────────────────────────────────

def _min_len(n: int):
    def _check(v: str) -> Optional[str]:
        if len(v) < n:
            return f"must be at least {n} characters (got {len(v)})"
        return None
    return _check


def _starts_with(*prefixes: str):
    def _check(v: str) -> Optional[str]:
        if not any(v.startswith(p) for p in prefixes):
            return f"must start with one of {prefixes!r}"
        return None
    return _check


def _starts_with_or_empty(*prefixes: str):
    """Accept empty string (not set) or a value with the given prefix."""
    def _check(v: str) -> Optional[str]:
        if v == "":
            return None
        if not any(v.startswith(p) for p in prefixes):
            return f"must start with one of {prefixes!r}"
        return None
    return _check


def _url_if_set():
    """Validate as a URL only when the value is non-empty."""
    def _check(v: str) -> Optional[str]:
        if not v:
            return None
        if not (v.startswith("http://") or v.startswith("https://")):
            return "must be a URL starting with http:// or https://"
        return None
    return _check


def _hex_len(n: int):
    """Exactly n hex characters."""
    def _check(v: str) -> Optional[str]:
        if not re.fullmatch(r"[0-9a-fA-F]+", v):
            return "must be a hex string"
        if len(v) != n:
            return f"must be exactly {n} hex characters (got {len(v)})"
        return None
    return _check


def _url():
    def _check(v: str) -> Optional[str]:
        if not (v.startswith("http://") or v.startswith("https://")):
            return "must be a URL starting with http:// or https://"
        return None
    return _check


def _boolean():
    def _check(v: str) -> Optional[str]:
        if v not in ("true", "false", "1", "0", "yes", "no", ""):
            return "must be a boolean-like value (true/false/1/0)"
        return None
    return _check


# ── variable registry ─────────────────────────────────────────────────────────

VARS: List[VarSpec] = [
    # ── License signing secret ──────────────────────────────────────────────
    VarSpec(
        name="AGENTSENTINEL_LICENSE_SIGNING_SECRET",
        required_dev=True,
        required_prod=True,
        description="HMAC secret for license key signing/verification",
        validator=_min_len(32),
    ),
    # ── Admin API secret ────────────────────────────────────────────────────
    VarSpec(
        name="ADMIN_API_SECRET",
        required_dev=True,
        required_prod=True,
        description="Bearer token for admin-only endpoints",
        validator=_min_len(32),
    ),
    # ── Supabase ────────────────────────────────────────────────────────────
    VarSpec(
        name="SUPABASE_URL",
        required_dev=False,
        required_prod=True,
        description="Supabase project URL",
        validator=_url(),
    ),
    VarSpec(
        name="SUPABASE_SERVICE_ROLE_KEY",
        required_dev=False,
        required_prod=True,
        description="Supabase service-role key (server-side only)",
        validator=_min_len(20),
    ),
    VarSpec(
        name="SUPABASE_ANON_KEY",
        required_dev=False,
        required_prod=True,
        description="Supabase anon key (safe for client-side)",
        validator=_min_len(20),
    ),
    # ── Stripe ──────────────────────────────────────────────────────────────
    VarSpec(
        name="STRIPE_SECRET_KEY",
        required_dev=False,
        required_prod=True,
        description="Stripe secret API key",
        validator=_starts_with("sk_live_", "sk_test_"),
    ),
    VarSpec(
        name="STRIPE_PUBLISHABLE_KEY",
        required_dev=False,
        required_prod=True,
        description="Stripe publishable key (front-end)",
        validator=_starts_with("pk_live_", "pk_test_"),
    ),
    VarSpec(
        name="STRIPE_WEBHOOK_SECRET",
        required_dev=False,
        required_prod=True,
        description="Stripe webhook signing secret",
        validator=_starts_with("whsec_"),
    ),
    VarSpec(
        name="STRIPE_PRICE_STARTER",
        required_dev=False,
        required_prod=True,
        description="Stripe Price ID for Starter tier",
        validator=_starts_with("price_"),
    ),
    VarSpec(
        name="STRIPE_PRICE_PRO",
        required_dev=False,
        required_prod=True,
        description="Stripe Price ID for Pro tier",
        validator=_starts_with("price_"),
    ),
    VarSpec(
        name="STRIPE_PRICE_PRO_TEAM",
        required_dev=False,
        required_prod=True,
        description="Stripe Price ID for Pro Team tier (base)",
        validator=_starts_with("price_"),
    ),
    VarSpec(
        name="STRIPE_PRICE_ENTERPRISE",
        required_dev=False,
        required_prod=True,
        description="Stripe Price ID for Enterprise tier",
        validator=_starts_with("price_"),
    ),
    VarSpec(
        name="STRIPE_PRICE_PRO_TEAM_BASE",
        required_dev=False,
        required_prod=True,
        description="Stripe Price ID for Pro Team base charge",
        validator=_starts_with("price_"),
    ),
    VarSpec(
        name="STRIPE_PRICE_PRO_TEAM_SEAT",
        required_dev=False,
        required_prod=True,
        description="Stripe Price ID for Pro Team per-seat charge",
        validator=_starts_with("price_"),
    ),
    # ── Email ────────────────────────────────────────────────────────────────
    VarSpec(
        name="RESEND_API_KEY",
        required_dev=False,
        required_prod=True,
        description="Resend API key for transactional email",
        validator=_starts_with("re_"),
    ),
    # ── Site URL ─────────────────────────────────────────────────────────────
    VarSpec(
        name="SITE_BASE_URL",
        required_dev=False,
        required_prod=True,
        description="Site base URL (used for Stripe redirects)",
        validator=_url(),
    ),
    # ── Dev / debug flags ────────────────────────────────────────────────────
    VarSpec(
        name="AGENTSENTINEL_DEV",
        required_dev=False,
        required_prod=False,
        description="Set to 1 to bypass paid-licence gate (dev only)",
        validator=_boolean(),
    ),
    VarSpec(
        name="AGENTSENTINEL_DEV_MODE",
        required_dev=False,
        required_prod=False,
        description="Set to true to bypass paid-licence gate in Python SDK",
        validator=_boolean(),
    ),
    VarSpec(
        name="AGENTSENTINEL_DASHBOARD_DEBUG",
        required_dev=False,
        required_prod=False,
        description="Set to 1 for verbose dashboard server logging",
        validator=_boolean(),
    ),
    # ── SDK vars ─────────────────────────────────────────────────────────────
    VarSpec(
        name="AGENTSENTINEL_LICENSE_KEY",
        required_dev=False,
        required_prod=False,
        description="License key used by the Python SDK",
        validator=_starts_with_or_empty("asv1_", "as_pro_", "as_team_", "as_ent_", "as_starter_"),
    ),
    VarSpec(
        name="AGENTSENTINEL_LICENSE_API",
        required_dev=False,
        required_prod=False,
        description="License validation API URL (SDK override)",
        validator=_url_if_set(),
    ),
]


# ── .env file parser ──────────────────────────────────────────────────────────

def _load_env_file(path: Path) -> Dict[str, str]:
    """
    Parse a .env file and return a dict of key → value.
    Supports:
      - KEY=value
      - KEY="value"
      - KEY='value'
      - # comments
      - blank lines
    Does NOT support multi-line values.
    """
    env: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return env

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, raw_val = line.partition("=")
        key = key.strip()
        raw_val = raw_val.strip()
        # Strip surrounding quotes
        if len(raw_val) >= 2 and raw_val[0] == raw_val[-1] and raw_val[0] in ('"', "'"):
            raw_val = raw_val[1:-1]
        # Remove inline comments (after unquoted value)
        # Only strip if the value isn't quoted already
        env[key] = raw_val
    return env


# ── mode detection ────────────────────────────────────────────────────────────

def _is_dev(env: Dict[str, str]) -> bool:
    """Infer dev mode from AGENTSENTINEL_DEV or AGENTSENTINEL_DEV_MODE."""
    return (
        env.get("AGENTSENTINEL_DEV", "").strip() == "1"
        or env.get("AGENTSENTINEL_DEV_MODE", "").strip().lower() == "true"
    )


# ── runner ────────────────────────────────────────────────────────────────────

def _colour(ok: bool, text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return ("\033[0;32m" if ok else "\033[0;31m") + text + "\033[0m"


def run_check(env: Dict[str, str], dev_mode: Optional[bool] = None) -> int:
    """
    Check each known variable.  Returns the number of failures.

    Parameters
    ----------
    env:
        Dictionary of environment variables (from .env or os.environ).
    dev_mode:
        Override the inferred dev/prod mode.  If None, inferred from env.
    """
    if dev_mode is None:
        dev_mode = _is_dev(env)

    mode_label = "dev" if dev_mode else "prod"

    col_name  = 40
    col_desc  = 45
    col_check = 6

    header = (
        f"{'Variable':<{col_name}}  {'Description':<{col_desc}}  {'Status':<{col_check}}"
    )
    sep = "─" * len(header)

    print(f"\nAgentSentinel config check  (mode: {mode_label})\n{sep}")
    print(header)
    print(sep)

    failures = 0

    for spec in VARS:
        required = spec.required_prod if not dev_mode else spec.required_dev
        value = env.get(spec.name, "")

        if not value:
            if required:
                status = _colour(False, "✗  MISSING")
                failures += 1
            else:
                status = "·  optional"
        elif spec.validator is not None:
            error = spec.validator(value)  # type: ignore[call-arg]
            if error:
                status = _colour(False, f"✗  {error[:30]}")
                failures += 1
            else:
                status = _colour(True, "✓  ok")
        else:
            status = _colour(True, "✓  ok")

        name_col = spec.name[:col_name]
        desc_col = spec.description[:col_desc]
        print(f"{name_col:<{col_name}}  {desc_col:<{col_desc}}  {status}")

    print(sep)
    if failures == 0:
        print(_colour(True, f"All checks passed  ({len(VARS)} variables checked, mode={mode_label})"))
    else:
        print(_colour(False, f"{failures} check(s) failed  (mode={mode_label})"))
    print()

    return failures


# ── console script entry point ────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> None:
    """Entry point for the ``agentsentinel-config-check`` console script."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="agentsentinel-config-check",
        description="Validate AgentSentinel environment configuration.",
    )
    parser.add_argument(
        "--env-file",
        metavar="PATH",
        default=None,
        help=(
            "Path to .env file to validate.  "
            "Defaults to .env in the current directory, "
            "then supabase/.env (both are checked if present)."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["dev", "prod"],
        default=None,
        help="Force dev or prod mode (overrides AGENTSENTINEL_DEV detection).",
    )
    args = parser.parse_args(argv)

    # Collect env: start from os.environ so already-exported vars are respected,
    # then overlay values from .env files (file values take precedence).
    combined: Dict[str, str] = {}

    if args.env_file:
        paths = [Path(args.env_file)]
    else:
        paths = [Path(".env"), Path("supabase/.env")]

    any_file_found = False
    for p in paths:
        if p.exists():
            file_env = _load_env_file(p)
            combined.update(file_env)
            any_file_found = True
            print(f"Loaded {p}  ({len(file_env)} variables)")

    if not any_file_found:
        print(
            "No .env file found.  Run ./scripts/setup-env.sh first, "
            "or pass --env-file <path>.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Also include os.environ for variables not overridden by any file
    for key, val in os.environ.items():
        if key not in combined:
            combined[key] = val

    dev_mode: Optional[bool] = None
    if args.mode == "dev":
        dev_mode = True
    elif args.mode == "prod":
        dev_mode = False

    failures = run_check(combined, dev_mode=dev_mode)
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
