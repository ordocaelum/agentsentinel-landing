/**
 * AgentSentinel Admin — Modal component
 */

let _currentModal = null;

/** Open a modal by its ID */
export function openModal(id) {
  const backdrop = document.getElementById(`modal-${id}`);
  if (!backdrop) return;
  backdrop.classList.remove('hidden');
  _currentModal = id;
  document.addEventListener('keydown', handleEsc);
}

/** Close a modal by its ID */
export function closeModal(id) {
  const backdrop = document.getElementById(`modal-${id}`);
  if (!backdrop) return;
  backdrop.classList.add('hidden');
  if (_currentModal === id) {
    _currentModal = null;
    document.removeEventListener('keydown', handleEsc);
  }
}

/** Close the topmost open modal */
export function closeTopModal() {
  if (_currentModal) closeModal(_currentModal);
}

function handleEsc(e) {
  if (e.key === 'Escape') closeTopModal();
}

/**
 * Show a confirmation dialog and return a Promise<boolean>.
 * @param {string} title
 * @param {string} message
 * @param {string} [confirmLabel='Confirm']
 * @param {'danger'|'warning'|'primary'} [confirmStyle='danger']
 */
export function confirm(title, message, confirmLabel = 'Confirm', confirmStyle = 'danger') {
  return new Promise((resolve) => {
    // Remove any existing confirm overlay
    document.getElementById('confirm-overlay')?.remove();

    const overlay = document.createElement('div');
    overlay.id = 'confirm-overlay';
    overlay.className = 'confirm-overlay';
    overlay.innerHTML = `
      <div class="confirm-box" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
        <h3 id="confirm-title">${escHtml(title)}</h3>
        <p>${escHtml(message)}</p>
        <div class="confirm-actions">
          <button id="confirm-cancel" class="btn btn-ghost">Cancel</button>
          <button id="confirm-ok" class="btn btn-${confirmStyle}">${escHtml(confirmLabel)}</button>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    const ok = () => { overlay.remove(); resolve(true); };
    const cancel = () => { overlay.remove(); resolve(false); };

    overlay.querySelector('#confirm-ok').addEventListener('click', ok);
    overlay.querySelector('#confirm-cancel').addEventListener('click', cancel);
    overlay.addEventListener('click', (e) => { if (e.target === overlay) cancel(); });

    const handleKey = (e) => {
      if (e.key === 'Escape') { cancel(); document.removeEventListener('keydown', handleKey); }
      if (e.key === 'Enter')  { ok();    document.removeEventListener('keydown', handleKey); }
    };
    document.addEventListener('keydown', handleKey);
  });
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Create a standard modal backdrop element and append to body */
export function createModal(id, title, bodyHtml, footerHtml = '', size = '') {
  document.getElementById(`modal-${id}`)?.remove();

  const el = document.createElement('div');
  el.id = `modal-${id}`;
  el.className = 'modal-backdrop hidden';
  el.innerHTML = `
    <div class="modal-box${size ? ' modal-' + size : ''}" role="dialog" aria-modal="true" aria-labelledby="modal-${id}-title">
      <div class="modal-header">
        <h2 class="modal-title" id="modal-${id}-title">${escHtml(title)}</h2>
        <button class="btn btn-ghost btn-sm" onclick="window._adminModals.close('${id}')" aria-label="Close">✕</button>
      </div>
      <div class="modal-body">${bodyHtml}</div>
      ${footerHtml ? `<div class="modal-footer">${footerHtml}</div>` : ''}
    </div>
  `;

  // Click outside to close
  el.addEventListener('click', (e) => { if (e.target === el) closeModal(id); });

  document.body.appendChild(el);
  return el;
}

// Expose to global scope for onclick handlers
if (typeof window !== 'undefined') {
  window._adminModals = { open: openModal, close: closeModal };
}
