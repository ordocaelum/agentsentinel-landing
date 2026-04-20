/**
 * AgentSentinel Admin — Format utilities
 */

export const fmt = {
  /** Format a monetary value in cents to a dollars string */
  money(cents, currency = 'USD') {
    if (cents == null) return '—';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
    }).format(cents / 100);
  },

  /** Format a number with commas */
  number(n) {
    if (n == null) return '—';
    return new Intl.NumberFormat('en-US').format(n);
  },

  /** Format a percent */
  percent(n, decimals = 1) {
    if (n == null) return '—';
    return `${Number(n).toFixed(decimals)}%`;
  },

  /** Format an ISO date string to readable date */
  date(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleDateString('en-US', {
        year: 'numeric', month: 'short', day: 'numeric',
      });
    } catch { return '—'; }
  },

  /** Format an ISO date string to readable datetime */
  datetime(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString('en-US', {
        year: 'numeric', month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit',
      });
    } catch { return '—'; }
  },

  /** Relative time ("2 minutes ago", "in 3 days") */
  relative(iso) {
    if (!iso) return '—';
    try {
      const diff = Date.now() - new Date(iso).getTime();
      const abs = Math.abs(diff);
      const future = diff < 0;
      if (abs < 60_000)        return future ? 'in a moment' : 'just now';
      if (abs < 3_600_000)     return `${future ? 'in ' : ''}${Math.round(abs / 60_000)}m${future ? '' : ' ago'}`;
      if (abs < 86_400_000)    return `${future ? 'in ' : ''}${Math.round(abs / 3_600_000)}h${future ? '' : ' ago'}`;
      if (abs < 7 * 86_400_000) return `${future ? 'in ' : ''}${Math.round(abs / 86_400_000)}d${future ? '' : ' ago'}`;
      return fmt.date(iso);
    } catch { return '—'; }
  },

  /** Mask a string (show first/last N chars, rest is •) */
  mask(str, showFirst = 8, showLast = 4) {
    if (!str) return '—';
    if (str.length <= showFirst + showLast) return str;
    const masked = '•'.repeat(Math.max(4, str.length - showFirst - showLast));
    return `${str.slice(0, showFirst)}${masked}${str.slice(-showLast)}`;
  },

  /** Return true if an ISO expiry string represents a past date */
  isExpired(iso) {
    if (!iso) return false;
    try { return new Date(iso) < new Date(); } catch { return false; }
  },

  /** Return true if used_count has reached max_uses (null max_uses = unlimited) */
  atLimit(usedCount, maxUses) {
    return maxUses !== null && maxUses !== undefined && usedCount >= maxUses;
  },

  /** Promo type human label */
  promoType(type) {
    const map = {
      discount_percent: 'Discount %',
      discount_fixed:   'Discount $',
      trial_extension:  'Trial Days',
      unlimited_trial:  'Unlimited Trial',
    };
    return map[type] || type || '—';
  },

  /** Promo value human label */
  promoValue(type, value) {
    if (type === 'discount_percent') return `${value}% off`;
    if (type === 'discount_fixed')   return `$${(value / 100).toFixed(2)} off`;
    if (type === 'trial_extension')  return `+${value} days`;
    if (type === 'unlimited_trial')  return 'Unlimited';
    return value;
  },

  /** License tier badge class */
  tierBadge(tier) {
    const map = {
      free: 'badge-muted',
      pro:  'badge-info',
      team: 'badge-purple',
      enterprise: 'badge-warning',
    };
    return map[tier] || 'badge-muted';
  },

  /** License status badge class */
  statusBadge(status) {
    const map = {
      active:    'badge-success',
      revoked:   'badge-danger',
      expired:   'badge-warning',
      cancelled: 'badge-muted',
    };
    return map[status] || 'badge-muted';
  },
};
