/**
 * Admin — Licenses page
 */
import { licenseAPI, auditAPI } from '../api.js';
import { fmt } from '../utils/format.js';
import { notify } from '../components/notifications.js';
import { confirm } from '../components/modal.js';

let _licenses = [];
let _filters = { search: '', status: '', tier: '' };

export async function render(container) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">🎫 Licenses</h1>
        <p class="page-subtitle">Manage all customer licenses</p>
      </div>
      <button class="btn btn-primary" id="btn-export-licenses">↓ Export CSV</button>
    </div>

    <!-- KPIs -->
    <div class="kpi-grid" id="license-kpis" style="grid-template-columns:repeat(5,1fr);margin-bottom:20px">
      ${[...Array(5)].map(() => `<div class="kpi-card skeleton" style="height:80px"></div>`).join('')}
    </div>

    <!-- Toolbar -->
    <div class="table-toolbar">
      <div class="search-box">
        <svg class="search-icon" width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="6" cy="6" r="4" stroke="currentColor" stroke-width="1.5"/><path d="M10 10l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
        <input id="lic-search" type="text" placeholder="Search key or email…">
      </div>
      <div class="filter-row">
        <select class="filter-select" id="lic-filter-status">
          <option value="">All Status</option>
          <option value="active">Active</option>
          <option value="revoked">Revoked</option>
          <option value="expired">Expired</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <select class="filter-select" id="lic-filter-tier">
          <option value="">All Tiers</option>
          <option value="free">Free</option>
          <option value="pro">Pro</option>
          <option value="team">Team</option>
          <option value="enterprise">Enterprise</option>
        </select>
        <button class="btn btn-ghost btn-sm" id="lic-refresh">🔄 Refresh</button>
      </div>
    </div>

    <!-- Table -->
    <div class="card" style="padding:0;overflow:hidden">
      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>License Key</th>
              <th>Customer</th>
              <th>Tier</th>
              <th>Status</th>
              <th>Agents</th>
              <th>Events</th>
              <th>Created</th>
              <th>Expires</th>
              <th style="width:120px">Actions</th>
            </tr>
          </thead>
          <tbody id="lic-table-body">
            <tr><td colspan="9" style="text-align:center;padding:32px;color:#475569">Loading…</td></tr>
          </tbody>
        </table>
      </div>
      <div id="lic-pagination" style="padding:12px 16px;border-top:1px solid rgba(148,163,184,.1);display:flex;align-items:center;justify-content:space-between">
        <span id="lic-count" class="text-xs text-muted"></span>
      </div>
    </div>

    <!-- Detail Modal -->
    <div id="modal-lic-detail" class="modal-backdrop hidden">
      <div class="modal-box modal-lg" role="dialog" aria-modal="true">
        <div class="modal-header">
          <h2 class="modal-title">License Details</h2>
          <button class="btn btn-ghost btn-sm" onclick="window._adminModals.close('lic-detail')">✕</button>
        </div>
        <div class="modal-body" id="lic-detail-body"></div>
        <div class="modal-footer">
          <button class="btn btn-ghost" onclick="window._adminModals.close('lic-detail')">Close</button>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#lic-search').addEventListener('input', (e) => {
    _filters.search = e.target.value;
    renderTable();
  });
  container.querySelector('#lic-filter-status').addEventListener('change', (e) => {
    _filters.status = e.target.value;
    loadLicenses();
  });
  container.querySelector('#lic-filter-tier').addEventListener('change', (e) => {
    _filters.tier = e.target.value;
    loadLicenses();
  });
  container.querySelector('#lic-refresh').addEventListener('click', loadLicenses);
  container.querySelector('#btn-export-licenses').addEventListener('click', exportCSV);

  await loadLicenses();
}

async function loadLicenses() {
  try {
    _licenses = await licenseAPI.list({
      status: _filters.status,
      tier:   _filters.tier,
    });
    renderKpis();
    renderTable();
  } catch (err) {
    notify.error('Failed to load licenses', err.message);
  }
}

