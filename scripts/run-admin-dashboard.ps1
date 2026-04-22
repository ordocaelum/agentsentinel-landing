# scripts/run-admin-dashboard.ps1
#
# One-command launcher for the AgentSentinel admin dashboard (Windows PowerShell).
#
# Usage:
#   .\scripts\run-admin-dashboard.ps1
#   .\scripts\run-admin-dashboard.ps1 -Port 9090
#   .\scripts\run-admin-dashboard.ps1 -Port 9090 -Host 0.0.0.0
#
# Environment:
#   AGENTSENTINEL_DEV         Set to "1" by default (licence-gate bypass for dev).
#                             Override by setting the variable before calling:
#                               $env:AGENTSENTINEL_DEV = "0"
#                               .\scripts\run-admin-dashboard.ps1
#   AGENTSENTINEL_DASHBOARD_PORT   Fallback port when -Port is not supplied.
#   AGENTSENTINEL_DASHBOARD_HOST   Fallback host when -Host is not supplied.

[CmdletBinding()]
param(
    [int]    $Port     = 0,
    [string] $BindHost = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Dev-mode default — opt-in bypass of the paid-licence gate.
# Never set AGENTSENTINEL_DEV=1 in production environments.
# ---------------------------------------------------------------------------
if (-not $env:AGENTSENTINEL_DEV) {
    $env:AGENTSENTINEL_DEV = "1"
}

# ---------------------------------------------------------------------------
# Resolve port and host for the printed URL.
# ---------------------------------------------------------------------------
$ResolvedPort = if ($Port -ne 0) { $Port }
                elseif ($env:AGENTSENTINEL_DASHBOARD_PORT) { [int]$env:AGENTSENTINEL_DASHBOARD_PORT }
                else { 8080 }

$ResolvedHost = if ($BindHost -ne "") { $BindHost }
                elseif ($env:AGENTSENTINEL_DASHBOARD_HOST) { $env:AGENTSENTINEL_DASHBOARD_HOST }
                else { "localhost" }

# ---------------------------------------------------------------------------
# Print banner
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "  AgentSentinel Admin Dashboard"
Write-Host "  -------------------------------------------------"
Write-Host "  URL:      http://${ResolvedHost}:${ResolvedPort}/admin"
if ($env:AGENTSENTINEL_DEV -eq "1") {
    Write-Host "  Dev mode: ENABLED (AGENTSENTINEL_DEV=1) -- licence gate bypassed"
    Write-Host "  WARNING: Do NOT use AGENTSENTINEL_DEV=1 in production."
}
Write-Host "  -------------------------------------------------"
Write-Host ""

# ---------------------------------------------------------------------------
# Build argument list and launch.
# Prefer the installed console script; fall back to python -m.
# ---------------------------------------------------------------------------

# Only pass flags that were explicitly supplied by the caller.
$DashArgs = @()
if ($Port -ne 0) {
    $DashArgs += "--port", "$Port"
}
if ($BindHost -ne "") {
    $DashArgs += "--host", "$BindHost"
}

$consoleScript = Get-Command agentsentinel-dashboard -ErrorAction SilentlyContinue
if ($consoleScript) {
    & agentsentinel-dashboard @DashArgs
} else {
    python -m agentsentinel.dashboard @DashArgs
}
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
