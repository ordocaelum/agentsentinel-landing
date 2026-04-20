/**
 * AgentSentinel Dashboard — Theme Switcher
 * Manages theme selection, localStorage persistence, and settings modal.
 */

(function () {
  'use strict';

  /* ── Constants ──────────────────────────────────────────────────────────── */
  const STORAGE_KEY = 'agentsentinel-theme';
  const DEFAULT_THEME = 'mission-control';
  const TRANSITION_DURATION = 300; // ms

  const THEMES = [
    {
      id: 'mission-control',
      name: 'Mission Control',
      desc: 'AI control room',
      iconClass: 'mission-control',
      stub: false,
    },
    {
      id: 'minimal-pro',
      name: 'Minimal Pro',
      desc: 'Clean & focused',
      iconClass: 'minimal-pro',
      stub: true,
    },
    {
      id: 'cyberpunk',
      name: 'Cyberpunk',
      desc: 'Neon on dark',
      iconClass: 'cyberpunk',
      stub: true,
    },
    {
      id: 'arctic',
      name: 'Arctic',
      desc: 'Icy light mode',
      iconClass: 'arctic',
      stub: true,
    },
  ];

  /* ── SVG Icons per theme ──────────────────────────────────────────────── */
  const THEME_ICONS = {
    'mission-control': `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="10" cy="10" r="9" stroke="#0ea5e9" stroke-width="1.5"/>
      <circle cx="10" cy="10" r="5.5" stroke="#06b6d4" stroke-width="1"/>
      <circle cx="10" cy="10" r="2" fill="#0ea5e9"/>
      <line x1="10" y1="1" x2="10" y2="4"   stroke="#0ea5e9" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="10" y1="16" x2="10" y2="19" stroke="#0ea5e9" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="1"  y1="10" x2="4"  y2="10" stroke="#0ea5e9" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="16" y1="10" x2="19" y2="10" stroke="#0ea5e9" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,
    'minimal-pro': `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3" y="3" width="14" height="14" rx="2" stroke="#3b82f6" stroke-width="1.5"/>
      <line x1="6" y1="7" x2="14" y2="7" stroke="#3b82f6" stroke-width="1.2" stroke-linecap="round"/>
      <line x1="6" y1="10" x2="11" y2="10" stroke="#3b82f6" stroke-width="1.2" stroke-linecap="round"/>
      <line x1="6" y1="13" x2="13" y2="13" stroke="#3b82f6" stroke-width="1.2" stroke-linecap="round"/>
    </svg>`,
    'cyberpunk': `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M11 2L4 11h6l-1 7 7-9h-6l1-7z" stroke="#f0e040" stroke-width="1.5" stroke-linejoin="round" fill="rgba(240,224,64,0.1)"/>
    </svg>`,
    'arctic': `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <line x1="10" y1="2" x2="10" y2="18" stroke="#38bdf8" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="2" y1="10" x2="18" y2="10" stroke="#38bdf8" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="4.3" y1="4.3" x2="15.7" y2="15.7" stroke="#38bdf8" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="15.7" y1="4.3" x2="4.3" y2="15.7" stroke="#38bdf8" stroke-width="1.5" stroke-linecap="round"/>
      <circle cx="10" cy="10" r="2.5" fill="#38bdf8" opacity=".4"/>
      <circle cx="10" cy="2"  r="1.2" fill="#38bdf8"/>
      <circle cx="10" cy="18" r="1.2" fill="#38bdf8"/>
      <circle cx="2"  cy="10" r="1.2" fill="#38bdf8"/>
      <circle cx="18" cy="10" r="1.2" fill="#38bdf8"/>
      <circle cx="4.3" cy="4.3" r="1" fill="#7dd3fc"/>
      <circle cx="15.7" cy="15.7" r="1" fill="#7dd3fc"/>
      <circle cx="15.7" cy="4.3" r="1" fill="#7dd3fc"/>
      <circle cx="4.3" cy="15.7" r="1" fill="#7dd3fc"/>
    </svg>`,
  };

  /* ── State ──────────────────────────────────────────────────────────────── */
  let currentTheme = DEFAULT_THEME;
  let pendingTheme = DEFAULT_THEME; // preview without committing
  let settingsOpen = false;

  /* ── Init ────────────────────────────────────────────────────────────────── */
  function init() {
    // Load saved theme or default
    const saved = localStorage.getItem(STORAGE_KEY) || DEFAULT_THEME;
    applyTheme(saved, false);
    buildSettingsModal();
    bindKeyboardShortcut();
    injectSettingsGearIfNeeded();
  }

  /* ── Apply theme ─────────────────────────────────────────────────────────── */
  function applyTheme(themeId, save = true) {
    const theme = THEMES.find(t => t.id === themeId);
    if (!theme || theme.stub) return;

    // Add transition class
    document.documentElement.style.setProperty('transition',
      `background-color ${TRANSITION_DURATION}ms ease, color ${TRANSITION_DURATION}ms ease`);

    document.documentElement.setAttribute('data-theme', themeId);
    currentTheme = themeId;

    if (save) {
      localStorage.setItem(STORAGE_KEY, themeId);
    }

    // Update active state in modal if open
    refreshThemeCards();

    // Remove transition after animation
    setTimeout(() => {
      document.documentElement.style.removeProperty('transition');
    }, TRANSITION_DURATION);
  }

  /* ── Build Settings Modal ────────────────────────────────────────────────── */
  function buildSettingsModal() {
    if (document.getElementById('modal-settings')) return; // already built

    const modal = document.createElement('div');
    modal.id = 'modal-settings';
    modal.className = 'modal-backdrop hidden';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-label', 'Settings');
    modal.addEventListener('click', function (e) {
      if (e.target === modal) closeSettings();
    });

    modal.innerHTML = `
      <div class="mc-settings-modal" id="settings-box">
        <!-- Header -->
        <div class="mc-settings-header">
          <div style="display:flex;align-items:center;gap:10px">
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" style="color:#0ea5e9">
              <circle cx="10" cy="10" r="3" stroke="currentColor" stroke-width="1.5"/>
              <path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.2 4.2l1.4 1.4M14.4 14.4l1.4 1.4M14.4 5.6l-1.4 1.4M5.6 14.4l-1.4 1.4"
                stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
            <span class="mc-settings-title">Settings</span>
          </div>
          <button class="mc-settings-close" onclick="window.agentTheme.closeSettings()" aria-label="Close settings">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </button>
        </div>

        <!-- Body -->
        <div class="mc-settings-body">

          <!-- Appearance section -->
          <div class="mc-settings-section">
            <p class="mc-settings-section-label">Appearance</p>

            <!-- Theme cards -->
            <div class="mc-theme-grid" id="settings-theme-grid">
              ${THEMES.map(theme => `
                <button
                  class="mc-theme-card${theme.stub ? ' stub' : ''}${theme.id === currentTheme ? ' active' : ''}"
                  data-theme-id="${theme.id}"
                  onclick="${theme.stub ? '' : 'window.agentTheme.previewTheme(\''+theme.id+'\')'}"
                  title="${theme.stub ? theme.name+' — Coming soon' : 'Switch to '+theme.name}"
                  ${theme.stub ? 'disabled aria-disabled="true"' : ''}
                >
                  <div class="mc-theme-icon ${theme.iconClass}">
                    ${THEME_ICONS[theme.id] || ''}
                  </div>
                  <div class="mc-theme-info">
                    <div class="name">${theme.name}</div>
                    <div class="desc">${theme.desc}</div>
                  </div>
                </button>
              `).join('')}
            </div>
          </div>

          <!-- Future sections placeholder -->
          <div class="mc-settings-section" style="opacity:.4;pointer-events:none">
            <p class="mc-settings-section-label">Real-time Updates</p>
            <p style="font-size:.75rem;color:var(--text-muted)">Configure refresh interval and live data streaming — coming soon</p>
          </div>

          <div class="mc-settings-section" style="opacity:.4;pointer-events:none">
            <p class="mc-settings-section-label">Export & Data</p>
            <p style="font-size:.75rem;color:var(--text-muted)">CSV / JSON export, data retention policies — coming soon</p>
          </div>

        </div>
      </div>
    `;

    document.body.appendChild(modal);
  }

  /* ── Preview theme (in settings, not committed) ─────────────────────────── */
  function previewTheme(themeId) {
    pendingTheme = themeId;
    applyTheme(themeId, false); // apply visually but don't save yet
    refreshThemeCards();
  }

  /* ── Refresh theme card active states ───────────────────────────────────── */
  function refreshThemeCards() {
    const cards = document.querySelectorAll('.mc-theme-card[data-theme-id]');
    const activeId = document.documentElement.getAttribute('data-theme') || DEFAULT_THEME;
    cards.forEach(card => {
      const isActive = card.dataset.themeId === activeId;
      card.classList.toggle('active', isActive);
    });
  }

  /* ── Open / Close ────────────────────────────────────────────────────────── */
  function openSettings() {
    const modal = document.getElementById('modal-settings');
    if (!modal) {
      buildSettingsModal();
    }
    pendingTheme = currentTheme;
    document.getElementById('modal-settings').classList.remove('hidden');
    settingsOpen = true;
    refreshThemeCards();
    // Allow license-manager.js to inject its section if loaded after modal build
    if (window.licenseManager && typeof window.licenseManager.updateLicenseDisplay === 'function') {
      setTimeout(function () {
        // Inject license section if not yet present
        var body = document.querySelector('.mc-settings-body');
        if (body && !document.getElementById('settings-license-section')) {
          if (window._licenseManagerInject) window._licenseManagerInject();
        } else if (body && document.getElementById('settings-license-section')) {
          window.licenseManager.updateLicenseDisplay();
        }
      }, 20);
    }
  }

  function closeSettings() {
    const modal = document.getElementById('modal-settings');
    if (modal) modal.classList.add('hidden');
    settingsOpen = false;

    // Auto-save on close: commit the pending theme
    if (pendingTheme && pendingTheme !== currentTheme) {
      applyTheme(pendingTheme, true);
    } else {
      // Save whatever is currently applied
      localStorage.setItem(STORAGE_KEY, document.documentElement.getAttribute('data-theme') || DEFAULT_THEME);
    }
  }

  /* ── Keyboard shortcut: Cmd+, / Ctrl+, ─────────────────────────────────── */
  function bindKeyboardShortcut() {
    document.addEventListener('keydown', function (e) {
      const isMac = navigator.platform.toUpperCase().includes('MAC');
      const modifier = isMac ? e.metaKey : e.ctrlKey;
      if (modifier && e.key === ',') {
        e.preventDefault();
        settingsOpen ? closeSettings() : openSettings();
      }
      if (e.key === 'Escape' && settingsOpen) {
        closeSettings();
      }
    });
  }

  /* ── Inject settings gear icon into header ──────────────────────────────── */
  function injectSettingsGearIfNeeded() {
    if (document.getElementById('btn-settings-gear')) return; // already present

    // Find the header button area
    const headerBtns = document.querySelector('header .flex.items-center.gap-2.flex-wrap');
    if (!headerBtns) return;

    const btn = document.createElement('button');
    btn.id = 'btn-settings-gear';
    btn.className = 'btn btn-ghost';
    btn.title = 'Settings (Cmd+,)';
    btn.setAttribute('aria-label', 'Open settings');
    btn.onclick = openSettings;
    btn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <circle cx="10" cy="10" r="3" stroke="currentColor" stroke-width="1.5"/>
        <path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.2 4.2l1.4 1.4M14.4 14.4l1.4 1.4M14.4 5.6l-1.4 1.4M5.6 14.4l-1.4 1.4"
          stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
      <span class="hidden sm:inline">Settings</span>
    `;

    // Insert before last-updated span or at end
    const lastUpdated = document.getElementById('last-updated');
    if (lastUpdated) {
      headerBtns.insertBefore(btn, lastUpdated);
    } else {
      headerBtns.appendChild(btn);
    }
  }

  /* ── Public API ──────────────────────────────────────────────────────────── */
  window.agentTheme = {
    init,
    openSettings,
    closeSettings,
    applyTheme,
    previewTheme,
    getTheme: () => currentTheme,
  };

  /* ── Auto-init when DOM is ready ─────────────────────────────────────────── */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
