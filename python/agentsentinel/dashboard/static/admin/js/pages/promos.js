/**
 * Admin — Promo Codes page (full CRUD)
 */
import { promoAPI } from '../api.js';
import { fmt } from '../utils/format.js';
import { notify } from '../components/notifications.js';
import { validate, setFieldError, clearFormErrors } from '../utils/validation.js';
import { confirm } from '../components/modal.js';
import { auditAPI } from '../api.js';

let _promos = [];
let _filters = { search: '', status: '', type: '' };

export async function render(container) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">🎟 Promo Codes</h1>
        <p class="page-subtitle">Create, edit, and manage promotional codes</p>
      </div>
      <button class="btn btn-primary" id="btn-create-promo">+ Create Promo</button>
    </div>

    <!-- Analytics strip -->
    <div class="kpi-grid" style="grid-template-columns:repeat(4,1fr)" id="promo-kpis">
      ${['Total Promos','Active','Total Uses','Templates'].map(l => `<div class="kpi-card skeleton" style="height:70px"></div>`).join('')}
    </div>

    <!-- Toolbar -->
    <div class="table-toolbar">
      <div class="search-box">
        <svg class="search-icon" width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="6" cy="6" r="4" stroke="currentColor" stroke-width="1.5"/><path d="M10 10l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
        <input id="promo-search" type="text" placeholder="Search code…" value="">
      </div>
      <div class="filter-row">
        <select class="filter-select" id="promo-filter-status">
          <option value="">All Status</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
        <select class="filter-select" id="promo-filter-type">
          <option value="">All Types</option>
          <option value="discount_percent">Discount %</option>
          <option value="discount_fixed">Discount $</option>
          <option value="trial_extension">Trial Days</option>
          <option value="unlimited_trial">Unlimited Trial</option>
        </select>
      </div>
    </div>

    <!-- Table -->
    <div class="card" style="padding:0;overflow:hidden">
      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Type</th>
              <th>Value</th>
              <th>Tier</th>
              <th>Active</th>
              <th>Uses</th>
              <th>Max Uses</th>
              <th>Expires</th>
              <th style="width:120px">Actions</th>
            </tr>
          </thead>
          <tbody id="promo-table-body">
            <tr><td colspan="9" style="text-align:center;padding:32px;color:#475569">Loading…</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Templates panel -->
    <div class="card mt-4">
      <div class="card-header">
        <span class="card-title">⚡ Quick Templates</span>
        <span class="text-xs text-muted">Click to pre-fill the create form</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px" id="promo-templates"></div>
    </div>

    <!-- Create/Edit Modal -->
    <div id="modal-promo-form" class="modal-backdrop hidden">
      <div class="modal-box" role="dialog" aria-modal="true" aria-labelledby="promo-form-title">
        <div class="modal-header">
          <h2 class="modal-title" id="promo-form-title">Create Promo Code</h2>
          <button class="btn btn-ghost btn-sm" id="promo-form-close">✕</button>
        </div>
        <div class="modal-body">
          <form id="promo-form" novalidate>
            <input type="hidden" id="promo-edit-id" value="">
            <div class="form-grid">
              <div class="form-group">
                <label class="form-label" for="f-code">Code *</label>
                <input class="form-control font-mono" id="f-code" type="text" placeholder="LAUNCH20" maxlength="64" autocapitalize="characters" style="text-transform:uppercase">
                <span class="form-hint">Letters, numbers, dash, underscore only</span>
              </div>
              <div class="form-group">
                <label class="form-label" for="f-type">Type *</label>
                <select class="form-control" id="f-type">
                  <option value="">Select type…</option>
                  <option value="discount_percent">Discount % (e.g., 20% off)</option>
                  <option value="discount_fixed">Discount $ (fixed amount in cents)</option>
                  <option value="trial_extension">Trial Days (+14 extra days)</option>
                  <option value="unlimited_trial">Unlimited Trial (no expiry)</option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label" for="f-value">Value *</label>
                <input class="form-control" id="f-value" type="number" min="0" placeholder="0">
                <span class="form-hint" id="f-value-hint">Enter the discount value</span>
              </div>
              <div class="form-group">
                <label class="form-label" for="f-tier">Tier Filter</label>
                <select class="form-control" id="f-tier">
                  <option value="">All Tiers</option>
                  <option value="free">Free</option>
                  <option value="pro">Pro</option>
                  <option value="team">Team</option>
                  <option value="enterprise">Enterprise</option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label" for="f-max-uses">Max Uses</label>
                <input class="form-control" id="f-max-uses" type="number" min="0" placeholder="Leave blank = unlimited">
                <span class="form-hint">Leave blank for unlimited uses</span>
              </div>
              <div class="form-group">
                <label class="form-label" for="f-expires">Expires At</label>
                <input class="form-control" id="f-expires" type="datetime-local">
                <span class="form-hint">Leave blank = never expires</span>
              </div>
              <div class="form-group col-span-2">
                <label class="form-label" for="f-description">Description</label>
                <textarea class="form-control" id="f-description" rows="2" placeholder="Internal note about this promo code…"></textarea>
              </div>
              <div class="form-group">
                <label class="toggle-wrap">
                  <input type="checkbox" class="toggle-input" id="f-active" checked>
                  <span class="toggle-track"><span class="toggle-thumb"></span></span>
                  <span class="toggle-label">Active (usable immediately)</span>
                </label>
              </div>
            </div>
          </form>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" id="promo-form-cancel">Cancel</button>
          <button class="btn btn-primary" id="promo-form-submit">Create Promo</button>
        </div>
      </div>
    </div>

    <!-- Usage Detail Modal -->
    <div id="modal-promo-usage" class="modal-backdrop hidden">
      <div class="modal-box modal-lg" role="dialog" aria-modal="true">
        <div class="modal-header">
          <h2 class="modal-title">Usage Details — <span id="usage-code-label"></span></h2>
          <button class="btn btn-ghost btn-sm" onclick="window._adminModals.close('promo-usage')">✕</button>
        </div>
        <div class="modal-body" id="promo-usage-body">Loading…</div>
      </div>
    </div>
  `;

  // Wire up events
  container.querySelector('#btn-create-promo').addEventListener('click', () => openCreateForm());
  container.querySelector('#promo-form-close').addEventListener('click', () => closeForm());
  container.querySelector('#promo-form-cancel').addEventListener('click', () => closeForm());
  container.querySelector('#promo-form-submit').addEventListener('click', submitForm);
  container.querySelector('#f-type').addEventListener('change', updateValueHint);
  container.querySelector('#f-code').addEventListener('input', e => {
    e.target.value = e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, '');
  });

  // Filters
  container.querySelector('#promo-search').addEventListener('input', (e) => {
    _filters.search = e.target.value;
    renderTable();
  });
  container.querySelector('#promo-filter-status').addEventListener('change', (e) => {
    _filters.status = e.target.value;
    loadPromos();
  });
  container.querySelector('#promo-filter-type').addEventListener('change', (e) => {
    _filters.type = e.target.value;
    loadPromos();
  });

  renderTemplates();
  await loadPromos();
}

const TEMPLATES = [
  { code: 'LAUNCH20',    type: 'discount_percent', value: 20, description: '20% off launch deal', tier: null },
  { code: 'STUDENTLIFE', type: 'discount_percent', value: 50, description: '50% student discount', tier: 'pro' },
  { code: 'FREETRIAL',   type: 'unlimited_trial',  value: 0,  description: 'Unlimited free trial',  tier: null },
  { code: 'EXTEND14',    type: 'trial_extension',  value: 14, description: '+14 extra trial days',  tier: null },
];

function renderTemplates() {
  const el = document.getElementById('promo-templates');
  if (!el) return;
  el.innerHTML = TEMPLATES.map(t => `
    <div class="card" style="padding:14px;cursor:pointer;border:1px solid rgba(14,165,233,.2)" onclick='window._promoFillTemplate(${JSON.stringify(t)})'>
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
        <code class="key-pill">${t.code}</code>
        <span class="badge badge-info" style="font-size:.62rem">${fmt.promoType(t.type)}</span>
      </div>
      <div style="font-size:.75rem;color:#64748b">${t.description}</div>
      <div style="font-size:.8rem;color:#94a3b8;margin-top:4px">${fmt.promoValue(t.type, t.value)}</div>
    </div>
  `).join('');
}

window._promoFillTemplate = function(t) {
  openCreateForm(t);
};

async function loadPromos() {
  try {
    _promos = await promoAPI.list({
      status: _filters.status,
      type:   _filters.type,
    });
    renderKpis();
    renderTable();
  } catch (err) {
    notify.error('Failed to load promos', err.message);
    const tbody = document.getElementById('promo-table-body');
    if (tbody) tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:#ef4444;padding:24px">Error: ${err.message}</td></tr>`;
  }
}

