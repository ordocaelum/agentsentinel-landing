/**
 * AgentSentinel Admin — Toast notifications component
 */

const CONTAINER_ID = 'toast-container';

function getContainer() {
  let c = document.getElementById(CONTAINER_ID);
  if (!c) {
    c = document.createElement('div');
    c.id = CONTAINER_ID;
    document.body.appendChild(c);
  }
  return c;
}

/**
 * Show a toast notification.
 * @param {'success'|'error'|'warning'|'info'} type
 * @param {string} title
 * @param {string} [message]
 * @param {number} [duration=4000]
 */
export function toast(type, title, message = '', duration = 4000) {
  const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
  const container = getContainer();

  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.innerHTML = `
    <span class="toast-icon">${icons[type] || 'ℹ️'}</span>
    <div class="toast-body">
      <div class="toast-title">${escHtml(title)}</div>
      ${message ? `<div class="toast-msg">${escHtml(message)}</div>` : ''}
    </div>
    <button class="toast-close" aria-label="Dismiss">✕</button>
    <div class="toast-progress"></div>
  `;

  el.querySelector('.toast-close').addEventListener('click', () => dismiss(el));
  container.appendChild(el);

  const timer = setTimeout(() => dismiss(el), duration);
  el.dataset.timer = timer;

  return el;
}

function dismiss(el) {
  if (el._dismissed) return;
  el._dismissed = true;
  clearTimeout(el.dataset.timer);
  el.classList.add('removing');
  el.addEventListener('animationend', () => el.remove(), { once: true });
  setTimeout(() => el.remove(), 400);
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export const notify = {
  success: (title, msg)  => toast('success', title, msg),
  error:   (title, msg)  => toast('error',   title, msg),
  warning: (title, msg)  => toast('warning', title, msg),
  info:    (title, msg)  => toast('info',    title, msg),
};
