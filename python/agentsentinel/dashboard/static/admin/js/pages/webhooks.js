/**
 * Admin — Webhooks & Events page
 */
import { webhookAPI } from '../api.js';
import { fmt } from '../utils/format.js';
import { notify } from '../components/notifications.js';

let _events = [];
let _filters = { search: '', status: '', type: '' };

export async function render(container) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">🔗 Webhooks & Events</h1>
        <p class="page-subtitle">Monitor Stripe webhook event log</p>
      </div>
      <button class="btn btn-ghost btn-sm" id="wh-refresh">🔄 Refresh</button>
    </div>

    <!-- KPIs -->
    <div class="kpi-grid" style="grid-template-columns:repeat(4,1fr);margin-bottom:20px">
      <div class="kpi-card" style="--kpi-color:#0ea5e9"><div class="kpi-icon">🔗</div><div class="kpi-label">Total Events</div><div class="kpi-value" id="wh-total">—</div></div>
      <div class="kpi-card" style="--kpi-color:#10b981"><div class="kpi-icon">✅</div><div class="kpi-label">Processed</div><div class="kpi-value" id="wh-processed">—</div></div>
      <div class="kpi-card" style="--kpi-color:#ef4444"><div class="kpi-icon">❌</div><div class="kpi-label">Failed</div><div class="kpi-value" id="wh-failed">—</div></div>
      <div class="kpi-card" style="--kpi-color:#f59e0b"><div class="kpi-icon">⏳</div><div class="kpi-label">Pending</div><div class="kpi-value" id="wh-pending">—</div></div>
    </div>

    <!-- Toolbar -->
    <div class="table-toolbar">
      <div class="search-box">
        <svg class="search-icon" width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="6" cy="6" r="4" stroke="currentColor" stroke-width="1.5"/><path d="M10 10l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
        <input id="wh-search" type="text" placeholder="Search event ID…">
      </div>
      <div class="filter-row">
        <select class="filter-select" id="wh-filter-status">
          <option value="">All Status</option>
          <option value="processed">Processed</option>
          <option value="pending">Pending</option>
          <option value="failed">Failed</option>
        </select>
      </div>
    </div>

    <!-- Table -->
    <div class="card" style="padding:0;overflow:hidden">
      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Stripe Event ID</th>
              <th>Event Type</th>
              <th>Status</th>
              <th>Error</th>
              <th>Created</th>
              <th>Processed At</th>
              <th style="width:80px">Actions</th>
            </tr>
          </thead>
          <tbody id="wh-table-body">
            <tr><td colspan="7" style="text-align:center;padding:32px;color:#475569">Loading…</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Payload Modal -->
    <div id="modal-wh-payload" class="modal-backdrop hidden">
      <div class="modal-box modal-lg" role="dialog" aria-modal="true">
        <div class="modal-header">
          <h2 class="modal-title">Event Payload</h2>
          <button class="btn btn-ghost btn-sm" onclick="window._adminModals.close('wh-payload')">✕</button>
        </div>
        <div class="modal-body">
          <pre class="json-viewer" id="wh-payload-content"></pre>
        </div>
      </div>
    </div>
  `;

  container.querySelector('#wh-refresh').addEventListener('click', loadEvents);
  container.querySelector('#wh-search').addEventListener('input', (e) => {
    _filters.search = e.target.value;
    renderTable();
  });
  container.querySelector('#wh-filter-status').addEventListener('change', (e) => {
    _filters.status = e.target.value;
    loadEvents();
  });

  await loadEvents();
}

async function loadEvents() {
  try {
    _events = await webhookAPI.list({ status: _filters.status, pageSize: 200 });
    renderKpis();
    renderTable();
  } catch (err) {
    notify.error('Failed to load events', err.message);
  }
}

function renderKpis() {
  const processed = _events.filter(e => e.status === 'processed').length;
  const failed    = _events.filter(e => e.status === 'failed').length;
  const pending   = _events.filter(e => e.status === 'pending').length;
  document.getElementById('wh-total').textContent     = fmt.number(_events.length);
  document.getElementById('wh-processed').textContent = fmt.number(processed);
  document.getElementById('wh-failed').textContent    = fmt.number(failed);
  document.getElementById('wh-pending').textContent   = fmt.number(pending);
}

function renderTable() {
  const tbody = document.getElementById('wh-table-body');
  if (!tbody) return;
  let rows = _events;
  const q = _filters.search.toLowerCase().trim();
  if (q) rows = rows.filter(e => (e.stripe_event_id||'').toLowerCase().includes(q) || (e.event_type||'').toLowerCase().includes(q));
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:32px;color:#475569">No events found</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(e => `
    <tr>
      <td><code class="key-pill" style="font-size:.7rem">${(e.stripe_event_id||'').slice(0,24)}…</code></td>
      <td style="font-size:.78rem;color:#94a3b8">${e.event_type || '—'}</td>
      <td>
        ${e.status === 'processed'
          ? '<span class="badge badge-success">Processed</span>'
          : e.status === 'failed'
          ? '<span class="badge badge-danger">Failed</span>'
          : '<span class="badge badge-warning">Pending</span>'
        }
      </td>
      <td style="max-width:160px;font-size:.75rem;color:#f87171" class="truncate">${e.error_message || '<span class="text-muted">—</span>'}</td>
      <td>${fmt.datetime(e.created_at)}</td>
      <td>${e.processed_at ? fmt.datetime(e.processed_at) : '<span class="text-muted">—</span>'}</td>
      <td>
        <button class="btn btn-ghost btn-xs" onclick="window._whPayload('${e.id}')" title="View payload">📄</button>
      </td>
    </tr>
  `).join('');
}

window._whPayload = function(id) {
  const event = _events.find(e => e.id === id);
  if (!event) return;
  document.getElementById('wh-payload-content').textContent = JSON.stringify(event.payload, null, 2);
  document.getElementById('modal-wh-payload').classList.remove('hidden');
};
