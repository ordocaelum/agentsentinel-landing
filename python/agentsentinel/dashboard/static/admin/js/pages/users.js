/**
 * Admin — Users page
 */
import { customerAPI } from '../api.js';
import { fmt } from '../utils/format.js';
import { notify } from '../components/notifications.js';

let _customers = [];
let _filters = { search: '' };

export async function render(container) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">👥 Users</h1>
        <p class="page-subtitle">Manage customers and view profiles</p>
      </div>
      <button class="btn btn-ghost btn-sm" id="users-export">↓ Export CSV</button>
    </div>

    <!-- KPIs -->
    <div class="kpi-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:20px">
      <div class="kpi-card" style="--kpi-color:#0ea5e9">
        <div class="kpi-icon">👥</div>
        <div class="kpi-label">Total Customers</div>
        <div class="kpi-value" id="users-total">—</div>
      </div>
      <div class="kpi-card" style="--kpi-color:#10b981">
        <div class="kpi-icon">📅</div>
        <div class="kpi-label">This Week</div>
        <div class="kpi-value" id="users-week">—</div>
        <div class="kpi-sub">new signups</div>
      </div>
      <div class="kpi-card" style="--kpi-color:#8b5cf6">
        <div class="kpi-icon">📆</div>
        <div class="kpi-label">This Month</div>
        <div class="kpi-value" id="users-month">—</div>
        <div class="kpi-sub">new signups</div>
      </div>
    </div>

    <!-- Toolbar -->
    <div class="table-toolbar">
      <div class="search-box">
        <svg class="search-icon" width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="6" cy="6" r="4" stroke="currentColor" stroke-width="1.5"/><path d="M10 10l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
        <input id="users-search" type="text" placeholder="Search by email…">
      </div>
      <button class="btn btn-ghost btn-sm" id="users-refresh">🔄 Refresh</button>
    </div>

    <!-- Table -->
    <div class="card" style="padding:0;overflow:hidden">
      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Email</th>
              <th>Name</th>
              <th>Stripe ID</th>
              <th>Joined</th>
              <th>Updated</th>
              <th style="width:80px">Actions</th>
            </tr>
          </thead>
          <tbody id="users-table-body">
            <tr><td colspan="6" style="text-align:center;padding:32px;color:#475569">Loading…</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Detail Modal -->
    <div id="modal-user-detail" class="modal-backdrop hidden">
      <div class="modal-box modal-lg" role="dialog" aria-modal="true">
        <div class="modal-header">
          <h2 class="modal-title">Customer Profile</h2>
          <button class="btn btn-ghost btn-sm" onclick="window._adminModals.close('user-detail')">✕</button>
        </div>
        <div class="modal-body" id="user-detail-body"></div>
        <div class="modal-footer">
          <button class="btn btn-ghost" onclick="window._adminModals.close('user-detail')">Close</button>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#users-search').addEventListener('input', (e) => {
    _filters.search = e.target.value;
    renderTable();
  });
  container.querySelector('#users-refresh').addEventListener('click', loadUsers);
  container.querySelector('#users-export').addEventListener('click', exportCSV);

  await loadUsers();
}

async function loadUsers() {
  try {
    _customers = await customerAPI.list({ pageSize: 200 });
    renderKpis();
    renderTable();
  } catch (err) {
    notify.error('Failed to load users', err.message);
  }
}

function renderKpis() {
  const now   = Date.now();
  const week  = 7 * 86_400_000;
  const month = 30 * 86_400_000;
  document.getElementById('users-total').textContent = fmt.number(_customers.length);
  document.getElementById('users-week').textContent  = _customers.filter(c => now - new Date(c.created_at) < week).length;
  document.getElementById('users-month').textContent = _customers.filter(c => now - new Date(c.created_at) < month).length;
}

function renderTable() {
  const tbody = document.getElementById('users-table-body');
  if (!tbody) return;
  let rows = _customers;
  const q = _filters.search.toLowerCase().trim();
  if (q) rows = rows.filter(c => (c.email||'').toLowerCase().includes(q) || (c.name||'').toLowerCase().includes(q));
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:32px;color:#475569">No customers found</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(c => `
    <tr>
      <td style="font-weight:500">${c.email || '—'}</td>
      <td>${c.name || '<span class="text-muted">—</span>'}</td>
      <td>${c.stripe_customer_id ? `<code class="key-pill">${c.stripe_customer_id.slice(0,20)}</code>` : '<span class="text-muted">—</span>'}</td>
      <td>${fmt.date(c.created_at)}</td>
      <td>${fmt.relative(c.updated_at)}</td>
      <td>
        <button class="btn btn-ghost btn-xs" onclick="window._userDetail('${c.id}')" title="View profile">🔍</button>
      </td>
    </tr>
  `).join('');
}

function exportCSV() {
  if (!_customers.length) { notify.warning('No data to export'); return; }
  const cols = ['id','email','name','stripe_customer_id','created_at','updated_at'];
  const header = cols.join(',');
  const rows = _customers.map(c => cols.map(k => `"${(c[k]||'').toString().replace(/"/g,'""')}"`).join(','));
  const csv = [header, ...rows].join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = `customers-${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  notify.success('CSV downloaded');
}

window._userDetail = async function(id) {
  const body = document.getElementById('user-detail-body');
  body.innerHTML = '<p style="color:#64748b">Loading…</p>';
  document.getElementById('modal-user-detail').classList.remove('hidden');
  try {
    const { customer, licenses } = await customerAPI.getWithLicenses(id);
    if (!customer) { body.innerHTML = '<p style="color:#ef4444">Customer not found</p>'; return; }
    body.innerHTML = `
      <div class="form-grid" style="margin-bottom:20px">
        <div class="form-group">
          <label class="form-label">Email</label>
          <span style="font-weight:600">${customer.email || '—'}</span>
        </div>
        <div class="form-group">
          <label class="form-label">Name</label>
          <span>${customer.name || '—'}</span>
        </div>
        <div class="form-group">
          <label class="form-label">Customer ID</label>
          <code class="key-pill">${customer.id.slice(0,12)}…</code>
        </div>
        <div class="form-group">
          <label class="form-label">Stripe ID</label>
          ${customer.stripe_customer_id ? `<code class="key-pill">${customer.stripe_customer_id}</code>` : '<span class="text-muted">—</span>'}
        </div>
        <div class="form-group">
          <label class="form-label">Joined</label>
          <span>${fmt.datetime(customer.created_at)}</span>
        </div>
      </div>
      <div class="divider"></div>
      <p class="card-title" style="margin-bottom:10px">Licenses (${licenses.length})</p>
      ${licenses.length ? `
        <div class="data-table-wrap">
          <table class="data-table">
            <thead><tr><th>Key</th><th>Tier</th><th>Status</th><th>Created</th></tr></thead>
            <tbody>
              ${licenses.map(l => `
                <tr>
                  <td><code class="key-pill">${fmt.mask(l.license_key, 8, 4)}</code></td>
                  <td><span class="badge ${fmt.tierBadge(l.tier)}">${(l.tier||'').toUpperCase()}</span></td>
                  <td><span class="badge ${fmt.statusBadge(l.status)}">${(l.status||'').toUpperCase()}</span></td>
                  <td>${fmt.date(l.created_at)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      ` : '<p style="color:#64748b">No licenses</p>'}
    `;
  } catch (err) {
    body.innerHTML = `<p style="color:#ef4444">Error: ${err.message}</p>`;
  }
};
