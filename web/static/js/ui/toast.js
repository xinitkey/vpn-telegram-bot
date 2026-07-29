// ── Toast notifications ─────────────────────────────────────────────────
// Lightweight feedback for non-blocking events (copied, saved, soft errors).

let container = null;

function getContainer() {
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    return container;
}

export function toast(message, kind = 'info', duration = 2500) {
    const el = document.createElement('div');
    el.className = `toast toast-${kind}`;
    el.textContent = message;
    getContainer().appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    setTimeout(() => {
        el.classList.remove('show');
        setTimeout(() => el.remove(), 300);
    }, duration);
}