function renderKpis() {
  const active    = _promos.filter(p => p.active).length;
  const totalUses = _promos.reduce((s, p) => s + (p.used_count || 0), 0);
  const kpis = [
    { label: 'Total Promos',   value: _promos.length,    icon: '🎟', color: '#0ea5e9' },
    { label: 'Active',         value: active,            icon: '✅', color: '#10b981' },
    { label: 'Total Uses',     value: fmt.number(totalUses), icon: '🎯', color: '#8b5cf6' },
    { label: 'Templates',      value: TEMPLATES.length,  icon: '⚡', color: '#f59e0b' },
  ];
  const el = document.getElementById('promo-kpis');
  if (!el) return;
  el.innerHTML = kpis.map(k => `
    <div class="kpi-card" style="--kpi-color:${k.color}">
      <div class="kpi-icon">${k.icon}</div>
      <div class="kpi-label">${k.label}</div>
      <div class="kpi-value">${k.value}</div>
    </div>
  `).join('');
}

function renderTable() {
  const tbody = document.getElementById('promo-table-body');
  if (!tbody) return;

  let rows = _promos;
  const q = _filters.search.toUpperCase().trim();
  if (q) rows = rows.filter(p => (p.code || '').includes(q) || (p.description || '').toLowerCase().includes(q.toLowerCase()));

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-state" style="padding:32px;text-align:center;color:#475569">No promo codes found</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(p => {
    const isExpired = fmt.isExpired(p.expires_at);
    const atLimit   = fmt.atLimit(p.used_count, p.max_uses);
    const effectivelyActive = p.active && !isExpired && !atLimit;
    return `
      <tr data-id="${p.id}">
        <td><code class="key-pill">${p.code}</code></td>
        <td><span class="badge badge-info">${fmt.promoType(p.type)}</span></td>
        <td style="font-weight:600;color:#f1f5f9">${fmt.promoValue(p.type, p.value)}</td>
        <td>${p.tier ? `<span class="badge ${fmt.tierBadge(p.tier)}">${p.tier.toUpperCase()}</span>` : '<span class="text-muted">All</span>'}</td>
        <td>
          <label class="toggle-wrap" title="${effectivelyActive ? 'Deactivate' : 'Activate'}">
            <input type="checkbox" class="toggle-input promo-active-toggle" data-id="${p.id}" ${p.active ? 'checked' : ''}>
            <span class="toggle-track"><span class="toggle-thumb"></span></span>
          </label>
          ${isExpired ? '<span class="badge badge-warning" style="margin-left:4px">Expired</span>' : ''}
          ${atLimit   ? '<span class="badge badge-muted"  style="margin-left:4px">Limit Reached</span>' : ''}
        </td>
        <td class="tabular-nums">${fmt.number(p.used_count || 0)}</td>
        <td class="tabular-nums">${p.max_uses === null ? '∞' : fmt.number(p.max_uses)}</td>
        <td>${fmt.relative(p.expires_at) !== '—' && p.expires_at ? fmt.date(p.expires_at) : '<span class="text-muted">Never</span>'}</td>
        <td>
          <div style="display:flex;gap:4px">
            <button class="btn btn-ghost btn-xs" onclick="window._promoEdit('${p.id}')" title="Edit">✏️</button>
            <button class="btn btn-ghost btn-xs" onclick="window._promoUsage('${p.id}','${p.code}')" title="Usage">📊</button>
            <button class="btn btn-ghost btn-xs" style="color:#f87171" onclick="window._promoDelete('${p.id}','${p.code}')" title="Delete">🗑</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  // Toggle listeners
  tbody.querySelectorAll('.promo-active-toggle').forEach(chk => {
    chk.addEventListener('change', async (e) => {
      const id = e.target.dataset.id;
      const active = e.target.checked;
      try {
        await promoAPI.toggle(id, active);
        await auditAPI.log({ action: active ? 'activated' : 'deactivated', entityType: 'promo', entityId: id });
        notify.success(`Promo ${active ? 'activated' : 'deactivated'}`);
        const promo = _promos.find(p => p.id === id);
        if (promo) promo.active = active;
      } catch (err) {
        notify.error('Failed to update promo', err.message);
        e.target.checked = !active; // revert
      }
    });
  });
}

function openCreateForm(prefill = null) {
  document.getElementById('promo-form-title').textContent = prefill?.id ? 'Edit Promo Code' : 'Create Promo Code';
  document.getElementById('promo-form-submit').textContent = prefill?.id ? 'Save Changes' : 'Create Promo';
  document.getElementById('promo-edit-id').value = prefill?.id || '';

  // Reset form
  document.getElementById('f-code').value       = prefill?.code        || '';
  document.getElementById('f-type').value        = prefill?.type        || '';
  document.getElementById('f-value').value       = prefill?.value       ?? '';
  document.getElementById('f-tier').value        = prefill?.tier        || '';
  document.getElementById('f-max-uses').value    = prefill?.max_uses    != null ? prefill.max_uses : '';
  document.getElementById('f-expires').value     = prefill?.expires_at  ? prefill.expires_at.slice(0,16) : '';
  document.getElementById('f-description').value = prefill?.description || '';
  document.getElementById('f-active').checked    = prefill?.active !== false;

  clearFormErrors('promo-form');
  updateValueHint();

  document.getElementById('modal-promo-form').classList.remove('hidden');
  setTimeout(() => document.getElementById('f-code').focus(), 100);
}

function closeForm() {
  document.getElementById('modal-promo-form').classList.add('hidden');
}

function updateValueHint() {
  const type = document.getElementById('f-type')?.value;
  const hint = document.getElementById('f-value-hint');
  if (!hint) return;
  const hints = {
    discount_percent: 'Percentage off (0–100)',
    discount_fixed:   'Amount in cents (e.g., 500 = $5.00)',
    trial_extension:  'Extra trial days to add',
    unlimited_trial:  'Set to 0 (value not used)',
  };
  hint.textContent = hints[type] || 'Enter the discount value';
}

async function submitForm() {
  clearFormErrors('promo-form');

  const isEdit   = !!document.getElementById('promo-edit-id').value;
  const id       = document.getElementById('promo-edit-id').value;
  const code     = document.getElementById('f-code').value.trim().toUpperCase().replace(/[^A-Z0-9_-]/g, '');
  const type     = document.getElementById('f-type').value;
  const value    = parseInt(document.getElementById('f-value').value, 10);
  const tier     = document.getElementById('f-tier').value || null;
  const maxUses  = document.getElementById('f-max-uses').value !== '' ? parseInt(document.getElementById('f-max-uses').value, 10) : null;
  const expires  = document.getElementById('f-expires').value ? new Date(document.getElementById('f-expires').value).toISOString() : null;
  const desc     = document.getElementById('f-description').value.trim() || null;
  const active   = document.getElementById('f-active').checked;

  // Validate
  let hasError = false;
  if (!isEdit) {
    const codeErr = validate.promoCode(code);
    if (codeErr) { setFieldError('f-code', codeErr); hasError = true; }
  }
  if (!type) { setFieldError('f-type', 'Type is required'); hasError = true; }
  const valErr = validate.positiveInt(isNaN(value) ? '' : value, 'Value');
  if (valErr) { setFieldError('f-value', valErr); hasError = true; }
  if (type === 'discount_percent') {
    const pctErr = validate.percent(value);
    if (pctErr) { setFieldError('f-value', pctErr); hasError = true; }
  }
  if (hasError) return;

  const btn = document.getElementById('promo-form-submit');
  btn.disabled = true;
  btn.textContent = isEdit ? 'Saving…' : 'Creating…';

  try {
    if (isEdit) {
      await promoAPI.update(id, { type, value, tier, max_uses: maxUses, expires_at: expires, description: desc, active });
      await auditAPI.log({ action: 'updated', entityType: 'promo', entityId: id, newValues: { type, value, tier, max_uses: maxUses } });
      notify.success('Promo code updated');
    } else {
      const created = await promoAPI.create({ code, type, value, tier, max_uses: maxUses, expires_at: expires, description: desc });
      await auditAPI.log({ action: 'created', entityType: 'promo', entityId: created.id, newValues: { code, type, value } });
      notify.success(`Promo "${created.code}" created!`);
    }
    closeForm();
    await loadPromos();
  } catch (err) {
    notify.error(isEdit ? 'Update failed' : 'Creation failed', err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = isEdit ? 'Save Changes' : 'Create Promo';
  }
}

window._promoEdit = function(id) {
  const promo = _promos.find(p => p.id === id);
  if (promo) openCreateForm({ ...promo, id });
};

window._promoDelete = async function(id, code) {
  const ok = await confirm(`Delete "${code}"?`, 'This promo code will be permanently deleted and can no longer be used.', 'Delete', 'danger');
  if (!ok) return;
  try {
    await promoAPI.delete(id);
    await auditAPI.log({ action: 'deleted', entityType: 'promo', entityId: id, oldValues: { code } });
    notify.success(`Promo "${code}" deleted`);
    _promos = _promos.filter(p => p.id !== id);
    renderTable();
    renderKpis();
  } catch (err) {
    notify.error('Delete failed', err.message);
  }
};

window._promoUsage = async function(id, code) {
  document.getElementById('usage-code-label').textContent = code;
  document.getElementById('modal-promo-usage').classList.remove('hidden');
  document.getElementById('promo-usage-body').innerHTML = '<p style="color:#64748b">Loading usage data…</p>';

  try {
    const licenses = await promoAPI.getUsage(id);
    if (!licenses.length) {
      document.getElementById('promo-usage-body').innerHTML = `<p style="color:#64748b">No licenses have used this promo code yet.</p>`;
      return;
    }
    document.getElementById('promo-usage-body').innerHTML = `
      <p style="margin-bottom:12px;color:#94a3b8">${licenses.length} license(s) have used this code:</p>
      <div class="data-table-wrap">
        <table class="data-table">
          <thead><tr><th>License ID</th><th>Tier</th><th>Created</th></tr></thead>
          <tbody>
            ${licenses.map(l => `
              <tr>
                <td><code class="key-pill">${l.id.slice(0,8)}…</code></td>
                <td><span class="badge ${fmt.tierBadge(l.tier)}">${(l.tier||'').toUpperCase()}</span></td>
                <td>${fmt.datetime(l.created_at)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  } catch (err) {
    document.getElementById('promo-usage-body').innerHTML = `<p style="color:#ef4444">Error: ${err.message}</p>`;
  }
};
