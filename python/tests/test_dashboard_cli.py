# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Smoke tests for the dashboard CLI entry point and dev-mode detection.

These tests validate argument parsing and environment-variable resolution
without binding real sockets.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from agentsentinel.dashboard.__main__ import _build_parser, main
from agentsentinel.dashboard.server import _is_dev_mode


# ---------------------------------------------------------------------------
# _is_dev_mode
# ---------------------------------------------------------------------------


def test_is_dev_mode_false_by_default(monkeypatch):
    monkeypatch.delenv("AGENTSENTINEL_DEV", raising=False)
    assert _is_dev_mode() is False


def test_is_dev_mode_true_when_set(monkeypatch):
    monkeypatch.setenv("AGENTSENTINEL_DEV", "1")
    assert _is_dev_mode() is True


def test_is_dev_mode_false_for_other_values(monkeypatch):
    for value in ("0", "true", "yes", "True", ""):
        monkeypatch.setenv("AGENTSENTINEL_DEV", value)
        assert _is_dev_mode() is False, f"Expected False for AGENTSENTINEL_DEV={value!r}"


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def test_parser_defaults():
    parser = _build_parser()
    args = parser.parse_args([])
    assert args.port is None
    assert args.host is None
    assert args.background is False


def test_parser_explicit_port_and_host():
    parser = _build_parser()
    args = parser.parse_args(["--port", "9090", "--host", "0.0.0.0"])
    assert args.port == 9090
    assert args.host == "0.0.0.0"


def test_parser_background_flag():
    parser = _build_parser()
    args = parser.parse_args(["--background"])
    assert args.background is True


def test_parser_invalid_port_exits(capsys):
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--port", "not-a-number"])


# ---------------------------------------------------------------------------
# main() — env-var resolution (no sockets opened)
# ---------------------------------------------------------------------------


def _run_main(argv, env_vars=None, monkeypatch=None):
    """Call main() with patched argv and start_dashboard stubbed out."""
    if env_vars and monkeypatch:
        for key, val in env_vars.items():
            monkeypatch.setenv(key, val)

    mock_start = MagicMock(return_value=MagicMock())  # non-None → success path
    with patch("agentsentinel.dashboard.__main__.start_dashboard", mock_start), \
         patch.object(sys, "argv", ["python -m agentsentinel.dashboard"] + argv):
        main()
    return mock_start


def test_main_defaults_to_port_8080(monkeypatch):
    monkeypatch.delenv("AGENTSENTINEL_DASHBOARD_PORT", raising=False)
    monkeypatch.delenv("AGENTSENTINEL_DASHBOARD_HOST", raising=False)
    mock_start = _run_main([], monkeypatch=monkeypatch)
    _, kwargs = mock_start.call_args
    assert kwargs["port"] == 8080
    assert kwargs["host"] == "localhost"


def test_main_cli_port_overrides_env(monkeypatch):
    monkeypatch.setenv("AGENTSENTINEL_DASHBOARD_PORT", "9999")
    mock_start = _run_main(["--port", "7070"], monkeypatch=monkeypatch)
    _, kwargs = mock_start.call_args
    assert kwargs["port"] == 7070


def test_main_env_port_used_when_no_cli_port(monkeypatch):
    monkeypatch.setenv("AGENTSENTINEL_DASHBOARD_PORT", "9191")
    monkeypatch.delenv("AGENTSENTINEL_DASHBOARD_HOST", raising=False)
    mock_start = _run_main([], monkeypatch=monkeypatch)
    _, kwargs = mock_start.call_args
    assert kwargs["port"] == 9191


def test_main_env_host_used_when_no_cli_host(monkeypatch):
    monkeypatch.setenv("AGENTSENTINEL_DASHBOARD_HOST", "0.0.0.0")
    monkeypatch.delenv("AGENTSENTINEL_DASHBOARD_PORT", raising=False)
    mock_start = _run_main([], monkeypatch=monkeypatch)
    _, kwargs = mock_start.call_args
    assert kwargs["host"] == "0.0.0.0"


def test_main_background_flag_passed_through(monkeypatch):
    monkeypatch.delenv("AGENTSENTINEL_DASHBOARD_PORT", raising=False)
    monkeypatch.delenv("AGENTSENTINEL_DASHBOARD_HOST", raising=False)
    mock_start = _run_main(["--background"], monkeypatch=monkeypatch)
    _, kwargs = mock_start.call_args
    assert kwargs["background"] is True


def test_main_invalid_env_port_falls_back_to_8080(monkeypatch, capsys):
    monkeypatch.setenv("AGENTSENTINEL_DASHBOARD_PORT", "notanumber")
    monkeypatch.delenv("AGENTSENTINEL_DASHBOARD_HOST", raising=False)
    mock_start = _run_main([], monkeypatch=monkeypatch)
    _, kwargs = mock_start.call_args
    assert kwargs["port"] == 8080
    captured = capsys.readouterr()
    assert "8080" in captured.err


# ---------------------------------------------------------------------------
# start_dashboard dev-mode bypass
# ---------------------------------------------------------------------------


def test_start_dashboard_dev_mode_bypasses_licence(monkeypatch, capsys):
    """When AGENTSENTINEL_DEV=1, start_dashboard must NOT call require_feature."""
    monkeypatch.setenv("AGENTSENTINEL_DEV", "1")
    from agentsentinel.dashboard.server import start_dashboard, DashboardServer

    mock_server = MagicMock(spec=DashboardServer)
    with patch("agentsentinel.dashboard.server.DashboardServer", return_value=mock_server), \
         patch("agentsentinel.licensing.require_feature") as mock_require:
        result = start_dashboard(MagicMock(), port=18080, background=True)

    mock_require.assert_not_called()
    captured = capsys.readouterr()
    assert "DEV MODE" in captured.out


def test_start_dashboard_no_dev_mode_enforces_licence(monkeypatch):
    """Without AGENTSENTINEL_DEV=1, start_dashboard must call require_feature."""
    monkeypatch.delenv("AGENTSENTINEL_DEV", raising=False)
    from agentsentinel.dashboard.server import start_dashboard
    from agentsentinel.licensing import FeatureNotAvailableError

    # require_feature is imported lazily inside start_dashboard, so patch
    # the source module directly.
    with patch("agentsentinel.licensing.require_feature",
               side_effect=FeatureNotAvailableError("no dashboard")) as mock_require:
        result = start_dashboard(MagicMock(), port=18081, background=True)

    mock_require.assert_called_once_with("dashboard")
    assert result is None