function renderKpis() {
  const total  = _licenses.length;
  const active = _licenses.filter(l => l.status === 'active').length;
  const pro    = _licenses.filter(l => l.tier === 'pro').length;
  const team   = _licenses.filter(l => l.tier === 'team').length;
  const revoked= _licenses.filter(l => l.status === 'revoked').length;

  const kpis = [
    { label: 'Total',    value: total,   icon: '📋', color: '#0ea5e9' },
    { label: 'Active',   value: active,  icon: '✅', color: '#10b981' },
    { label: 'Pro',      value: pro,     icon: '⭐', color: '#6366f1' },
    { label: 'Team',     value: team,    icon: '👥', color: '#8b5cf6' },
    { label: 'Revoked',  value: revoked, icon: '🚫', color: '#ef4444' },
  ];
  const el = document.getElementById('license-kpis');
  if (el) el.innerHTML = kpis.map(k => `
    <div class="kpi-card" style="--kpi-color:${k.color}">
      <div class="kpi-icon">${k.icon}</div>
      <div class="kpi-label">${k.label}</div>
      <div class="kpi-value">${k.value}</div>
    </div>
  `).join('');
}

function renderTable() {
  const tbody = document.getElementById('lic-table-body');
  if (!tbody) return;

  let rows = _licenses;
  const q = _filters.search.toLowerCase().trim();
  if (q) rows = rows.filter(l =>
    (l.license_key || '').toLowerCase().includes(q) ||
    (l.customers?.email || '').toLowerCase().includes(q)
  );

  const countEl = document.getElementById('lic-count');
  if (countEl) countEl.textContent = `Showing ${rows.length} of ${_licenses.length} licenses`;

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-state" style="padding:32px;text-align:center;color:#475569">No licenses found</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(l => {
    const email = l.customers?.email || '—';
    const isExpired = fmt.isExpired(l.expires_at);
    const effectiveStatus = isExpired && l.status === 'active' ? 'expired' : l.status;
    return `
      <tr>
        <td>
          <div style="display:flex;align-items:center;gap:6px">
            <code class="key-pill" id="key-${l.id}" title="${l.license_key}">${fmt.mask(l.license_key, 10, 4)}</code>
            <button class="btn btn-ghost btn-xs" onclick="window._licReveal('${l.id}','${l.license_key}')" title="Reveal key">👁</button>
          </div>
        </td>
        <td style="max-width:160px" class="truncate" title="${email}">${email}</td>
        <td><span class="badge ${fmt.tierBadge(l.tier)}">${(l.tier||'').toUpperCase()}</span></td>
        <td><span class="badge ${fmt.statusBadge(effectiveStatus)}">${effectiveStatus.toUpperCase()}</span></td>
        <td class="tabular-nums">${fmt.number(l.agents_limit)}</td>
        <td class="tabular-nums">${fmt.number(l.events_limit)}</td>
        <td>${fmt.date(l.created_at)}</td>
        <td>${l.expires_at ? fmt.date(l.expires_at) : '<span class="text-muted">Never</span>'}</td>
        <td>
          <div style="display:flex;gap:4px">
            <button class="btn btn-ghost btn-xs" onclick="window._licDetail('${l.id}')" title="View details">🔍</button>
            ${l.status === 'active'
              ? `<button class="btn btn-ghost btn-xs" style="color:#fbbf24" onclick="window._licRevoke('${l.id}')" title="Revoke">🚫</button>`
              : `<button class="btn btn-ghost btn-xs" style="color:#34d399" onclick="window._licActivate('${l.id}')" title="Activate">✅</button>`
            }
            <button class="btn btn-ghost btn-xs" style="color:#f87171" onclick="window._licDelete('${l.id}')" title="Delete">🗑</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function exportCSV() {
  if (!_licenses.length) { notify.warning('No data to export'); return; }
  const cols = ['id','license_key','tier','status','agents_limit','events_limit','created_at','expires_at'];
  const header = cols.join(',');
  const rows = _licenses.map(l => cols.map(c => `"${(l[c]||'').toString().replace(/"/g,'""')}"`).join(','));
  const csv = [header, ...rows].join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = `licenses-${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  notify.success('CSV downloaded');
}

window._licReveal = function(id, key) {
  const el = document.getElementById(`key-${id}`);
  if (el) {
    const showing = el.dataset.revealed === '1';
    el.textContent = showing ? fmt.mask(key, 10, 4) : key;
    el.dataset.revealed = showing ? '0' : '1';
  }
};

window._licDetail = function(id) {
  const l = _licenses.find(x => x.id === id);
  if (!l) return;
  const body = document.getElementById('lic-detail-body');
  if (body) {
    body.innerHTML = `
      <div class="form-grid">
        <div class="form-group">
          <label class="form-label">License Key</label>
          <code class="key-pill" style="font-size:.8rem">${l.license_key}</code>
        </div>
        <div class="form-group">
          <label class="form-label">Customer Email</label>
          <span>${l.customers?.email || '—'}</span>
        </div>
        <div class="form-group">
          <label class="form-label">Tier</label>
          <span class="badge ${fmt.tierBadge(l.tier)}">${(l.tier||'').toUpperCase()}</span>
        </div>
        <div class="form-group">
          <label class="form-label">Status</label>
          <span class="badge ${fmt.statusBadge(l.status)}">${(l.status||'').toUpperCase()}</span>
        </div>
        <div class="form-group">
          <label class="form-label">Agents Limit</label>
          <span>${fmt.number(l.agents_limit)}</span>
        </div>
        <div class="form-group">
          <label class="form-label">Events Limit</label>
          <span>${fmt.number(l.events_limit)}</span>
        </div>
        <div class="form-group">
          <label class="form-label">Created</label>
          <span>${fmt.datetime(l.created_at)}</span>
        </div>
        <div class="form-group">
          <label class="form-label">Expires</label>
          <span>${l.expires_at ? fmt.datetime(l.expires_at) : 'Never'}</span>
        </div>
        ${l.stripe_subscription_id ? `<div class="form-group col-span-2"><label class="form-label">Stripe Subscription</label><code class="key-pill">${l.stripe_subscription_id}</code></div>` : ''}
        ${l.promo_code_id ? `<div class="form-group"><label class="form-label">Promo Applied</label><span class="badge badge-info">${l.discount_type || 'promo'}</span></div>` : ''}
      </div>
    `;
  }
  document.getElementById('modal-lic-detail').classList.remove('hidden');
};

window._licRevoke = async function(id) {
  const ok = await confirm('Revoke License?', 'This will revoke the license. The customer will lose access.', 'Revoke', 'danger');
  if (!ok) return;
  try {
    await licenseAPI.revoke(id);
    await auditAPI.log({ action: 'revoked', entityType: 'license', entityId: id });
    notify.success('License revoked');
    const l = _licenses.find(x => x.id === id);
    if (l) l.status = 'revoked';
    renderTable();
  } catch (err) {
    notify.error('Revoke failed', err.message);
  }
};

window._licActivate = async function(id) {
  try {
    await licenseAPI.activate(id);
    await auditAPI.log({ action: 'activated', entityType: 'license', entityId: id });
    notify.success('License activated');
    const l = _licenses.find(x => x.id === id);
    if (l) l.status = 'active';
    renderTable();
  } catch (err) {
    notify.error('Activation failed', err.message);
  }
};

window._licDelete = async function(id) {
  const ok = await confirm('Delete License?', 'This will permanently delete the license. This cannot be undone.', 'Delete', 'danger');
  if (!ok) return;
  try {
    await licenseAPI.delete(id);
    await auditAPI.log({ action: 'deleted', entityType: 'license', entityId: id });
    notify.success('License deleted');
    _licenses = _licenses.filter(l => l.id !== id);
    renderTable();
    renderKpis();
  } catch (err) {
    notify.error('Delete failed', err.message);
  }
};
