// ── Modal manager + promise-based dialogs ───────────────────────────────
// Replaces per-modal open/close boilerplate: overlay click closes,
// body scroll is locked, dialogs resolve with the clicked button id.

const openStack = [];

export function openModal(id) {
    const el = document.getElementById(id);
    if (!el || el.classList.contains('active')) return;
    el.classList.add('active');
    openStack.push(id);
    document.body.classList.add('modal-open');
}

export function closeModal(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('active');
    const i = openStack.indexOf(id);
    if (i !== -1) openStack.splice(i, 1);
    if (!openStack.length) document.body.classList.remove('modal-open');
}

export function isModalOpen(id) {
    return openStack.includes(id);
}

export function initModals() {
    document.addEventListener('click', (e) => {
        // click on the dimmed overlay itself closes the modal
        if (e.target.classList?.contains('modal-overlay')) {
            closeModal(e.target.id);
        }
    });
}

// ── Unified dialog (confirm / alert) ────────────────────────────────────
// showDialog({ title, message, icon: 'success'|'error'|null, buttons })
// buttons: [{ id, text, kind: 'primary'|'secondary'|'cancel', keepOpen }]
// Resolves with the clicked button id.

const ICONS = {
    success: '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#27ae60" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
    error: '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#e74c3c" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
};

export function showDialog({ title, message, icon = null, buttons = [] }) {
    return new Promise((resolve) => {
        const root = document.getElementById('dialog-modal');
        const iconEl = document.getElementById('dialog-icon');
        document.getElementById('dialog-title').textContent = title;
        document.getElementById('dialog-message').textContent = message;
        iconEl.innerHTML = icon ? ICONS[icon] : '';
        iconEl.style.display = icon ? '' : 'none';

        const box = document.getElementById('dialog-buttons');
        box.innerHTML = '';
        for (const b of buttons) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = b.text;
            btn.className = `custom-modal-btn custom-modal-btn-${b.kind || 'secondary'}`;
            btn.addEventListener('click', () => {
                if (!b.keepOpen) closeModal('dialog-modal');
                resolve(b.id);
            }, { once: true });
            box.appendChild(btn);
        }
        openModal('dialog-modal');
    });
}

export function alertDialog(title, message, isError = false) {
    return showDialog({
        title,
        message,
        icon: isError ? 'error' : 'success',
        buttons: [{ id: 'ok', text: 'Закрыть', kind: isError ? 'secondary' : 'primary' }],
    });
}
