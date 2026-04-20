/**
 * AgentSentinel Admin — Validation utilities
 */

export const validate = {
  required(value, label = 'Field') {
    if (!value || (typeof value === 'string' && !value.trim())) {
      return `${label} is required`;
    }
    return null;
  },

  email(value) {
    if (!value) return 'Email is required';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return 'Invalid email address';
    return null;
  },

  promoCode(value) {
    if (!value || !value.trim()) return 'Promo code is required';
    const cleaned = value.trim().toUpperCase().replace(/[^A-Z0-9_-]/g, '');
    if (cleaned.length < 3) return 'Code must be at least 3 characters';
    if (cleaned.length > 64) return 'Code must be at most 64 characters';
    return null;
  },

  positiveInt(value, label = 'Value') {
    const n = Number(value);
    if (!Number.isInteger(n) || n < 0) return `${label} must be a non-negative integer`;
    return null;
  },

  percent(value) {
    const n = Number(value);
    if (!Number.isInteger(n) || n < 0 || n > 100) return 'Value must be 0–100';
    return null;
  },

  futureDate(value) {
    if (!value) return null; // optional
    const d = new Date(value);
    if (isNaN(d.getTime())) return 'Invalid date';
    if (d <= new Date()) return 'Date must be in the future';
    return null;
  },

  /** Run multiple validators and return first error */
  first(...validators) {
    for (const v of validators) {
      if (v) return v;
    }
    return null;
  },

  /** Validate a form object, returning { field: error } map */
  form(rules) {
    const errors = {};
    for (const [field, validators] of Object.entries(rules)) {
      for (const v of validators) {
        if (v) { errors[field] = v; break; }
      }
    }
    return errors;
  },
};

/** Show/clear field errors in a form */
export function setFieldError(fieldId, message) {
  const el = document.getElementById(fieldId);
  if (!el) return;
  let err = el.parentNode.querySelector('.form-error');
  if (message) {
    el.style.borderColor = '#ef4444';
    if (!err) {
      err = document.createElement('span');
      err.className = 'form-error';
      el.parentNode.appendChild(err);
    }
    err.textContent = message;
  } else {
    el.style.borderColor = '';
    if (err) err.remove();
  }
}

export function clearFormErrors(formId) {
  const form = document.getElementById(formId);
  if (!form) return;
  form.querySelectorAll('.form-error').forEach(el => el.remove());
  form.querySelectorAll('.form-control').forEach(el => { el.style.borderColor = ''; });
}
