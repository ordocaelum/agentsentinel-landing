#Requires -Version 5.1
<#
.SYNOPSIS
    AgentSentinel environment bootstrap script for Windows (PowerShell).

.DESCRIPTION
    Copies .env.example -> .env and supabase/.env.example -> supabase/.env,
    substituting __GENERATE_*__ placeholders with cryptographically-secure
    generated values.

.PARAMETER Force
    Overwrite existing .env files without prompting.

.PARAMETER DryRun
    Print what would be written without making any changes.

.PARAMETER Regenerate
    Regenerate a single named secret in the existing .env files, leaving
    everything else untouched.

.EXAMPLE
    .\scripts\setup-env.ps1
    .\scripts\setup-env.ps1 -Force
    .\scripts\setup-env.ps1 -DryRun
    .\scripts\setup-env.ps1 -Regenerate ADMIN_API_SECRET
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$DryRun,
    [string]$Regenerate = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ─── colour helpers ──────────────────────────────────────────────────────────
function Write-Info    { param([string]$Msg) Write-Host "[setup-env] $Msg" -ForegroundColor Cyan }
function Write-Ok      { param([string]$Msg) Write-Host "✓ $Msg" -ForegroundColor Green }
function Write-Warn    { param([string]$Msg) Write-Host "⚠  $Msg" -ForegroundColor Yellow }
function Write-Err     { param([string]$Msg) Write-Host "✗  $Msg" -ForegroundColor Red }

# ─── secret generation ───────────────────────────────────────────────────────
function New-RandomHex32 {
    $rng   = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 32
    $rng.GetBytes($bytes)
    ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
}

function New-RandomBase64_64 {
    $rng   = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 64
    $rng.GetBytes($bytes)
    [Convert]::ToBase64String($bytes)
}

function New-Uuid {
    [guid]::NewGuid().ToString("d")
}

function Get-GeneratedValue {
    param([string]$Placeholder)
    switch ($Placeholder) {
        "__GENERATE_HEX_32__"    { New-RandomHex32 }
        "__GENERATE_BASE64_64__" { New-RandomBase64_64 }
        "__GENERATE_UUID__"      { New-Uuid }
        default                  { throw "Unknown placeholder token: $Placeholder" }
    }
}

# ─── process one .env file ───────────────────────────────────────────────────
function Invoke-ProcessFile {
    param(
        [string]$Src,
        [string]$Dst,
        [bool]  $IsDryRun,
        [string]$RegenKey = ""
    )

    $generatedKeys = @()
    $manualKeys    = @()
    $outputLines   = @()

    $lines = Get-Content -LiteralPath $Src -Encoding UTF8
    foreach ($line in $lines) {
        # Skip comments and blank lines unchanged
        if ($line -match '^\s*#' -or $line -match '^\s*$') {
            $outputLines += $line
            continue
        }

        if ($line -notmatch '=') {
            $outputLines += $line
            continue
        }

        $key = $line.Split('=', 2)[0]
        $val = $line.Substring($key.Length + 1)

        if ($val -match '^__GENERATE_') {
            # If --Regenerate is set and this is NOT the target key, preserve current value
            if ($RegenKey -ne "" -and $key -ne $RegenKey) {
                if (Test-Path $Dst) {
                    $existing = (Get-Content $Dst -Encoding UTF8 |
                                 Where-Object { $_ -match "^${key}=" } |
                                 Select-Object -First 1)
                    if ($existing) {
                        $outputLines += $existing
                        continue
                    }
                }
                $outputLines += $line
                continue
            }

            $newVal = Get-GeneratedValue -Placeholder $val
            $outputLines += "${key}=${newVal}"
            $generatedKeys += $key
        }
        elseif ($val -eq "" -or $val -match '_here$' -or $val -match '_xxxxx$') {
            $outputLines += $line
            $manualKeys  += $key
        }
        else {
            $outputLines += $line
        }
    }

    if ($IsDryRun) {
        Write-Host "`n--- dry-run: would write $Dst ---" -ForegroundColor Magenta
        $outputLines | ForEach-Object { Write-Host $_ }
        Write-Host "--------------------------------------`n" -ForegroundColor Magenta
    }
    else {
        # Write atomically via temp file then rename
        $tmp = "${Dst}.tmp.$$"
        $outputLines | Set-Content -LiteralPath $tmp -Encoding UTF8
        Move-Item -LiteralPath $tmp -Destination $Dst -Force
    }

    foreach ($k in $generatedKeys) { Write-Ok "Generated  $k" }
    foreach ($k in $manualKeys)    { Write-Warn "Manual     $k  <- fill in manually" }
}

