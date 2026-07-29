// ── API layer ───────────────────────────────────────────────────────────
// Single place for: auth header, timeouts, error normalization.
// Backend-agnostic (works with the aiohttp routes in web/routes.py).

import { initData } from './tg.js';

export class ApiError extends Error {
    constructor(message, status = 0) {
        super(message);
        this.status = status;
    }
}

const DEV_USER_ID = 1; // used only when opened in a plain browser (backend DEV_MODE)
const DEFAULT_TIMEOUT = 12000;

function withDevUser(path) {
    if (initData) return path;
    const sep = path.includes('?') ? '&' : '?';
    return `${path}${sep}userId=${DEV_USER_ID}`;
}

async function request(path, { method = 'GET', body, timeout = DEFAULT_TIMEOUT } = {}) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    let res;
    try {
        res = await fetch(withDevUser(path), {
            method,
            headers: {
                ...(body ? { 'Content-Type': 'application/json' } : {}),
                'X-Init-Data': initData,
            },
            body: body ? JSON.stringify({ ...body, initData }) : undefined,
            signal: ctrl.signal,
        });
    } catch (e) {
        const msg = e.name === 'AbortError'
            ? 'Сервер не отвечает. Попробуйте ещё раз'
            : 'Сбой сети. Проверьте соединение';
        throw new ApiError(msg, 0);
    } finally {
        clearTimeout(timer);
    }

    let data = null;
    try { data = await res.json(); } catch { /* non-JSON response */ }
    if (!res.ok) {
        throw new ApiError(data?.error || `Ошибка сервера (${res.status})`, res.status);
    }
    return data;
}

export const api = {
    getConfig: () => request('/api/config'),
    getUserData: () => request('/api/user-data'),
    getDevices: () => request('/api/user-devices'),
    applyPromo: (code) => request('/api/apply-promo', { method: 'POST', body: { code } }),
    buySubscription: ({ days, price, promoCode }) =>
        request('/api/buy-subscription', { method: 'POST', body: { days, price, promoCode } }),
    createPayment: ({ amount, method, paymentMethod }) =>
        request('/api/create-payment', { method: 'POST', body: { amount, method, paymentMethod } }),
};
