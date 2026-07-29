// ── Store ───────────────────────────────────────────────────────────────
// Minimal observable state container. One source of truth instead of
// scattered globals + DOM-as-state.

const listeners = new Set();

export const state = {
    status: 'loading',        // 'loading' | 'ready' | 'error'
    error: '',
    user: null,               // /api/user-data payload
    config: null,             // /api/config payload (falls back to defaults)
    devices: null,            // cached /api/user-devices payload
    promo: { code: '', discountPercent: 0, tariffPrices: {} },
    selection: { tariffDays: 0 },   // UI state that must survive re-renders
};

export function setState(patch) {
    Object.assign(state, patch);
    for (const fn of listeners) fn(state);
}

export function subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
}

export function resetPromo() {
    state.promo = { code: '', discountPercent: 0, tariffPrices: {} };
}
