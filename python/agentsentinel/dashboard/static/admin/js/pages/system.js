/**
 * Admin — System & Settings page
 */
import { getConfig, saveConfig, clearConfig } from '../utils/auth.js';
import { notify } from '../components/notifications.js';

export async function render(container) {
  const cfg = getConfig();
  container.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">⚙️ System & Settings</h1>
        <p class="page-subtitle">Admin configuration and environment status</p>
      </div>
    </div>

    <!-- Connection settings -->
    <div class="card mb-4">
      <div class="card-header">
        <span class="card-title">🔗 Supabase Connection</span>
        <span id="conn-status" class="badge badge-muted">Checking…</span>
      </div>
      <div class="form-grid">
        <div class="form-group">
          <label class="form-label">Supabase Project URL</label>
          <input class="form-control" id="s-url" type="url" placeholder="https://xxxx.supabase.co" value="${escHtml(cfg.supabaseUrl||'')}">
        </div>
        <div class="form-group">
          <label class="form-label">Service Role Key (secret)</label>
          <div style="position:relative">
            <input class="form-control font-mono" id="s-key" type="password" placeholder="eyJh…" value="${escHtml(cfg.supabaseKey||'')}">
            <button class="btn btn-ghost btn-xs" style="position:absolute;right:6px;top:50%;transform:translateY(-50%)" id="toggle-key-vis" title="Show/hide key">👁</button>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">Admin API Secret</label>
          <div style="position:relative">
            <input class="form-control font-mono" id="s-admin-secret" type="password" placeholder="your-admin-api-secret" value="${escHtml(cfg.adminApiSecret||'')}">
            <button class="btn btn-ghost btn-xs" style="position:absolute;right:6px;top:50%;transform:translateY(-50%)" id="toggle-secret-vis" title="Show/hide secret">👁</button>
          </div>
          <span class="form-hint">Used to call admin-generate-promo Edge Function</span>
        </div>
        <div class="form-group" style="display:flex;align-items:flex-end">
          <button class="btn btn-primary" id="save-conn" style="width:100%">💾 Save & Test Connection</button>
        </div>
      </div>
    </div>

    <!-- Database Status -->
    <div class="card mb-4">
      <div class="card-header">
        <span class="card-title">🗄️ Database Tables</span>
        <button class="btn btn-ghost btn-sm" id="check-tables">🔍 Check Status</button>
      </div>
      <div id="table-status-list" style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px">
        ${['customers','licenses','promo_codes','webhook_events','admin_logs','dashboard_metrics'].map(t => `
          <div class="sys-status-card">
            <span class="status-dot gray" id="tbl-dot-${t}"></span>
            <span class="sys-status-label font-mono">${t}</span>
            <span class="sys-status-value" id="tbl-val-${t}">—</span>
          </div>
        `).join('')}
      </div>
    </div>

    <!-- Admin Actions -->
    <div class="card mb-4">
      <div class="card-header"><span class="card-title">🔧 Admin Actions</span></div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="btn btn-warning" id="btn-clear-config">🗑 Clear Saved Config</button>
        <button class="btn btn-ghost" id="btn-copy-config">📋 Copy Config (JSON)</button>
      </div>
    </div>

    <!-- Documentation -->
    <div class="card">
      <div class="card-header"><span class="card-title">📚 Quick Reference</span></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;font-size:.82rem;color:#94a3b8">
        <div>
          <p class="form-label mb-4" style="margin-bottom:6px">Edge Functions</p>
          <ul style="list-style:none;display:flex;flex-direction:column;gap:4px">
            <li><code class="key-pill">POST /functions/v1/admin-generate-promo</code></li>
            <li><code class="key-pill">POST /functions/v1/validate-promo</code></li>
            <li><code class="key-pill">POST /functions/v1/validate-license</code></li>
            <li><code class="key-pill">POST /functions/v1/stripe-webhook</code></li>
          </ul>
        </div>
        <div>
          <p class="form-label" style="margin-bottom:6px">Supabase Tables</p>
          <ul style="list-style:none;display:flex;flex-direction:column;gap:4px">
            <li><code class="key-pill">customers</code> — customer records</li>
            <li><code class="key-pill">licenses</code> — license keys + tiers</li>
            <li><code class="key-pill">promo_codes</code> — promotional codes</li>
            <li><code class="key-pill">webhook_events</code> — Stripe events</li>
            <li><code class="key-pill">admin_logs</code> — audit trail</li>
          </ul>
        </div>
      </div>
    </div>
  `;

  // Save connection
  container.querySelector('#save-conn').addEventListener('click', saveConnection);
  container.querySelector('#check-tables').addEventListener('click', checkTables);
  container.querySelector('#btn-clear-config').addEventListener('click', () => {
    clearConfig();
    notify.success('Config cleared', 'Reload the page to reconfigure');
  });
  container.querySelector('#btn-copy-config').addEventListener('click', () => {
    navigator.clipboard?.writeText(JSON.stringify(getConfig(), null, 2));
    notify.info('Copied to clipboard');
  });
  container.querySelector('#toggle-key-vis').addEventListener('click', () => {
    const inp = document.getElementById('s-key');
    inp.type = inp.type === 'password' ? 'text' : 'password';
  });
  container.querySelector('#toggle-secret-vis').addEventListener('click', () => {
    const inp = document.getElementById('s-admin-secret');
    inp.type = inp.type === 'password' ? 'text' : 'password';
  });

  // Auto-check connection
  checkConnection();
}

async function saveConnection() {
  const url    = document.getElementById('s-url').value.trim().replace(/\/+$/, '');
  const key    = document.getElementById('s-key').value.trim();
  const secret = document.getElementById('s-admin-secret').value.trim();

  if (!url || !key) { notify.error('URL and key are required'); return; }

  saveConfig({ supabaseUrl: url, supabaseKey: key, adminApiSecret: secret || null });
  notify.info('Saved — testing connection…');
  await checkConnection();
}

async function checkConnection() {
  const statusEl = document.getElementById('conn-status');
  const { supabaseUrl, supabaseKey } = getConfig();
  if (!supabaseUrl || !supabaseKey) {
    if (statusEl) { statusEl.textContent = 'Not configured'; statusEl.className = 'badge badge-muted'; }
    return;
  }
  try {
    const { verifyAdminAccess } = await import('../utils/auth.js');
    const ok = await verifyAdminAccess(supabaseUrl, supabaseKey);
    if (statusEl) {
      statusEl.textContent = ok ? '✓ Connected' : '✗ Access Denied';
      statusEl.className = ok ? 'badge badge-success' : 'badge badge-danger';
    }
    if (ok) notify.success('Connected to Supabase');
    else notify.error('Access denied', 'Check your service role key');
  } catch (err) {
    if (statusEl) { statusEl.textContent = '✗ Error'; statusEl.className = 'badge badge-danger'; }
    notify.error('Connection failed', err.message);
  }
}

async function checkTables() {
  const { supabaseUrl, supabaseKey } = getConfig();
  if (!supabaseUrl || !supabaseKey) { notify.warning('Configure connection first'); return; }
  const tables = ['customers','licenses','promo_codes','webhook_events','admin_logs','dashboard_metrics'];
  await Promise.all(tables.map(async (table) => {
    const dot = document.getElementById(`tbl-dot-${table}`);
    const val = document.getElementById(`tbl-val-${table}`);
    try {
      const res = await fetch(`${supabaseUrl}/rest/v1/${table}?limit=1&select=id`, {
        headers: { apikey: supabaseKey, Authorization: `Bearer ${supabaseKey}` },
      });
      const ok = res.ok;
      if (dot) dot.className = `status-dot ${ok ? 'green' : 'yellow'}`;
      if (val) val.textContent = ok ? '✓ accessible' : `HTTP ${res.status}`;
    } catch {
      if (dot) dot.className = 'status-dot red';
      if (val) val.textContent = '✗ error';
    }
  }));
  notify.success('Table check complete');
}

function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
