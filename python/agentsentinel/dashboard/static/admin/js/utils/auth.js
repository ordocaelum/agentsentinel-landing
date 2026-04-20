/**
 * AgentSentinel Admin — Auth utilities
 * Stores admin credentials for the current browser session.
 *
 * SECURITY NOTE: The Supabase service-role key is stored in sessionStorage
 * (not localStorage) so it is automatically cleared when the browser tab/
 * session is closed. The non-sensitive project URL is kept in localStorage
 * for convenience. Never expose the service-role key to end users.
 */

const URL_KEY      = 'agentsentinel-admin-url';
const KEY_KEY      = 'agentsentinel-admin-key';      // sessionStorage — clears on tab close
const SECRET_KEY   = 'agentsentinel-admin-secret';   // sessionStorage — clears on tab close

export function getConfig() {
  try {
    const supabaseUrl    = localStorage.getItem(URL_KEY) || '';
    const supabaseKey    = sessionStorage.getItem(KEY_KEY) || '';
    const adminApiSecret = sessionStorage.getItem(SECRET_KEY) || '';
    return { supabaseUrl, supabaseKey, adminApiSecret };
  } catch {
    return {};
  }
}

export function saveConfig({ supabaseUrl = '', supabaseKey = '', adminApiSecret = '' } = {}) {
  // URL is non-sensitive — persist across sessions for convenience
  localStorage.setItem(URL_KEY, supabaseUrl);
  // Keys are sensitive — use sessionStorage so they are cleared when the tab closes
  sessionStorage.setItem(KEY_KEY, supabaseKey);
  if (adminApiSecret) sessionStorage.setItem(SECRET_KEY, adminApiSecret);
  else sessionStorage.removeItem(SECRET_KEY);
}

export function clearConfig() {
  localStorage.removeItem(URL_KEY);
  sessionStorage.removeItem(KEY_KEY);
  sessionStorage.removeItem(SECRET_KEY);
}

export function hasConfig() {
  const c = getConfig();
  return !!(c.supabaseUrl && c.supabaseKey);
}

/** Verify admin credentials by attempting a minimal read against the promo_codes table.
 *  Returns true if the service-role key has access. */
export async function verifyAdminAccess(supabaseUrl, supabaseKey) {
  try {
    const res = await fetch(`${supabaseUrl}/rest/v1/promo_codes?limit=1`, {
      headers: {
        apikey: supabaseKey,
        Authorization: `Bearer ${supabaseKey}`,
        'Content-Type': 'application/json',
      },
    });
    return res.ok;
  } catch {
    return false;
  }
}
