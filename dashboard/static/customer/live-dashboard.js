// AgentSentinel Live Dashboard — polling, event stream rendering, approval actions
// Polls every 3 seconds for stats and every 5 seconds for events.

import { fetchStats, fetchEvents, getDashboardParams } from "./customer-api.js";

// ── State ────────────────────────────────────────────────────────────────────

const state = {
  licenseKey: null,
  polling: false,
  lastEventId: null,
};

// ── Bootstrap ────────────────────────────────────────────────────────────────

export async function initDashboard() {
  const { licenseKey } = getDashboardParams();
  if (!licenseKey) {
    showFatalError("No license key found. Please use the link from your purchase email or onboarding wizard.");
    return;
  }
  state.licenseKey = licenseKey;

  // Initial load
  await refreshAll();

  // Start polling loops
  state.polling = true;
  setInterval(() => refreshStats(), 3000);
  setInterval(() => refreshEvents(), 5000);
}

// ── Refresh helpers ───────────────────────────────────────────────────────────

async function refreshAll() {
  await Promise.all([refreshStats(), refreshEvents()]);
}

async function refreshStats() {
  try {
    const stats = await fetchStats(state.licenseKey);
    renderStats(stats);
  } catch { /* silently skip — network blip */ }
}

async function refreshEvents() {
  try {
    const { events } = await fetchEvents(state.licenseKey, { limit: 20 });
    renderEventStream(events);
  } catch { /* silently skip */ }
}

// ── Renderers ────────────────────────────────────────────────────────────────

function renderStats(stats) {
  setEl("#stat-spend",     `$${(stats.total_spend || 0).toFixed(4)}`);
  setEl("#stat-events",    (stats.event_count || 0).toLocaleString());
  setEl("#stat-approvals", stats.approvals_pending || 0);
  setEl("#stat-tier",      capitalize(stats.tier || "—"));
  setEl("#stat-status",    stats.agent_status === "running" ? "🟢 Running" : "⏸ Paused");

  // Budget progress bars
  if (stats.daily_budget) {
    const pct = Math.min(100, ((stats.total_spend || 0) / stats.daily_budget) * 100);
    setProgress("#bar-daily", pct);
    setEl("#lbl-daily", `$${(stats.total_spend || 0).toFixed(2)} / $${stats.daily_budget.toFixed(2)}`);
  }

  // Uptime
  if (stats.uptime_since) {
    const since = new Date(stats.uptime_since);
    const mins = Math.floor((Date.now() - since.getTime()) / 60000);
    setEl("#stat-uptime", mins < 60 ? `${mins}m` : `${Math.floor(mins / 60)}h ${mins % 60}m`);
  }
}

function renderEventStream(events) {
  const tbody = document.getElementById("event-table-body");
  if (!tbody) return;

  if (!events || events.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-center text-slate-500 py-8">No events yet. Run the test script from the onboarding wizard to see events here.</td></tr>`;
    return;
  }

  tbody.innerHTML = events.map((ev) => {
    const statusClass = {
      allowed: "text-green-400",
      blocked: "text-red-400",
      pending: "text-yellow-400",
      expired: "text-orange-400",
    }[ev.status] || "text-slate-400";

    const cost = ev.cost != null ? `$${parseFloat(ev.cost).toFixed(4)}` : "—";
    const ts = ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : "—";

    return `<tr class="border-b border-slate-800 hover:bg-slate-800/30 transition-colors">
      <td class="px-4 py-2 font-mono text-xs text-slate-400">${escHtml(ts)}</td>
      <td class="px-4 py-2 font-mono text-xs text-slate-300">${escHtml(ev.agent_id || "—")}</td>
      <td class="px-4 py-2 text-sm text-white">${escHtml(ev.tool_name || "—")}</td>
      <td class="px-4 py-2"><span class="${statusClass} text-xs font-semibold uppercase">${escHtml(ev.status || "—")}</span></td>
      <td class="px-4 py-2 text-sm text-slate-300 font-mono">${escHtml(cost)}</td>
    </tr>`;
  }).join("");
}

// ── Utility helpers ───────────────────────────────────────────────────────────

function setEl(selector, value) {
  const el = document.querySelector(selector);
  if (el) el.textContent = value;
}

function setProgress(selector, pct) {
  const el = document.querySelector(selector);
  if (el) el.style.width = `${pct}%`;
}

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function showFatalError(msg) {
  const el = document.getElementById("dash-fatal-error");
  if (el) { el.textContent = msg; el.classList.remove("hidden"); }
}
