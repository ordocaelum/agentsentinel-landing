# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Command-line interface for AgentSentinel license management."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from datetime import datetime, timezone


def _cmd_keygen(args: argparse.Namespace) -> int:
    """Generate an HMAC-signed license key."""
    from agentsentinel.utils.keygen import SIGNING_SECRET_ENV, generate_license_key

    if not os.environ.get(SIGNING_SECRET_ENV):
        print(
            f"Error: {SIGNING_SECRET_ENV} environment variable is not set.",
            file=sys.stderr,
        )
        print(
            "Run `agentsentinel dev-setup` to generate a signing secret, or set the variable manually.",
            file=sys.stderr,
        )
        return 1

    try:
        key = generate_license_key(args.tier, valid_days=args.days)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(key)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    """Verify a license key (offline HMAC check, then optionally the API)."""
    from agentsentinel.utils.keygen import verify_license_key

    key = args.key
    result = verify_license_key(key)

    if result.get("valid"):
        valid_until = result.get("valid_until")
        if valid_until:
            dt = datetime.fromtimestamp(valid_until, tz=timezone.utc)
            expiry_str = dt.strftime("%Y-%m-%d")
        else:
            expiry_str = "N/A"

        print(f"Key:        {key}")
        print("Valid:      True")
        print(f"Tier:       {result['tier']}")
        print(f"Expires:    {expiry_str}")
        return 0
    else:
        error = result.get("error", "Unknown error")
        # If signing secret is unavailable the offline check cannot run; note it clearly.
        if "Signing secret unavailable" in error:
            print(f"Key:        {key}")
            print("Valid:      Unknown (offline check skipped — signing secret not set)")
            print(
                "Set AGENTSENTINEL_LICENSE_SIGNING_SECRET to verify HMAC-signed keys offline."
            )
        else:
            print(f"Key:        {key}")
            print("Valid:      False")
            print(f"Error:      {error}")
        return 1


def _cmd_dev_setup(args: argparse.Namespace) -> int:
    """Generate a signing secret (if missing) and a signed key for local development."""
    from agentsentinel.utils.keygen import SIGNING_SECRET_ENV, generate_license_key

    signing_secret = os.environ.get(SIGNING_SECRET_ENV)
    generated_secret = False
    if not signing_secret:
        signing_secret = secrets.token_urlsafe(32)
        generated_secret = True

    try:
        key = generate_license_key(args.tier, valid_days=365, secret=signing_secret)
    except ValueError as exc:
        print(f"Error generating key: {exc}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("AgentSentinel Dev Setup")
    print("=" * 60)
    if generated_secret:
        print("\nGenerated a new signing secret (not previously set).")
    else:
        print("\nUsing existing signing secret from environment.")

    print(f"\nTier:    {args.tier}")
    print(f"Key:     {key}")

    print("\n--- Set these environment variables ---")
    print("\nbash / zsh / macOS Terminal:")
    if generated_secret:
        print(f'  export {SIGNING_SECRET_ENV}="{signing_secret}"')  # lgtm[py/clear-text-logging-sensitive-data]
    print(f'  export AGENTSENTINEL_LICENSE_KEY="{key}"')

    print("\nPowerShell:")
    if generated_secret:
        print(f'  $env:{SIGNING_SECRET_ENV} = "{signing_secret}"')  # lgtm[py/clear-text-logging-sensitive-data]
    print(f'  $env:AGENTSENTINEL_LICENSE_KEY = "{key}"')

    print("\nWindows Command Prompt (cmd):")
    if generated_secret:
        print(f'  set {SIGNING_SECRET_ENV}={signing_secret}')  # lgtm[py/clear-text-logging-sensitive-data]
    print(f'  set AGENTSENTINEL_LICENSE_KEY={key}')

    print("\n" + "=" * 60)
    print("After setting the variables, run: agentsentinel status")
    print("=" * 60)
    return 0


def _cmd_status(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Show current license status by reading env vars and validating."""
    from agentsentinel.licensing import LicenseManager

    mgr = LicenseManager()

    info = mgr.get_license_info()

    key_display = os.environ.get("AGENTSENTINEL_LICENSE_KEY", "(not set)")
    if key_display and len(key_display) > 20:
        key_display = key_display[:12] + "..." + key_display[-4:]

    print("=" * 40)
    print("AgentSentinel License Status")
    print("=" * 40)
    print(f"License Key:       {key_display}")
    print(f"Tier:              {info.tier.value}")
    print(f"Valid:             {info.is_valid}")

    if info.valid_until:
        dt = datetime.fromtimestamp(info.valid_until, tz=timezone.utc)
        print(f"Expires:           {dt.strftime('%Y-%m-%d')}")

    if info.validation_error:
        print(f"Note:              {info.validation_error}")

    print()
    print("Feature Access:")
    print(f"  Dashboard:       {'✅' if info.limits.dashboard_enabled else '❌'}")
    print(f"  Integrations:    {'✅' if info.limits.integrations_enabled else '❌'}")
    print(f"  Multi-agent:     {'✅' if info.limits.multi_agent_enabled else '❌'}")
    print(f"  Watermark:       {'required' if info.limits.watermark_required else 'not required'}")
    print(f"  Max agents:      {info.limits.max_agents}")
    print(f"  Max events/mo:   {info.limits.max_events_per_month:,}")
    print("=" * 40)

    return 0 if info.is_valid else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentsentinel",
        description="AgentSentinel license management CLI",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # --- keygen ---
    keygen_parser = subparsers.add_parser(
        "keygen",
        help="Generate an HMAC-signed license key",
    )
    keygen_parser.add_argument(
        "--tier",
        choices=["free", "starter", "pro", "pro_team", "team", "enterprise"],
        default="pro",
        help="License tier: free, starter, pro, pro_team, team, enterprise (default: pro)",
    )
    keygen_parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Key validity in days (default: 365)",
    )
    keygen_parser.set_defaults(func=_cmd_keygen)

    # --- validate ---
    validate_parser = subparsers.add_parser(
        "validate",
        help="Verify that a license key is valid",
    )
    validate_parser.add_argument("key", help="The license key to validate")
    validate_parser.set_defaults(func=_cmd_validate)

    # --- dev-setup ---
    dev_setup_parser = subparsers.add_parser(
        "dev-setup",
        help="Generate a signing secret and a signed key for local development",
    )
    dev_setup_parser.add_argument(
        "--tier",
        choices=["free", "starter", "pro", "pro_team", "team", "enterprise"],
        default="pro",
        help="License tier to generate: free, starter, pro, pro_team, team, enterprise (default: pro)",
    )
    dev_setup_parser.set_defaults(func=_cmd_dev_setup)

    # --- status ---
    status_parser = subparsers.add_parser(
        "status",
        help="Show current license status",
    )
    status_parser.set_defaults(func=_cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
