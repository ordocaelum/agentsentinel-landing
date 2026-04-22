# AgentSentinel Admin Dashboard — Local Development Guide

> **Audience:** Developers and administrators running the AgentSentinel admin
> dashboard on their local machine.
>
> For the full production/backend reference (Supabase, Edge Functions, Stripe),
> see [ADMIN_DASHBOARD.md](../ADMIN_DASHBOARD.md) in the repository root.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Step-by-Step Setup](#3-step-by-step-setup)
4. [Run Commands](#4-run-commands)
5. [Environment Variables](#5-environment-variables)
6. [Authentication Model](#6-authentication-model)
7. [One-Command Launch Scripts](#7-one-command-launch-scripts)
8. [Verification Checklist](#8-verification-checklist)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Overview

The AgentSentinel Admin Dashboard is a browser-based Single-Page Application
(SPA) served by the Python `agentsentinel` package at the `/admin` path. The
Python process serves only static files; all live data is fetched directly from
Supabase by the browser.

```
You (browser)  ──────────────────────────────────────────────────────────►  /admin
                                                                              │
                            python -m agentsentinel.dashboard                 │
                            (stdlib HTTP server, no extra deps)               │
                                                                              ▼
                                                                   Supabase REST / Edge Fns
```

---

## 2. Prerequisites

| Requirement | Minimum version |
|---|---|
| Python | 3.9 |
| pip | any recent version |

No other dependencies are required. The server is built on the Python standard
library only.

---

## 3. Step-by-Step Setup

```bash
# 1. Clone the repository (skip if already done)
git clone https://github.com/ordocaelum/agentsentinel-landing.git
cd agentsentinel-landing

# 2. Install the Python package in editable mode
#    This ensures 'import agentsentinel' resolves to *this* repo,
#    not a version installed from PyPI.
pip install -e python/

# 3. Verify the install resolves to the repo
python -c "import agentsentinel; print(agentsentinel.__file__)"
# Expected: .../agentsentinel-landing/python/agentsentinel/__init__.py

# 4. Start the dashboard (see Section 4 for all command forms)
AGENTSENTINEL_DEV=1 python -m agentsentinel.dashboard
```

---

## 4. Run Commands

### Default (port 8080, localhost)

```bash
AGENTSENTINEL_DEV=1 python -m agentsentinel.dashboard
```

Access at: **http://localhost:8080/admin**

### Explicit port and host

```bash
AGENTSENTINEL_DEV=1 python -m agentsentinel.dashboard --port 8080 --host localhost
```

### Custom port

```bash
AGENTSENTINEL_DEV=1 python -m agentsentinel.dashboard --port 9090
```

Access at: **http://localhost:9090/admin**

### Non-blocking (background thread)

```bash
AGENTSENTINEL_DEV=1 python -m agentsentinel.dashboard --background
```

Returns immediately; useful when embedding in a larger script.

### Windows PowerShell equivalent

```powershell
$env:AGENTSENTINEL_DEV = "1"
python -m agentsentinel.dashboard
```

---

## 5. Environment Variables

| Variable | Description | Default |
|---|---|---|
| `AGENTSENTINEL_DEV` | Set to `1` to bypass the paid-licence gate in local development. **Never set in production.** | *(unset)* |
| `AGENTSENTINEL_DASHBOARD_PORT` | Default port when `--port` is not supplied on the command line. | `8080` |
| `AGENTSENTINEL_DASHBOARD_HOST` | Default host/interface when `--host` is not supplied. | `localhost` |

**Priority order for port/host resolution:**

1. CLI argument (`--port`, `--host`) — highest priority
2. Environment variable (`AGENTSENTINEL_DASHBOARD_PORT`, `AGENTSENTINEL_DASHBOARD_HOST`)
3. Built-in default (`8080` / `localhost`)

---

## 6. Authentication Model

### Local development (dev mode)

**There is no login prompt in local dev mode.** When `AGENTSENTINEL_DEV=1` is
set:

- The paid-licence gate is bypassed entirely.
- The server binds to `localhost` by default, so it is only reachable from
  your own machine.
- No password, token, or session cookie is required to load `/admin`.

**Security caveats:**

- `AGENTSENTINEL_DEV=1` is **opt-in only**. Never set it in a shared or
  production environment.
- Do not bind to `0.0.0.0` with `AGENTSENTINEL_DEV=1` — this would expose an
  unauthenticated admin panel to every host on the network.
- The browser-side admin SPA stores the Supabase service-role key in
  `sessionStorage` (cleared when the tab closes). Treat this key with the same
  care as a root password.

### Production

In production, the licence gate enforces a valid paid licence key before the
server starts. Direct network access to the dashboard endpoint should be
restricted by a firewall or reverse-proxy layer.

---

## 7. One-Command Launch Scripts

Two convenience wrappers live in `scripts/`:

| Script | Platform |
|---|---|
| `scripts/run-admin-dashboard.sh` | macOS / Linux (bash) |
| `scripts/run-admin-dashboard.ps1` | Windows PowerShell |

Both scripts:

- Set `AGENTSENTINEL_DEV=1` by default (can be overridden by the caller).
- Accept optional `--port` and `--host` arguments and pass them through.
- Print the full access URL (including `/admin`) before starting.
- Exit immediately on Python errors (fail-fast).

### bash (macOS/Linux)

```bash
# Default
bash scripts/run-admin-dashboard.sh

# Custom port and host
bash scripts/run-admin-dashboard.sh --port 9090 --host 0.0.0.0
```

### PowerShell (Windows)

```powershell
# Default
.\scripts\run-admin-dashboard.ps1

# Custom port
.\scripts\run-admin-dashboard.ps1 -Port 9090

# Custom port and host
.\scripts\run-admin-dashboard.ps1 -Port 9090 -BindHost 0.0.0.0
```

---

## 8. Verification Checklist

Run these checks after starting the server to confirm everything is working:

**Terminal output** — you should see:

```
⚠️  [AgentSentinel] DEV MODE ACTIVE — licence check bypassed (AGENTSENTINEL_DEV=1).  Do NOT use this setting in production.
[AgentSentinel] Starting admin dashboard at http://localhost:8080/admin
[AgentSentinel] Press Ctrl-C to stop.
```

**curl (HTTP 200)**

```bash
curl -I http://localhost:8080/admin
# Expected: HTTP/1.0 200 OK  (or HTTP/1.1 200 OK)
```

**Browser**

Open **http://localhost:8080/admin** — you should see the AgentSentinel Admin
Dashboard SPA without any login screen.

**Correct package import**

```bash
python -c "import agentsentinel; print(agentsentinel.__file__)"
# Expected path ends with: .../python/agentsentinel/__init__.py
```

---

## 9. Troubleshooting

### Port already in use

```
OSError: [Errno 98] Address already in use
```

Find and stop the conflicting process:

```bash
# macOS/Linux
lsof -ti :8080 | xargs kill -9

# Windows PowerShell
Get-Process -Id (Get-NetTCPConnection -LocalPort 8080).OwningProcess | Stop-Process
```

Or start on a different port:

```bash
AGENTSENTINEL_DEV=1 python -m agentsentinel.dashboard --port 8081
```

---

### Wrong Python environment / wrong package import

If you see `ModuleNotFoundError: No module named 'agentsentinel'` or behaviour
that doesn't match the repo source, your shell is using the wrong Python
interpreter or a PyPI-installed version of the package.

Diagnose:

```bash
# Check which Python is active
which python   # macOS/Linux
where python   # Windows

# Check which agentsentinel is imported
python -c "import agentsentinel; print(agentsentinel.__file__)"
```

Fix by installing the local package in editable mode into the active
environment:

```bash
pip install -e python/
```

---

### Dev mode not enabled

```
FeatureNotAvailableError: dashboard feature requires a paid licence
```

You forgot to set `AGENTSENTINEL_DEV=1`. Either:

```bash
# Inline (single command)
AGENTSENTINEL_DEV=1 python -m agentsentinel.dashboard

# Or export for the session
export AGENTSENTINEL_DEV=1
python -m agentsentinel.dashboard
```

On Windows PowerShell:

```powershell
$env:AGENTSENTINEL_DEV = "1"
python -m agentsentinel.dashboard
```

---

### Can't reach `/admin` in the browser

1. **Check the server is running** — the terminal must show "Press Ctrl-C to
   stop." and remain open.

2. **Check the port** — the URL must match what was printed: e.g.,
   `http://localhost:8080/admin`.

3. **Check the path** — `/admin` (not `/`, not `/admin/`).

4. **curl test**:

   ```bash
   curl -v http://localhost:8080/admin
   ```

   - If you get `Connection refused`, the server is not running or bound to a
     different port.
   - If you get a 404, navigate to the exact path shown in the startup message.

5. **Firewall** — on some systems, even `localhost` connections can be blocked.
   Temporarily disable the firewall or add an exception for the port.
