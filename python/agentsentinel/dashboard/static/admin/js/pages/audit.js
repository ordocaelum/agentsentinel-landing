/**
 * Admin — Audit Log page
 */
import { auditAPI } from '../api.js';
import { fmt } from '../utils/format.js';
import { notify } from '../components/notifications.js';

let _logs = [];
let _filters = { adminId: '', action: '', entityType: '' };

export async function render(container) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">📋 Audit Log</h1>
        <p class="page-subtitle">Immutable record of all admin actions</p>
      </div>
      <button class="btn btn-ghost btn-sm" id="audit-refresh">🔄 Refresh</button>
    </div>

    <!-- Toolbar -->
    <div class="table-toolbar">
      <div class="search-box">
        <svg class="search-icon" width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="6" cy="6" r="4" stroke="currentColor" stroke-width="1.5"/><path d="M10 10l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
        <input id="audit-search" type="text" placeholder="Filter by admin…">
      </div>
      <div class="filter-row">
        <select class="filter-select" id="audit-filter-action">
          <option value="">All Actions</option>
          <option value="created">Created</option>
          <option value="updated">Updated</option>
          <option value="deleted">Deleted</option>
          <option value="activated">Activated</option>
          <option value="deactivated">Deactivated</option>
          <option value="revoked">Revoked</option>
        </select>
        <select class="filter-select" id="audit-filter-entity">
          <option value="">All Entities</option>
          <option value="promo">Promo Code</option>
          <option value="license">License</option>
          <option value="user">User</option>
          <option value="system">System</option>
        </select>
      </div>
    </div>

    <!-- Table -->
    <div class="card" style="padding:0;overflow:hidden">
      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Admin</th>
              <th>Action</th>
              <th>Entity Type</th>
              <th>Entity ID</th>
              <th>Status</th>
              <th style="width:80px">Details</th>
            </tr>
          </thead>
          <tbody id="audit-table-body">
            <tr><td colspan="7" style="text-align:center;padding:32px;color:#475569">Loading…</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Detail Modal -->
    <div id="modal-audit-detail" class="modal-backdrop hidden">
      <div class="modal-box" role="dialog" aria-modal="true">
        <div class="modal-header">
          <h2 class="modal-title">Audit Entry Details</h2>
          <button class="btn btn-ghost btn-sm" onclick="window._adminModals.close('audit-detail')">✕</button>
        </div>
        <div class="modal-body" id="audit-detail-body"></div>
      </div>
    </div>
  `;

  container.querySelector('#audit-refresh').addEventListener('click', loadLogs);
  container.querySelector('#audit-search').addEventListener('input', (e) => {
    _filters.adminId = e.target.value;
    renderTable();
  });
  container.querySelector('#audit-filter-action').addEventListener('change', (e) => {
    _filters.action = e.target.value;
    loadLogs();
  });
  container.querySelector('#audit-filter-entity').addEventListener('change', (e) => {
    _filters.entityType = e.target.value;
    loadLogs();
  });

  await loadLogs();
}

async function loadLogs() {
  try {
    _logs = await auditAPI.list({
      action:     _filters.action,
      entityType: _filters.entityType,
      pageSize:   200,
    });
    renderTable();
  } catch (err) {
    // Gracefully handle case where admin_logs table doesn't exist yet
    const tbody = document.getElementById('audit-table-body');
    if (err.message.includes('42P01') || err.message.includes('does not exist') || err.message.includes('404')) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:32px;color:#f59e0b">
        ⚠️ The <code>admin_logs</code> table doesn't exist yet.<br>
        <span style="font-size:.8rem">Run migration <code>011_admin_tables.sql</code> in your Supabase project first.</span>
      </td></tr>`;
    } else {
      notify.error('Failed to load audit log', err.message);
      if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:#ef4444;padding:24px">Error: ${err.message}</td></tr>`;
    }
  }
}

function renderTable() {
  const tbody = document.getElementById('audit-table-body');
  if (!tbody) return;
  let rows = _logs;
  const q = _filters.adminId.toLowerCase().trim();
  if (q) rows = rows.filter(l => (l.admin_id||'').toLowerCase().includes(q));
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:32px;color:#475569">No audit entries found</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(l => `
    <tr>
      <td style="white-space:nowrap;font-size:.78rem">${fmt.datetime(l.created_at)}</td>
      <td style="max-width:140px" class="truncate">${l.admin_id || '—'}</td>
      <td>
        <span class="badge ${actionBadge(l.action)}">${l.action || '—'}</span>
      </td>
      <td style="color:#94a3b8">${l.entity_type || '—'}</td>
      <td style="font-size:.73rem;color:#64748b">${l.entity_id ? l.entity_id.slice(0,12) + '…' : '—'}</td>
      <td>
        <span class="badge ${l.status === 'success' ? 'badge-success' : 'badge-danger'}">${l.status || 'success'}</span>
      </td>
      <td>
        ${(l.old_values || l.new_values) ? `<button class="btn btn-ghost btn-xs" onclick="window._auditDetail('${l.id}')">👁</button>` : '—'}
      </td>
    </tr>
  `).join('');
}

function actionBadge(action) {
  const map = {
    created:     'badge-success',
    updated:     'badge-info',
    deleted:     'badge-danger',
    activated:   'badge-success',
    deactivated: 'badge-warning',
    revoked:     'badge-danger',
  };
  return map[action] || 'badge-muted';
}

window._auditDetail = function(id) {
  const log = _logs.find(l => l.id === id);
  if (!log) return;
  const body = document.getElementById('audit-detail-body');
  if (body) {
    body.innerHTML = `
      <div class="form-grid" style="margin-bottom:16px">
        <div class="form-group"><label class="form-label">Timestamp</label><span>${fmt.datetime(log.created_at)}</span></div>
        <div class="form-group"><label class="form-label">Admin</label><span>${log.admin_id || '—'}</span></div>
        <div class="form-group"><label class="form-label">Action</label><span class="badge ${actionBadge(log.action)}">${log.action}</span></div>
        <div class="form-group"><label class="form-label">Entity</label><span>${log.entity_type} / ${log.entity_id || '—'}</span></div>
      </div>
      ${log.old_values ? `
        <p class="form-label" style="margin-bottom:6px">Before</p>
        <pre class="json-viewer">${JSON.stringify(log.old_values, null, 2)}</pre>
      ` : ''}
      ${log.new_values ? `
        <p class="form-label" style="margin-top:12px;margin-bottom:6px">After</p>
        <pre class="json-viewer">${JSON.stringify(log.new_values, null, 2)}</pre>
      ` : ''}
      ${log.error_message ? `<p style="color:#f87171;margin-top:12px;font-size:.8rem">Error: ${log.error_message}</p>` : ''}
    `;
  }
  document.getElementById('modal-audit-detail').classList.remove('hidden');
};
