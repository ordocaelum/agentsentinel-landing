/**
 * AgentSentinel Dashboard — License Manager
 * Handles license key activation, storage, display, and usage stats.
 *
 * The Supabase project URL is read from the `data-supabase-url` attribute on
 * this script tag.  Set it when deploying:
 *
 *   <script src="./js/license-manager.js" data-supabase-url="https://xxxxx.supabase.co"></script>
 *
 * If the attribute is absent the module degrades gracefully — the license
 * activation form still renders but validation calls are skipped.
 */

(function () {
  'use strict';

  /* ── Constants ──────────────────────────────────────────────────────────── */
  const STORAGE_KEY = 'agentsentinel-license';

  // Read Supabase URL from script tag attribute (optional)
  const scriptTag = document.currentScript || (function () {
    var scripts = document.getElementsByTagName('script');
    return scripts[scripts.length - 1];
  })();
  const SUPABASE_URL = (scriptTag && scriptTag.getAttribute('data-supabase-url')) || '';
  const VALIDATE_LICENSE_URL = SUPABASE_URL
    ? `${SUPABASE_URL}/functions/v1/validate-license`
    : '';

  /* ── State ──────────────────────────────────────────────────────────────── */
  let currentLicense = null;

  /* ── Load saved license ─────────────────────────────────────────────────── */
  function loadSavedLicense() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        currentLicense = JSON.parse(saved);
        updateLicenseDisplay();
        updateLicenseBadge();
      }
    } catch (e) {
      console.warn('[LicenseManager] Failed to load saved license:', e);
    }
  }

  /* ── Activate license ───────────────────────────────────────────────────── */
  async function activateLicense() {
    const input = document.getElementById('license-key-input');
    const statusDiv = document.getElementById('license-status');
    if (!input || !statusDiv) return;

    const key = input.value.trim();
    if (!key) {
      statusDiv.innerHTML = '<span style="color:#f59e0b">Enter a license key</span>';
      return;
    }

    statusDiv.innerHTML = '<span style="color:#94a3b8">Validating…</span>';

    if (!VALIDATE_LICENSE_URL) {
      // No Supabase URL configured — store locally without remote validation
      // (useful for development or offline use)
      currentLicense = {
        key: key,
        tier: 'unknown',
        limits: { max_agents: '—', max_events_per_month: '—' },
        features: {},
        activated_at: new Date().toISOString(),
        locally_stored: true,
      };
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(currentLicense)); } catch (e) {}
      statusDiv.innerHTML = '<span style="color:#f59e0b">⚠ License stored locally (no remote validation configured)</span>';
      input.value = '';
      updateLicenseDisplay();
      updateLicenseBadge();
      return;
    }

    try {
      const response = await fetch(VALIDATE_LICENSE_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-validation-source': 'dashboard',
        },
        body: JSON.stringify({ license_key: key }),
      });

      const result = await response.json();

      if (result.valid) {
        currentLicense = {
          key: key,
          tier: result.tier,
          limits: result.limits,
          features: result.features,
          activated_at: new Date().toISOString(),
        };

        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(currentLicense)); } catch (e) {}

        statusDiv.innerHTML = '<span style="color:#34d399">✓ License activated!</span>';
        input.value = '';

        updateLicenseDisplay();
        updateLicenseBadge();
      } else {
        statusDiv.innerHTML = `<span style="color:#f87171">✗ ${result.error || 'Invalid license key'}</span>`;
      }
    } catch (err) {
      statusDiv.innerHTML = '<span style="color:#f87171">Error validating license. Check your connection and try again.</span>';
      console.error('[LicenseManager] Validation error:', err);
    }
  }

  /* ── Update license display in settings modal ───────────────────────────── */
  function updateLicenseDisplay() {
    const tierEl = document.getElementById('current-tier');
    const statusEl = document.getElementById('current-status');
    const agentsEl = document.getElementById('current-agents');
    const eventsEl = document.getElementById('current-events');
    const keyDisplayEl = document.getElementById('active-key-display');
    const activeKeySection = document.getElementById('active-key-section');
    const usageSection = document.getElementById('usage-section');
    const licenseInfoEl = document.getElementById('license-info');

    if (!currentLicense) {
      if (licenseInfoEl) licenseInfoEl.style.display = 'none';
      if (activeKeySection) activeKeySection.style.display = 'none';
      if (usageSection) usageSection.style.display = 'none';
      return;
    }

    if (licenseInfoEl) licenseInfoEl.style.display = '';

    const tierName = currentLicense.tier ? currentLicense.tier.toUpperCase().replace('_', ' ') : '—';
    if (tierEl) tierEl.textContent = tierName;
    if (statusEl) {
      statusEl.textContent = 'ACTIVE';
      statusEl.style.color = '#34d399';
    }

    const limits = currentLicense.limits || {};
    if (agentsEl) {
      agentsEl.textContent = limits.max_agents === 999999 || limits.max_agents === '—'
        ? (limits.max_agents === 999999 ? '∞' : '—')
        : String(limits.max_agents);
    }
    if (eventsEl) {
      eventsEl.textContent = limits.max_events_per_month === 999999999 || limits.max_events_per_month === '—'
        ? (limits.max_events_per_month === 999999999 ? '∞' : '—')
        : Number(limits.max_events_per_month).toLocaleString();
    }

    if (keyDisplayEl) {
      keyDisplayEl.value = currentLicense.key || '';
      keyDisplayEl.type = 'password';
    }
    if (activeKeySection) activeKeySection.style.display = '';
    if (usageSection) usageSection.style.display = '';

    // Update usage placeholders
    const callsStat = document.getElementById('calls-stat');
    const costStat = document.getElementById('cost-stat');
    if (callsStat) callsStat.textContent = '0 / Unlimited';
    if (costStat) costStat.textContent = '$0 / Unlimited';
  }

  /* ── Update license badge in header ─────────────────────────────────────── */
  function updateLicenseBadge() {
    const badge = document.getElementById('license-badge');
    const tierEl = document.getElementById('license-tier');
    const agentsEl = document.getElementById('license-agents');

    if (!badge) return;

    if (!currentLicense) {
      badge.style.display = 'none';
      return;
    }

    const tierName = currentLicense.tier
      ? currentLicense.tier.toUpperCase().replace('_', ' ')
      : '?';
    if (tierEl) tierEl.textContent = tierName;

    const maxAgents = currentLicense.limits && currentLicense.limits.max_agents;
    if (agentsEl) {
      agentsEl.textContent = maxAgents === 999999
        ? '• ∞ agents'
        : maxAgents
        ? `• ${maxAgents} agent${maxAgents === 1 ? '' : 's'}`
        : '';
    }

    badge.style.display = 'flex';
  }

  /* ── Reveal / hide key toggle ────────────────────────────────────────────── */
  function toggleKeyReveal() {
    const input = document.getElementById('active-key-display');
    const btn = document.getElementById('license-reveal-btn');
    if (!input) return;

    if (input.type === 'password') {
      input.type = 'text';
      if (btn) btn.textContent = '🙈';
    } else {
      input.type = 'password';
      if (btn) btn.textContent = '👁️';
    }
  }

  /* ── Copy active key ─────────────────────────────────────────────────────── */
  async function copyActiveKey() {
    const input = document.getElementById('active-key-display');
    const btn = document.getElementById('license-copy-btn');
    if (!input || !input.value) return;

    try {
      await navigator.clipboard.writeText(input.value);
      if (btn) {
        btn.textContent = '✓';
        setTimeout(() => { btn.textContent = '📋'; }, 2000);
      }
    } catch (e) {
      console.warn('[LicenseManager] Clipboard write failed:', e);
    }
  }

  /* ── Remove license ──────────────────────────────────────────────────────── */
  function removeLicense() {
    currentLicense = null;
    try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
    updateLicenseDisplay();
    updateLicenseBadge();
    const statusDiv = document.getElementById('license-status');
    if (statusDiv) statusDiv.innerHTML = '<span style="color:#94a3b8">License removed.</span>';
  }

  /* ── Build license section HTML ─────────────────────────────────────────── */
  function buildLicenseSection() {
    return `
      <div class="mc-settings-section" id="settings-license-section">
        <p class="mc-settings-section-label">License</p>

        <!-- Current License Info -->
        <div id="license-info" style="background:rgba(15,23,42,0.5);border:1px solid rgba(51,65,85,0.6);border-radius:10px;padding:12px;margin-bottom:12px;${currentLicense ? '' : 'display:none'}">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
            <div>
              <p style="font-size:.7rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em">Tier</p>
              <p id="current-tier" style="font-size:1rem;font-weight:700;color:#e2e8f0">—</p>
            </div>
            <div>
              <p style="font-size:.7rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em">Status</p>
              <p id="current-status" style="font-size:1rem;font-weight:700;color:#34d399">—</p>
            </div>
            <div>
              <p style="font-size:.7rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em">Max Agents</p>
              <p id="current-agents" style="font-size:1rem;font-weight:700;color:#e2e8f0">—</p>
            </div>
            <div>
              <p style="font-size:.7rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em">Events/Month</p>
              <p id="current-events" style="font-size:1rem;font-weight:700;color:#e2e8f0">—</p>
            </div>
          </div>
        </div>

        <!-- License Key Input -->
        <div style="margin-bottom:12px">
          <p style="font-size:.7rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px">Activate License</p>
          <div style="display:flex;gap:8px">
            <input
              id="license-key-input"
              type="password"
              placeholder="Paste your license key (asv1_… or as_pro_…)"
              style="flex:1;background:rgba(15,23,42,0.8);border:1px solid rgba(51,65,85,0.6);border-radius:8px;padding:8px 12px;color:#e2e8f0;font-size:.8rem;outline:none;font-family:'JetBrains Mono',monospace"
            />
            <button
              onclick="window.licenseManager.activateLicense()"
              style="background:#0ea5e9;color:#fff;border:none;border-radius:8px;padding:8px 14px;font-weight:600;font-size:.8rem;cursor:pointer;white-space:nowrap"
            >
              Activate
            </button>
          </div>
          <div id="license-status" style="font-size:.75rem;margin-top:5px;min-height:1rem"></div>
        </div>

        <!-- Current Key Display -->
        <div id="active-key-section" style="${currentLicense ? '' : 'display:none'}margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid rgba(51,65,85,0.4)">
          <p style="font-size:.7rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px">Current License Key</p>
          <div style="display:flex;gap:6px">
            <input
              id="active-key-display"
              type="password"
              readonly
              style="flex:1;background:rgba(15,23,42,0.8);border:1px solid rgba(51,65,85,0.6);border-radius:8px;padding:8px 12px;color:#34d399;font-size:.75rem;font-family:'JetBrains Mono',monospace;outline:none"
            />
            <button
              id="license-reveal-btn"
              onclick="window.licenseManager.toggleKeyReveal()"
              title="Show/hide key"
              style="background:rgba(30,41,59,0.8);border:1px solid rgba(51,65,85,0.6);border-radius:8px;padding:8px 10px;cursor:pointer;font-size:.9rem"
            >👁️</button>
            <button
              id="license-copy-btn"
              onclick="window.licenseManager.copyActiveKey()"
              title="Copy key"
              style="background:rgba(30,41,59,0.8);border:1px solid rgba(51,65,85,0.6);border-radius:8px;padding:8px 10px;cursor:pointer;font-size:.9rem"
            >📋</button>
          </div>
        </div>

        <!-- Usage Stats -->
        <div id="usage-section" style="${currentLicense ? '' : 'display:none'}margin-bottom:12px">
          <p style="font-size:.7rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Usage This Month</p>
          <div style="display:flex;justify-content:space-between;font-size:.75rem;margin-bottom:4px">
            <span style="color:#94a3b8">Calls</span>
            <span id="calls-stat" style="color:#e2e8f0">0 / Unlimited</span>
          </div>
          <div style="height:6px;background:#1e293b;border-radius:3px;overflow:hidden;margin-bottom:8px">
            <div style="height:100%;background:#10b981;width:0%"></div>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:.75rem;margin-bottom:4px">
            <span style="color:#94a3b8">Cost</span>
            <span id="cost-stat" style="color:#e2e8f0">$0 / Unlimited</span>
          </div>
          <div style="height:6px;background:#1e293b;border-radius:3px;overflow:hidden">
            <div style="height:100%;background:#0ea5e9;width:0%"></div>
          </div>
        </div>

        <!-- Help Links -->
        <div style="padding-top:10px;border-top:1px solid rgba(51,65,85,0.4)">
          <p style="font-size:.7rem;color:#64748b;margin-bottom:8px">Need help?</p>
          <div style="display:flex;flex-direction:column;gap:4px">
            <a href="/getting-started.html" target="_blank" style="color:#38bdf8;font-size:.75rem;text-decoration:none">→ Getting Started Guide</a>
            <a href="/portal.html" target="_blank" style="color:#38bdf8;font-size:.75rem;text-decoration:none">→ View License in Portal</a>
            <a href="mailto:support@agentsentinel.net" style="color:#38bdf8;font-size:.75rem;text-decoration:none">→ Contact Support</a>
          </div>
        </div>
      </div>
    `;
  }

  /* ── Inject license section into existing settings modal ────────────────── */
  function injectLicenseSection() {
    // Wait for the settings modal to be built by theme-switcher.js
    const tryInject = function () {
      const settingsBody = document.querySelector('.mc-settings-body');
      if (!settingsBody) return false;
      if (document.getElementById('settings-license-section')) return true;

      settingsBody.insertAdjacentHTML('beforeend', buildLicenseSection());
      updateLicenseDisplay();
      return true;
    };

    // Attempt immediately (modal may already exist)
    if (!tryInject()) {
      // Poll until the modal is built (theme-switcher creates it lazily on first open)
      const btn = document.getElementById('btn-settings-gear');
      if (btn) {
        const origClick = btn.onclick;
        btn.onclick = function (e) {
          if (origClick) origClick.call(this, e);
          setTimeout(tryInject, 50);
        };
      }
    }
  }

  /* ── Expose public API ───────────────────────────────────────────────────── */
  window.licenseManager = {
    activateLicense,
    toggleKeyReveal,
    copyActiveKey,
    removeLicense,
    updateLicenseDisplay,
    updateLicenseBadge,
  };

  // Expose inject function for theme-switcher.js to call when modal is opened
  window._licenseManagerInject = injectLicenseSection;

  /* ── Initialise on DOMContentLoaded ─────────────────────────────────────── */
  function init() {
    loadSavedLicense();
    injectLicenseSection();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
