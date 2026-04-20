/**
 * Admin — Metrics & Analytics page
 */
import { metricsAPI } from '../api.js';
import { fmt } from '../utils/format.js';
import { notify } from '../components/notifications.js';

export async function render(container) {
  container.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">📈 Metrics & Analytics</h1>
        <p class="page-subtitle">Business KPIs and system analytics</p>
      </div>
      <button class="btn btn-ghost btn-sm" id="metrics-refresh">🔄 Refresh</button>
    </div>

    <!-- Loading state -->
    <div id="metrics-loading" style="text-align:center;padding:60px;color:#475569">
      <div style="font-size:2rem;margin-bottom:12px">📊</div>
      <p>Loading metrics…</p>
    </div>
    <div id="metrics-content" class="hidden">
      <!-- License metrics -->
      <div class="card mb-4">
        <div class="card-header"><span class="card-title">🎫 License Metrics</span></div>
        <div class="kpi-grid" id="metrics-licenses" style="grid-template-columns:repeat(4,1fr)"></div>
      </div>
      <!-- Customer metrics -->
      <div class="card mb-4">
        <div class="card-header"><span class="card-title">👥 Customer Metrics</span></div>
        <div class="kpi-grid" id="metrics-customers" style="grid-template-columns:repeat(3,1fr)"></div>
      </div>
      <!-- Promo metrics -->
      <div class="card mb-4">
        <div class="card-header"><span class="card-title">🎟 Promo Metrics</span></div>
        <div class="kpi-grid" id="metrics-promos" style="grid-template-columns:repeat(3,1fr)"></div>
      </div>
      <!-- Webhook metrics -->
      <div class="card mb-4">
        <div class="card-header"><span class="card-title">🔗 Webhook Metrics</span></div>
        <div class="kpi-grid" id="metrics-webhooks" style="grid-template-columns:repeat(3,1fr)"></div>
      </div>
      <!-- Tier distribution chart -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
        <div class="card">
          <div class="card-header"><span class="card-title">🎫 License Tier Distribution</span></div>
          <div style="position:relative;height:220px;display:flex;align-items:center;justify-content:center">
            <canvas id="chart-tiers" style="max-height:200px"></canvas>
          </div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">📋 License Status Distribution</span></div>
          <div style="position:relative;height:220px;display:flex;align-items:center;justify-content:center">
            <canvas id="chart-status" style="max-height:200px"></canvas>
          </div>
        </div>
      </div>
    </div>
  `;

  document.getElementById('metrics-refresh').addEventListener('click', () => loadMetrics());
  await loadMetrics();
}

async function loadMetrics() {
  document.getElementById('metrics-loading').classList.remove('hidden');
  document.getElementById('metrics-content').classList.add('hidden');
  try {
    const m = await metricsAPI.getOverview();
    renderLicenseMetrics(m);
    renderCustomerMetrics(m);
    renderPromoMetrics(m);
    renderWebhookMetrics(m);
    renderCharts(m);
    document.getElementById('metrics-loading').classList.add('hidden');
    document.getElementById('metrics-content').classList.remove('hidden');
  } catch (err) {
    notify.error('Failed to load metrics', err.message);
    document.getElementById('metrics-loading').innerHTML = `<p style="color:#ef4444">Error: ${err.message}</p>`;
  }
}

function kpiCard(label, value, sub, icon, color) {
  return `<div class="kpi-card" style="--kpi-color:${color}"><div class="kpi-icon">${icon}</div><div class="kpi-label">${label}</div><div class="kpi-value">${value}</div>${sub ? `<div class="kpi-sub">${sub}</div>` : ''}</div>`;
}

function renderLicenseMetrics(m) {
  const el = document.getElementById('metrics-licenses');
  if (!el) return;
  const tiers = m.licenses_by_tier || {};
  el.innerHTML = [
    kpiCard('Total Licenses',      fmt.number(m.total_licenses),         '',                          '🎫', '#0ea5e9'),
    kpiCard('Active Licenses',     fmt.number(m.active_licenses),        `${fmt.percent(m.active_licenses / Math.max(m.total_licenses,1) * 100)} active rate`, '✅', '#10b981'),
    kpiCard('New This Week',       fmt.number(m.new_licenses_week),      '',                          '📈', '#6366f1'),
    kpiCard('New This Month',      fmt.number(m.new_licenses_month),     '',                          '📅', '#f59e0b'),
  ].join('');
}

function renderCustomerMetrics(m) {
  const el = document.getElementById('metrics-customers');
  if (!el) return;
  el.innerHTML = [
    kpiCard('Total Customers',  fmt.number(m.total_customers),       '',                          '👥', '#0ea5e9'),
    kpiCard('New This Week',    fmt.number(m.new_customers_week),    '',                          '📈', '#10b981'),
    kpiCard('New This Month',   fmt.number(m.new_customers_month),   '',                          '📅', '#6366f1'),
  ].join('');
}

function renderPromoMetrics(m) {
  const el = document.getElementById('metrics-promos');
  if (!el) return;
  el.innerHTML = [
    kpiCard('Total Promos',   fmt.number(m.total_promos),   '',                          '🎟', '#ec4899'),
    kpiCard('Active Promos',  fmt.number(m.active_promos),  '',                          '✅', '#10b981'),
    kpiCard('Total Uses',     fmt.number(m.promo_uses),     'total redemptions',         '🎯', '#8b5cf6'),
  ].join('');
}

function renderWebhookMetrics(m) {
  const el = document.getElementById('metrics-webhooks');
  if (!el) return;
  const successRate = m.total_webhooks > 0
    ? fmt.percent(m.processed_webhooks / m.total_webhooks * 100)
    : '—';
  el.innerHTML = [
    kpiCard('Total Events',     fmt.number(m.total_webhooks),    '',              '🔗', '#0ea5e9'),
    kpiCard('Processed',        fmt.number(m.processed_webhooks), successRate + ' success rate', '✅', '#10b981'),
    kpiCard('Failed',           fmt.number(m.failed_webhooks),   'need attention', '⚠️', m.failed_webhooks > 0 ? '#ef4444' : '#10b981'),
  ].join('');
}

function renderCharts(m) {
  const tiers = m.licenses_by_tier || {};
  const tierCtx = document.getElementById('chart-tiers');
  if (tierCtx && window.Chart) {
    new window.Chart(tierCtx, {
      type: 'doughnut',
      data: {
        labels: ['Free', 'Pro', 'Team', 'Enterprise'],
        datasets: [{
          data: [tiers.free||0, tiers.pro||0, tiers.team||0, tiers.enterprise||0],
          backgroundColor: ['#64748b','#0ea5e9','#8b5cf6','#f59e0b'],
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#94a3b8', font: { size: 11 } } } },
      },
    });
  }

  const statusCtx = document.getElementById('chart-status');
  if (statusCtx && window.Chart) {
    const active    = m.active_licenses;
    const inactive  = m.total_licenses - m.active_licenses;
    new window.Chart(statusCtx, {
      type: 'doughnut',
      data: {
        labels: ['Active', 'Inactive/Revoked'],
        datasets: [{
          data: [active, inactive],
          backgroundColor: ['#10b981', '#ef4444'],
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#94a3b8', font: { size: 11 } } } },
      },
    });
  }
}
