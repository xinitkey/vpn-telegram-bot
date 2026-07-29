// ── Telegram WebApp wrapper ─────────────────────────────────────────────
// Real WebApp object when inside Telegram; no-op stub for browser dev.

const stub = {
    expand() {},
    ready() {},
    setHeaderColor() {},
    setBackgroundColor() {},
    onEvent() {},
    initData: '',
    initDataUnsafe: { user: { id: 1, first_name: 'Dev', last_name: 'User', username: 'dev' } },
    colorScheme: 'dark',
    themeParams: {},
    openLink: (url) => window.open(url, '_blank'),
    openTelegramLink: (url) => window.open(url, '_blank'),
    showAlert: (msg) => alert(msg),
    HapticFeedback: { impactOccurred() {}, notificationOccurred() {} },
};

export const tg = window.Telegram?.WebApp || stub;
export const initData = tg.initData || '';
export const isTelegram = Boolean(initData);
export const tgUser = tg.initDataUnsafe?.user || stub.initDataUnsafe.user;

export function initTelegram() {
    if (!window.Telegram?.WebApp) return;
    tg.ready();
    tg.expand();
}

// ── Theming ─────────────────────────────────────────────────────────────
// Dark is the default theme (tokens in styles.css). When Telegram reports
// a light colorScheme we flip the token set, then let themeParams override
// individual tokens so the app matches the user's Telegram theme.

const PARAM_MAP = {
    bg_color: '--bg',
    secondary_bg_color: '--card',
    text_color: '--text-1',
    hint_color: '--text-2',
    link_color: '--link',
};

const FALLBACK_BG = { light: '#f3f2f0', dark: '#0e0d0c' };

export function applyTelegramTheme() {
    const scheme = tg.colorScheme === 'light' ? 'light' : 'dark';
    document.body.classList.toggle('theme-light', scheme === 'light');

    const root = document.documentElement;
    const params = tg.themeParams || {};
    for (const cssVar of Object.values(PARAM_MAP)) root.style.removeProperty(cssVar);
    for (const [param, cssVar] of Object.entries(PARAM_MAP)) {
        if (params[param]) root.style.setProperty(cssVar, params[param]);
    }

    const bg = params.bg_color || FALLBACK_BG[scheme];
    try {
        tg.setHeaderColor(bg);
        tg.setBackgroundColor(bg);
    } catch { /* older clients */ }
}

export function initTheme() {
    applyTelegramTheme();
    try { tg.onEvent('themeChanged', applyTelegramTheme); } catch { /* unsupported */ }
}

export function haptic(style = 'light') {
    try { tg.HapticFeedback.impactOccurred(style); } catch { /* unsupported */ }
}

export function hapticNotify(type = 'success') {
    try { tg.HapticFeedback.notificationOccurred(type); } catch { /* unsupported */ }
}

export function openExternal(url) {
    if (window.Telegram?.WebApp?.openLink) tg.openLink(url);
    else window.open(url, '_blank');
}

export function openTelegramLink(url) {
    if (window.Telegram?.WebApp?.openTelegramLink) tg.openTelegramLink(url);
    else window.open(url, '_blank');
}
