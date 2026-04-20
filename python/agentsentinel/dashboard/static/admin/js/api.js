/**
 * AgentSentinel Admin — Supabase API client
 * All database operations go through this module.
 */

import { getConfig } from './utils/auth.js';

function cfg() {
  return getConfig();
}

/** Build fetch headers for Supabase REST API */
function headers(extra = {}) {
  const { supabaseKey } = cfg();
  return {
    apikey: supabaseKey,
    Authorization: `Bearer ${supabaseKey}`,
    'Content-Type': 'application/json',
    Prefer: 'return=representation',
    ...extra,
  };
}

/** Base URL for REST API */
function base(table) {
  const { supabaseUrl } = cfg();
  return `${supabaseUrl}/rest/v1/${table}`;
}

/** Generic GET with query string */
async function get(table, params = '') {
  const res = await fetch(`${base(table)}${params ? '?' + params : ''}`, {
    headers: headers({ Prefer: 'return=representation' }),
  });
  if (!res.ok) throw new Error(`GET ${table} failed: ${res.status} ${await res.text()}`);
  return res.json();
}

/** Generic POST (insert) */
async function post(table, body) {
  const res = await fetch(base(table), {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${table} failed: ${res.status} ${await res.text()}`);
  return res.json();
}

/** Generic PATCH (update) by id */
async function patch(table, id, body) {
  const res = await fetch(`${base(table)}?id=eq.${id}`, {
    method: 'PATCH',
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PATCH ${table} failed: ${res.status} ${await res.text()}`);
  return res.json();
}

/** Generic DELETE by id */
async function del(table, id) {
  const res = await fetch(`${base(table)}?id=eq.${id}`, {
    method: 'DELETE',
    headers: headers({ Prefer: 'return=representation' }),
  });
  if (!res.ok) throw new Error(`DELETE ${table} failed: ${res.status} ${await res.text()}`);
  // 204 = no content
  if (res.status === 204) return null;
  return res.json();
}

/** Count rows matching filter */
async function count(table, filter = '') {
  const res = await fetch(`${base(table)}${filter ? '?' + filter + '&' : '?'}select=id`, {
    headers: { ...headers(), Prefer: 'count=exact' },
  });
  if (!res.ok) throw new Error(`COUNT ${table} failed: ${res.status}`);
  const ct = res.headers.get('content-range');
  if (ct) {
    const total = ct.split('/')[1];
    return total === '*' ? 0 : parseInt(total, 10);
  }
  return 0;
}

// ═══════════════════════════════════════════════════════════════════
// PROMO CODES
// ═══════════════════════════════════════════════════════════════════

export const promoAPI = {
  /** List all promo codes with optional filters */
  async list({ search = '', status = '', type = '', tier = '', page = 1, pageSize = 50 } = {}) {
    const params = new URLSearchParams();
    params.set('select', '*');
    params.set('order', 'created_at.desc');
    params.set('limit', pageSize);
    params.set('offset', (page - 1) * pageSize);

    if (search) {
      params.set('code', `ilike.*${search.toUpperCase()}*`);
    }
    if (status === 'active')   params.set('active', 'eq.true');
    if (status === 'inactive') params.set('active', 'eq.false');
    if (type)  params.set('type', `eq.${type}`);
    if (tier)  params.set('tier', `eq.${tier}`);

    const data = await get('promo_codes', params.toString());
    return data;
  },

  /** Create a promo code via the admin Edge Function */
  async create(payload) {
    const { supabaseUrl, adminApiSecret } = cfg();
    const fnUrl = `${supabaseUrl}/functions/v1/admin-generate-promo`;

    // Normalise code
    const body = {
      ...payload,
      code: payload.code.trim().toUpperCase().replace(/[^A-Z0-9_-]/g, ''),
    };

    const res = await fetch(fnUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${adminApiSecret || cfg().supabaseKey}`,
      },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `Create promo failed: ${res.status}`);
    return data;
  },

  /** Toggle active status */
  async toggle(id, active) {
    return patch('promo_codes', id, { active });
  },

  /** Update promo */
  async update(id, payload) {
    return patch('promo_codes', id, payload);
  },

  /** Delete promo */
  async delete(id) {
    return del('promo_codes', id);
  },

  /** Get usage stats for a promo */
  async getUsage(promoId) {
    const params = `promo_code_id=eq.${promoId}&select=id,created_at,tier&limit=100`;
    const rows = await get('licenses', params);
    return rows;
  },
};

// ═══════════════════════════════════════════════════════════════════
// LICENSES
// ═══════════════════════════════════════════════════════════════════

export const licenseAPI = {
  async list({ search = '', status = '', tier = '', page = 1, pageSize = 50 } = {}) {
    const params = new URLSearchParams();
    params.set('select', '*,customers(email,name,stripe_customer_id)');
    params.set('order', 'created_at.desc');
    params.set('limit', pageSize);
    params.set('offset', (page - 1) * pageSize);

    if (status) params.set('status', `eq.${status}`);
    if (tier)   params.set('tier', `eq.${tier}`);
    if (search) {
      // Search by license key or customer email
      params.set('license_key', `ilike.*${search}*`);
    }

    return get('licenses', params.toString());
  },

  async update(id, payload) {
    return patch('licenses', id, payload);
  },

  async revoke(id) {
    return patch('licenses', id, { status: 'revoked' });
  },

  async activate(id) {
    return patch('licenses', id, { status: 'active' });
  },

  async delete(id) {
    return del('licenses', id);
  },
};

// ═══════════════════════════════════════════════════════════════════
// CUSTOMERS / USERS
// ═══════════════════════════════════════════════════════════════════

export const customerAPI = {
  async list({ search = '', page = 1, pageSize = 50 } = {}) {
    const params = new URLSearchParams();
    params.set('select', '*');
    params.set('order', 'created_at.desc');
    params.set('limit', pageSize);
    params.set('offset', (page - 1) * pageSize);
    if (search) params.set('email', `ilike.*${search}*`);
    return get('customers', params.toString());
  },

  async getWithLicenses(customerId) {
    const [customer, licenses] = await Promise.all([
      get('customers', `id=eq.${customerId}&select=*`),
      get('licenses', `customer_id=eq.${customerId}&select=*`),
    ]);
    return { customer: customer[0], licenses };
  },

  async update(id, payload) {
    return patch('customers', id, payload);
  },
};

// ═══════════════════════════════════════════════════════════════════
// WEBHOOKS / EVENTS
// ═══════════════════════════════════════════════════════════════════

export const webhookAPI = {
  async list({ search = '', status = '', type = '', page = 1, pageSize = 50 } = {}) {
    const params = new URLSearchParams();
    params.set('select', '*');
    params.set('order', 'created_at.desc');
    params.set('limit', pageSize);
    params.set('offset', (page - 1) * pageSize);

    if (status === 'processed')    params.set('processed', 'eq.true');
    if (status === 'unprocessed')  params.set('processed', 'eq.false');
    if (type)   params.set('event_type', `eq.${type}`);
    if (search) params.set('stripe_event_id', `ilike.*${search}*`);

    return get('webhook_events', params.toString());
  },
};

// ═══════════════════════════════════════════════════════════════════
// ADMIN LOGS
// ═══════════════════════════════════════════════════════════════════

export const auditAPI = {
  async list({ adminId = '', action = '', entityType = '', page = 1, pageSize = 50 } = {}) {
    const params = new URLSearchParams();
    params.set('select', '*');
    params.set('order', 'created_at.desc');
    params.set('limit', pageSize);
    params.set('offset', (page - 1) * pageSize);

    if (adminId)    params.set('admin_id', `ilike.*${adminId}*`);
    if (action)     params.set('action', `eq.${action}`);
    if (entityType) params.set('entity_type', `eq.${entityType}`);

    return get('admin_logs', params.toString());
  },

  async log(entry) {
    return post('admin_logs', {
      admin_id:    entry.adminId || 'admin',
      action:      entry.action,
      entity_type: entry.entityType,
      entity_id:   entry.entityId || null,
      old_values:  entry.oldValues || null,
      new_values:  entry.newValues || null,
      ip_address:  entry.ipAddress || null,
      status:      entry.status || 'success',
    });
  },
};

// ═══════════════════════════════════════════════════════════════════
// METRICS
// ═══════════════════════════════════════════════════════════════════

export const metricsAPI = {
  /** Fetch aggregated KPIs in parallel */
  async getOverview() {
    const [licenseRows, customerRows, webhookRows, promoRows] = await Promise.allSettled([
      get('licenses',      'select=id,status,tier,created_at'),
      get('customers',     'select=id,created_at'),
      get('webhook_events','select=id,processed,error_message&limit=500&order=created_at.desc'),
      get('promo_codes',   'select=id,active,used_count'),
    ]);

    const licenses  = licenseRows.status  === 'fulfilled' ? licenseRows.value  : [];
    const customers = customerRows.status === 'fulfilled' ? customerRows.value : [];
    const webhooks  = webhookRows.status  === 'fulfilled' ? webhookRows.value  : [];
    const promos    = promoRows.status    === 'fulfilled' ? promoRows.value    : [];

    const now   = Date.now();
    const day   = 86_400_000;
    const week  = 7 * day;
    const month = 30 * day;

    return {
      total_licenses:   licenses.length,
      active_licenses:  licenses.filter(l => l.status === 'active').length,
      licenses_by_tier: {
        free:       licenses.filter(l => l.tier === 'free').length,
        pro:        licenses.filter(l => l.tier === 'pro').length,
        team:       licenses.filter(l => l.tier === 'team').length,
        enterprise: licenses.filter(l => l.tier === 'enterprise').length,
      },
      new_licenses_week:  licenses.filter(l => now - new Date(l.created_at) < week).length,
      new_licenses_month: licenses.filter(l => now - new Date(l.created_at) < month).length,

      total_customers: customers.length,
      new_customers_week:  customers.filter(c => now - new Date(c.created_at) < week).length,
      new_customers_month: customers.filter(c => now - new Date(c.created_at) < month).length,

      total_webhooks:    webhooks.length,
      processed_webhooks: webhooks.filter(w => w.processed).length,
      failed_webhooks:   webhooks.filter(w => !w.processed && w.error_message).length,

      total_promos:  promos.length,
      active_promos: promos.filter(p => p.active).length,
      promo_uses:    promos.reduce((s, p) => s + (p.used_count || 0), 0),
    };
  },
};

// ═══════════════════════════════════════════════════════════════════
// DASHBOARD METRICS CACHE
// ═══════════════════════════════════════════════════════════════════

export const dashMetrics = {
  async getAll() {
    return get('dashboard_metrics', 'select=*');
  },
  async set(key, value, metadata = {}) {
    const { supabaseUrl, supabaseKey } = cfg();
    const res = await fetch(`${supabaseUrl}/rest/v1/dashboard_metrics`, {
      method: 'POST',
      headers: {
        ...headers(),
        Prefer: 'resolution=merge-duplicates',
      },
      body: JSON.stringify({ metric_key: key, metric_value: value, metadata, updated_at: new Date().toISOString() }),
    });
    if (!res.ok) throw new Error(`Set metric failed: ${res.status}`);
    return res.status === 204 ? null : res.json();
  },
};
