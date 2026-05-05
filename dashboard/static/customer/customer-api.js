// AgentSentinel Customer Dashboard API
// Calls the new Edge Functions using the dashboard_token embedded in the URL.

const SUPABASE_URL = (
  window.__AS_SUPABASE_URL ||
  "https://your-project.supabase.co"
);
const FN_BASE = `${SUPABASE_URL}/functions/v1`;

/**
 * Parse the dashboard_token and customer_id from the current URL.
 * URL format: /d/{customer_id}/{dashboard_token}
 * Query param fallback: ?token=<license_key>
 */
export function getDashboardParams() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  // /d/{customer_id}/{dashboard_token}
  if (parts[0] === "d" && parts.length >= 3) {
    return { customerId: parts[1], dashboardToken: parts[2], licenseKey: null };
  }
  // Fallback: ?token=<license_key> (for onboarding wizard)
  const params = new URLSearchParams(window.location.search);
  return { customerId: null, dashboardToken: null, licenseKey: params.get("token") };
}

/**
 * Fetch the dashboard configuration for the given license key.
 * Returns the JSON from GET /customer-dashboard/{license_key}
 */
export async function fetchDashboardConfig(licenseKey) {
  const res = await fetch(`${FN_BASE}/customer-dashboard/${encodeURIComponent(licenseKey)}`);
  if (!res.ok) throw new Error(`Dashboard config error: ${res.status}`);
  return res.json();
}

/**
 * Fetch live statistics for the dashboard.
 * Returns the JSON from GET /customer-stats/{license_key}
 */
export async function fetchStats(licenseKey) {
  const res = await fetch(`${FN_BASE}/customer-stats/${encodeURIComponent(licenseKey)}`);
  if (!res.ok) throw new Error(`Stats error: ${res.status}`);
  return res.json();
}

/**
 * Fetch the latest events for the dashboard.
 * Returns { events, total, limit, offset }
 */
export async function fetchEvents(licenseKey, { limit = 20, offset = 0, order = "desc" } = {}) {
  const url = `${FN_BASE}/customer-events-list/${encodeURIComponent(licenseKey)}?limit=${limit}&offset=${offset}&order=${order}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Events error: ${res.status}`);
  return res.json();
}

/**
 * Post a single test event to verify the pipeline end-to-end.
 */
export async function postTestEvent(licenseKey, agentId = "test-agent") {
  const payload = {
    events: [{
      license_key: licenseKey,
      agent_id: agentId,
      tool_name: "test_connection",
      status: "allowed",
      cost: 0,
      timestamp: new Date().toISOString(),
      metadata: { source: "onboarding_wizard" },
    }],
  };
  const res = await fetch(`${FN_BASE}/customer-events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Test event error: ${res.status}`);
  return res.json();
}
