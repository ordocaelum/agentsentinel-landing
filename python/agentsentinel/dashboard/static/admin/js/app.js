/**
 * AgentSentinel Admin Dashboard — Main App Controller
 * SPA router with lazy-loaded page modules.
 */

import { getConfig, saveConfig, hasConfig, verifyAdminAccess } from './utils/auth.js';
import { notify } from './components/notifications.js';
import { openModal, closeModal } from './components/modal.js';

// ── Page registry ──────────────────────────────────────────────────────────
const PAGES = {
  overview: () => import('./pages/overview.js'),
  licenses: () => import('./pages/licenses.js'),
  promos:   () => import('./pages/promos.js'),
  users:    () => import('./pages/users.js'),
  metrics:  () => import('./pages/metrics.js'),
  webhooks: () => import('./pages/webhooks.js'),
  system:   () => import('./pages/system.js'),
  audit:    () => import('./pages/audit.js'),
};

// ── Nav config ─────────────────────────────────────────────────────────────
const NAV = [
  { id: 'overview', label: 'Overview',        icon: '📊', group: 'main' },
  { id: 'licenses', label: 'Licenses',        icon: '🎫', group: 'main' },
  { id: 'promos',   label: 'Promo Codes',     icon: '🎟', group: 'main' },
  { id: 'users',    label: 'Users',           icon: '👥', group: 'main' },
  { id: 'metrics',  label: 'Metrics',         icon: '📈', group: 'analytics' },
  { id: 'webhooks', label: 'Webhooks',        icon: '🔗', group: 'analytics' },
  { id: 'system',   label: 'System',          icon: '⚙️', group: 'settings' },
  { id: 'audit',    label: 'Audit Log',       icon: '📋', group: 'settings' },
];

// ── App state ──────────────────────────────────────────────────────────────
let _currentPage = null;

class AdminApp {
  constructor() {
    this.currentPage = 'overview';
  }

  /** Boot sequence */
  async init() {
    // Always render setup screen if no config
    if (!hasConfig()) {
      this._showSetup();
      return;
    }
    this._showApp();
    this.navigate(this._getPageFromHash() || 'overview');
  }

  // ── Setup screen ──────────────────────────────────────────────────────────
  _showSetup() {
    document.getElementById('setup-screen').classList.remove('hidden');
    document.getElementById('admin-app').classList.add('hidden');
    this._bindSetupForm();
  }

  _bindSetupForm() {
    const form = document.getElementById('setup-form');
    if (!form) return;

    document.getElementById('toggle-setup-key')?.addEventListener('click', () => {
      const inp = document.getElementById('setup-key');
      if (inp) inp.type = inp.type === 'password' ? 'text' : 'password';
    });
    document.getElementById('toggle-setup-secret')?.addEventListener('click', () => {
      const inp = document.getElementById('setup-secret');
      if (inp) inp.type = inp.type === 'password' ? 'text' : 'password';
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const url    = document.getElementById('setup-url').value.trim().replace(/\/+$/, '');
      const key    = document.getElementById('setup-key').value.trim();
      const secret = document.getElementById('setup-secret').value.trim();
      const errEl  = document.getElementById('setup-error');

      if (!url || !key) {
        if (errEl) errEl.textContent = 'URL and service key are required';
        return;
      }

      const btn = document.getElementById('setup-submit');
      btn.disabled = true;
      btn.textContent = 'Connecting…';
      if (errEl) errEl.textContent = '';

      const ok = await verifyAdminAccess(url, key);
      if (!ok) {
        if (errEl) errEl.textContent = 'Connection failed — check your URL and key';
        btn.disabled = false;
        btn.textContent = 'Connect & Enter Dashboard';
        return;
      }

      saveConfig({ supabaseUrl: url, supabaseKey: key, adminApiSecret: secret || null });
      this._showApp();
      this.navigate('overview');
    });
  }

  // ── Main app ───────────────────────────────────────────────────────────────
  _showApp() {
    document.getElementById('setup-screen').classList.add('hidden');
    document.getElementById('admin-app').classList.remove('hidden');
    this._buildSidebar();
    this._bindGlobalEvents();
  }

  _buildSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;

    const groups = {
      main:      { label: 'Main', items: [] },
      analytics: { label: 'Analytics', items: [] },
      settings:  { label: 'Settings', items: [] },
    };

    NAV.forEach(n => groups[n.group]?.items.push(n));

    const navHtml = Object.entries(groups).map(([, g]) => `
      <div class="nav-section-label">${g.label}</div>
      ${g.items.map(n => `
        <a class="nav-item" id="nav-${n.id}" href="#${n.id}" data-page="${n.id}" title="${n.label}">
          <span class="nav-icon">${n.icon}</span>
          <span class="nav-label">${n.label}</span>
        </a>
      `).join('')}
    `).join('');

    const navContainer = document.getElementById('nav-items');
    if (navContainer) navContainer.innerHTML = navHtml;

    sidebar.querySelectorAll('.nav-item').forEach(el => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        this.navigate(el.dataset.page);
      });
    });
  }

  _bindGlobalEvents() {
    // Sidebar toggle
    document.getElementById('btn-sidebar-toggle')?.addEventListener('click', () => {
      document.getElementById('sidebar')?.classList.toggle('collapsed');
    });

    // Sign out
    document.getElementById('btn-signout')?.addEventListener('click', () => {
      if (confirm('Sign out and clear saved credentials?')) {
        clearConfig();
        location.reload();
      }
    });

    // Hash routing
    window.addEventListener('hashchange', () => {
      const page = this._getPageFromHash();
      if (page && page !== this.currentPage) this.navigate(page);
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        document.querySelectorAll('.modal-backdrop:not(.hidden)').forEach(m => m.classList.add('hidden'));
      }
    });
  }

  _getPageFromHash() {
    const hash = location.hash.slice(1);
    return PAGES[hash] ? hash : null;
  }

  /** Navigate to a page */
  async navigate(pageId) {
    if (!PAGES[pageId]) pageId = 'overview';

    this.currentPage = pageId;
    location.hash = pageId;

    // Update nav
    document.querySelectorAll('.nav-item').forEach(el => {
      el.classList.toggle('active', el.dataset.page === pageId);
    });

    // Update header page title
    const navItem = NAV.find(n => n.id === pageId);
    const titleEl = document.getElementById('page-title-text');
    if (titleEl && navItem) titleEl.textContent = `${navItem.icon} ${navItem.label}`;

    // Show loading state
    const content = document.getElementById('page-content');
    if (!content) return;
    content.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;min-height:200px;color:#475569">
        <div style="text-align:center">
          <div style="font-size:2rem;margin-bottom:8px">⏳</div>
          <p>Loading ${navItem?.label || 'page'}…</p>
        </div>
      </div>
    `;

    try {
      const mod = await PAGES[pageId]();
      _currentPage = mod;
      await mod.render(content);
    } catch (err) {
      // Use separate arguments instead of template literal to avoid tainted format string
      console.error('Failed to load admin page:', pageId, err);
      // Escape the error message before injecting into DOM to prevent XSS
      const safeMsg = String(err.message || 'Unknown error')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .slice(0, 200);
      content.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">⚠️</div>
          <div class="empty-title">Failed to load page</div>
          <div class="empty-desc">${safeMsg}</div>
        </div>
      `;
      notify.error('Page failed to load', safeMsg);
    }
  }
}

// ── Bootstrap ──────────────────────────────────────────────────────────────
const app = new AdminApp();
window.adminApp = app;

// Start when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => app.init());
} else {
  app.init();
}
