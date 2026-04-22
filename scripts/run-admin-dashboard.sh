#!/usr/bin/env bash
# scripts/run-admin-dashboard.sh
#
# One-command launcher for the AgentSentinel admin dashboard (macOS / Linux).
#
# Usage:
#   bash scripts/run-admin-dashboard.sh
#   bash scripts/run-admin-dashboard.sh --port 9090
#   bash scripts/run-admin-dashboard.sh --port 9090 --host 0.0.0.0
#
# Environment:
#   AGENTSENTINEL_DEV         Set to 1 by default (licence-gate bypass for dev).
#                             Override by exporting before calling this script:
#                               AGENTSENTINEL_DEV=0 bash scripts/run-admin-dashboard.sh
#   AGENTSENTINEL_DASHBOARD_PORT   Fallback port when --port is not supplied.
#   AGENTSENTINEL_DASHBOARD_HOST   Fallback host when --host is not supplied.

set -euo pipefail

# ---------------------------------------------------------------------------
# Dev-mode default — opt-in bypass of the paid-licence gate.
# Never set AGENTSENTINEL_DEV=1 in production environments.
# ---------------------------------------------------------------------------
: "${AGENTSENTINEL_DEV:=1}"
export AGENTSENTINEL_DEV

# ---------------------------------------------------------------------------
# Resolve port and host for the printed URL (the Python process resolves them
# independently, but we want to print the right URL here).
# ---------------------------------------------------------------------------
PORT="${AGENTSENTINEL_DASHBOARD_PORT:-8080}"
HOST="${AGENTSENTINEL_DASHBOARD_HOST:-localhost}"

# Parse optional --port / --host args so we can print the correct URL
PASSTHROUGH_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)
            PORT="$2"
            PASSTHROUGH_ARGS+=("$1" "$2")
            shift 2
            ;;
        --host)
            HOST="$2"
            PASSTHROUGH_ARGS+=("$1" "$2")
            shift 2
            ;;
        *)
            PASSTHROUGH_ARGS+=("$1")
            shift
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Print banner
# ---------------------------------------------------------------------------
echo ""
echo "  AgentSentinel Admin Dashboard"
echo "  ─────────────────────────────────────────────────"
echo "  URL:      http://${HOST}:${PORT}/admin"
if [[ "${AGENTSENTINEL_DEV}" == "1" ]]; then
    echo "  Dev mode: ENABLED (AGENTSENTINEL_DEV=1) — licence gate bypassed"
    echo "  ⚠️  Do NOT use AGENTSENTINEL_DEV=1 in production."
fi
echo "  ─────────────────────────────────────────────────"
echo ""

# ---------------------------------------------------------------------------
# Launch — prefer the installed console script, fall back to python -m.
# Errors propagate immediately thanks to set -e.
# ---------------------------------------------------------------------------
if command -v agentsentinel-dashboard &>/dev/null; then
    exec agentsentinel-dashboard "${PASSTHROUGH_ARGS[@]+"${PASSTHROUGH_ARGS[@]}"}"
else
    exec python -m agentsentinel.dashboard "${PASSTHROUGH_ARGS[@]+"${PASSTHROUGH_ARGS[@]}"}"
fi
