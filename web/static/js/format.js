// ── Formatters (pure functions) ─────────────────────────────────────────

export function formatTs(ts) {
    if (!ts || ts <= 0) return '—';
    const d = new Date(ts);
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// Compact date for tight cells: "31 июл" (year appended only if not current)
const MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
export function formatDateShort(ts) {
    if (!ts || ts <= 0) return '—';
    const d = new Date(ts);
    const base = `${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}`;
    return d.getFullYear() === new Date().getFullYear() ? base : `${base} ${d.getFullYear()}`;
}

export function formatTraffic(bytes) {
    if (!bytes || bytes <= 0) return '0 B';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`;
    return `${(bytes / 1073741824).toFixed(2)} GB`;
}

// Money: 99.3000000004 → "99.3", 129 → "129"
export function formatMoney(amount) {
    const n = Number(amount) || 0;
    const rounded = Math.round(n * 100) / 100;
    return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2);
}

// Russian plural: plural(5, ['день', 'дня', 'дней']) → 'дней'
export function plural(n, forms) {
    const mod100 = Math.abs(n) % 100;
    const mod10 = mod100 % 10;
    if (mod100 > 10 && mod100 < 20) return forms[2];
    if (mod10 > 1 && mod10 < 5) return forms[1];
    if (mod10 === 1) return forms[0];
    return forms[2];
}

// Big counter on home: { value: 5, unit: 'дн.' } / { value: 3, unit: 'ч' }
export function remainingParts(endTs, now = Date.now()) {
    const remaining = (endTs || 0) - now;
    if (remaining <= 0) return { value: '0', unit: 'дн.' };
    if (remaining >= 86400000) return { value: String(Math.floor(remaining / 86400000)), unit: 'дн.' };
    if (remaining >= 3600000) return { value: String(Math.floor(remaining / 3600000)), unit: 'ч' };
    return { value: String(Math.floor(remaining / 60000)), unit: 'мин' };
}

export function subscriptionStatus(u) {
    const end = u?.subscriptionEnd || 0;
    const now = Date.now();
    if (end > now) {
        const daysLeft = (end - now) / 86400000;
        return daysLeft <= 7
            ? { text: 'Скоро истекает', cls: 'b-expiring' }
            : { text: 'Активна', cls: 'b-active' };
    }
    if (end > 0) return { text: 'Истекла', cls: 'b-inactive' };
    return { text: 'Нет подписки', cls: 'b-inactive' };
}

export function formatLastOnline(ts) {
    if (!ts || ts <= 0) return '—';
    const diff = Date.now() - ts;
    if (diff < 60000) return 'только что';
    if (diff < 3600000) return `${Math.floor(diff / 60000)} мин. назад`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)} ч. назад`;
    return formatTs(ts);
}
