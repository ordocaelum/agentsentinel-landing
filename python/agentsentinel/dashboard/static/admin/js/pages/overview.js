/**
 * Admin — Overview page
 */
import { metricsAPI } from '../api.js';
import { fmt } from '../utils/format.js';
import { notify } from '../components/notifications.js';

export async function render(container) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">📊 Dashboard Overview</h1>
        <p class="page-subtitle">Real-time KPIs and system status</p>
      </div>
      <button class="btn btn-ghost btn-sm" id="overview-refresh">🔄 Refresh</button>
    </div>

    <!-- KPI Grid -->
    <div class="kpi-grid" id="kpi-grid">
      ${[...Array(8)].map((_, i) => `<div class="kpi-card skeleton" style="height:90px"></div>`).join('')}
    </div>

    <!-- System Status + Quick Stats -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px" id="status-row">
      <!-- System Health -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">🛰 System Status</span>
          <span id="sys-last-check" class="text-xs text-muted">—</span>
        </div>
        <div id="sys-status-list" style="display:flex;flex-direction:column;gap:8px">
          ${['Supabase DB', 'Licenses Table', 'Promo Codes', 'Webhook Events'].map(s => `
            <div class="sys-status-card">
              <span class="status-dot gray pulsing" id="sys-dot-${s.replace(/ /g,'-').toLowerCase()}"></span>
              <span class="sys-status-label">${s}</span>
              <span class="sys-status-value" id="sys-val-${s.replace(/ /g,'-').toLowerCase()}">Checking…</span>
            </div>
          `).join('')}
        </div>
      </div>

      <!-- License Tier Breakdown -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">🎫 License Tiers</span>
        </div>
        <div id="tier-breakdown" style="display:flex;flex-direction:column;gap:10px">
          ${['free','starter','pro','pro_team','team','enterprise'].map(tier => `
            <div style="display:flex;align-items:center;gap:10px">
              <span class="badge ${fmt.tierBadge(tier)}" style="min-width:72px;justify-content:center">${tier.toUpperCase()}</span>
              <div style="flex:1;background:rgba(148,163,184,.1);border-radius:4px;height:6px;overflow:hidden">
                <div id="tier-bar-${tier}" style="height:100%;border-radius:4px;background:var(--tier-color-${tier},#0ea5e9);width:0%;transition:width .6s"></div>
              </div>
              <span id="tier-count-${tier}" class="text-xs text-muted tabular-nums" style="min-width:28px;text-align:right">—</span>
            </div>
          `).join('')}
        </div>
      </div>
    </div>

    <!-- Recent Activity -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">📋 Recent License Activity</span>
        <button class="btn btn-ghost btn-xs" onclick="window.adminApp.navigate('licenses')">View All →</button>
      </div>
      <div id="recent-licenses">
        <div class="empty-state"><div class="empty-icon">📋</div><div class="empty-title">Loading…</div></div>
      </div>
    </div>
  `;

  document.getElementById('overview-refresh')?.addEventListener('click', () => loadData(container));

  await loadData(container);
}

async function loadData(container) {
  try {
    const m = await metricsAPI.getOverview();
    renderKpis(m);
    renderTierBars(m);
    await checkSysHealth();
  } catch (err) {
    notify.error('Failed to load metrics', err.message);
  }
}

function renderKpis(m) {
  const kpis = [
    { label: 'Total Licenses',   value: fmt.number(m.total_licenses),   sub: `${m.active_licenses} active`,   icon: '🎫', color: '#0ea5e9' },
    { label: 'Active Licenses',  value: fmt.number(m.active_licenses),  sub: `${fmt.number(m.new_licenses_month)} this month`, icon: '✅', color: '#10b981' },
    { label: 'Total Customers',  value: fmt.number(m.total_customers),  sub: `${m.new_customers_week} this week`, icon: '👥', color: '#6366f1' },
    { label: 'New This Month',   value: fmt.number(m.new_customers_month), sub: 'customers',               icon: '📈', color: '#f59e0b' },
    { label: 'Total Promos',     value: fmt.number(m.total_promos),     sub: `${m.active_promos} active`,    icon: '🎟', color: '#ec4899' },
    { label: 'Promo Uses',       value: fmt.number(m.promo_uses),       sub: 'total redemptions',            icon: '🎯', color: '#8b5cf6' },
    { label: 'Webhook Events',   value: fmt.number(m.total_webhooks),   sub: `${m.processed_webhooks} processed`, icon: '🔗', color: '#14b8a6' },
    { label: 'Failed Webhooks',  value: fmt.number(m.failed_webhooks),  sub: 'need attention',               icon: '⚠️',  color: m.failed_webhooks > 0 ? '#ef4444' : '#10b981' },
  ];

  const grid = document.getElementById('kpi-grid');
  if (!grid) return;
  grid.innerHTML = kpis.map(k => `
    <div class="kpi-card" style="--kpi-color:${k.color}">
      <div class="kpi-icon">${k.icon}</div>
      <div class="kpi-label">${k.label}</div>
      <div class="kpi-value">${k.value}</div>
      <div class="kpi-sub">${k.sub}</div>
    </div>
  `).join('');
}

function renderTierBars(m) {
  const tiers = m.licenses_by_tier || {};
  const total = m.total_licenses || 1;
  const colors = { free: '#64748b', starter: '#06b6d4', pro: '#0ea5e9', pro_team: '#6366f1', team: '#8b5cf6', enterprise: '#f59e0b' };
  for (const [tier, cnt] of Object.entries(tiers)) {
    const bar = document.getElementById(`tier-bar-${tier}`);
    const lbl = document.getElementById(`tier-count-${tier}`);
    if (bar) { bar.style.width = `${(cnt / total * 100).toFixed(1)}%`; bar.style.background = colors[tier] || '#0ea5e9'; }
    if (lbl) lbl.textContent = cnt;
  }
}

async function checkSysHealth() {
  const tables = [
    { id: 'supabase-db',     label: 'Supabase DB',     table: 'customers' },
    { id: 'licenses-table',  label: 'Licenses Table',  table: 'licenses' },
    { id: 'promo-codes',     label: 'Promo Codes',     table: 'promo_codes' },
    { id: 'webhook-events',  label: 'Webhook Events',  table: 'webhook_events' },
  ];

  await Promise.all(tables.map(async ({ id, table }) => {
    const dot = document.getElementById(`sys-dot-${id}`);
    const val = document.getElementById(`sys-val-${id}`);
    try {
      const { getConfig } = await import('../utils/auth.js');
      const { supabaseUrl, supabaseKey } = getConfig();
      const t0 = Date.now();
      const res = await fetch(`${supabaseUrl}/rest/v1/${table}?limit=1`, {
        headers: { apikey: supabaseKey, Authorization: `Bearer ${supabaseKey}` },
      });
      const ms = Date.now() - t0;
      if (dot) { dot.className = `status-dot ${res.ok ? 'green' : 'red'}`; }
      if (val) val.textContent = res.ok ? `✓ ${ms}ms` : `✗ HTTP ${res.status}`;
    } catch {
      if (dot) dot.className = 'status-dot red';
      if (val) val.textContent = '✗ Unreachable';
    }
  }));

  const lastEl = document.getElementById('sys-last-check');
  if (lastEl) lastEl.textContent = `Last check: ${new Date().toLocaleTimeString()}`;
}