# ─── regen a single key in an existing file ──────────────────────────────────
function Invoke-RegenInFile {
    param([string]$Dst, [string]$Key)

    if (-not (Test-Path $Dst)) {
        Write-Err "$Dst does not exist. Run setup-env.ps1 first."
        exit 1
    }

    # Try to find the placeholder token from the example file
    $dir     = Split-Path $Dst -Parent
    $example = if (Test-Path "$dir\.env.example") { "$dir\.env.example" }
               elseif (Test-Path ".env.example")   { ".env.example" }
               else                                 { $null }

    $placeholder = "__GENERATE_HEX_32__"
    if ($example) {
        $exLine = Get-Content $example -Encoding UTF8 |
                  Where-Object { $_ -match "^${Key}=" } |
                  Select-Object -First 1
        if ($exLine -and $exLine.Split('=',2)[1] -match '^__GENERATE_') {
            $placeholder = $exLine.Split('=',2)[1]
        }
    }

    $newVal = Get-GeneratedValue -Placeholder $placeholder
    $content = Get-Content $Dst -Encoding UTF8
    $updated = $content | ForEach-Object {
        if ($_ -match "^${Key}=") { "${Key}=${newVal}" } else { $_ }
    }
    $tmp = "${Dst}.tmp.$$"
    $updated | Set-Content -LiteralPath $tmp -Encoding UTF8
    Move-Item -LiteralPath $tmp -Destination $Dst -Force
    Write-Ok "Regenerated  $Key  in $Dst"
}

# ─── locate repo root ────────────────────────────────────────────────────────
$scriptDir = $PSScriptRoot
$repoRoot  = Split-Path $scriptDir -Parent

$rootExample = Join-Path $repoRoot ".env.example"
$rootEnv     = Join-Path $repoRoot ".env"
$supaExample = Join-Path $repoRoot "supabase\.env.example"
$supaEnv     = Join-Path $repoRoot "supabase\.env"

if (-not (Test-Path $rootExample)) {
    Write-Err "Cannot find $rootExample — are you in the repo root?"
    exit 1
}
if (-not (Test-Path $supaExample)) {
    Write-Err "Cannot find $supaExample — are you in the repo root?"
    exit 1
}

# ─── --Regenerate mode ───────────────────────────────────────────────────────
if ($Regenerate -ne "") {
    Write-Info "Regenerating $Regenerate ..."
    $found = $false
    if (Test-Path $rootEnv) {
        $match = Get-Content $rootEnv -Encoding UTF8 | Where-Object { $_ -match "^${Regenerate}=" }
        if ($match) { Invoke-RegenInFile -Dst $rootEnv -Key $Regenerate; $found = $true }
    }
    if (Test-Path $supaEnv) {
        $match = Get-Content $supaEnv -Encoding UTF8 | Where-Object { $_ -match "^${Regenerate}=" }
        if ($match) { Invoke-RegenInFile -Dst $supaEnv -Key $Regenerate; $found = $true }
    }
    if (-not $found) {
        Write-Err "$Regenerate not found in $rootEnv or $supaEnv"
        exit 1
    }
    exit 0
}

# ─── normal setup mode ───────────────────────────────────────────────────────
Write-Host "`nAgentSentinel — environment setup`n" -ForegroundColor White

# Root .env
if ((Test-Path $rootEnv) -and (-not $Force) -and (-not $DryRun)) {
    Write-Warn "$rootEnv already exists — skipping (use -Force to overwrite)"
} else {
    Write-Info "Processing $rootExample -> $rootEnv"
    Invoke-ProcessFile -Src $rootExample -Dst $rootEnv -IsDryRun $DryRun.IsPresent
    if (-not $DryRun) { Write-Ok "Wrote $rootEnv" }
}

Write-Host ""

# Supabase .env
if ((Test-Path $supaEnv) -and (-not $Force) -and (-not $DryRun)) {
    Write-Warn "$supaEnv already exists — skipping (use -Force to overwrite)"
} else {
    Write-Info "Processing $supaExample -> $supaEnv"
    Invoke-ProcessFile -Src $supaExample -Dst $supaEnv -IsDryRun $DryRun.IsPresent
    if (-not $DryRun) { Write-Ok "Wrote $supaEnv" }
}

Write-Host ""
Write-Info "Next steps:"
Write-Host "  1. Fill in the " -NoNewline
Write-Host "⚠ Manual" -ForegroundColor Yellow -NoNewline
Write-Host " entries above (Stripe keys, Supabase URL, etc.)"
Write-Host "  2. Run " -NoNewline; Write-Host "agentsentinel-config-check" -ForegroundColor White -NoNewline; Write-Host " to validate all required variables"
Write-Host "  3. Run " -NoNewline; Write-Host "agentsentinel-dashboard" -ForegroundColor White -NoNewline; Write-Host " to start the admin dashboard"
Write-Host "  4. Run " -NoNewline; Write-Host "supabase secrets set --env-file supabase/.env" -ForegroundColor White -NoNewline; Write-Host " to push secrets to Supabase"
Write-Host ""
