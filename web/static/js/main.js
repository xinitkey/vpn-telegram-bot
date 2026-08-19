// ── BlackVPN WebApp — main controller ───────────────────────────────────
// Sections: config → elements → render → data → topup → tariffs →
// purchase → devices → trial → tabs → actions → init.

import { tg, isTelegram, tgUser, initTelegram, initTheme, haptic, hapticNotify, openExternal, openTelegramLink } from './tg.js';
import { api } from './api.js';
import { state, setState, subscribe, resetPromo } from './store.js';
import * as fmt from './format.js';
import { initModals, openModal, closeModal, showDialog, alertDialog } from './ui/modal.js';
import { toast } from './ui/toast.js';
import { initParticles } from './ui/particles.js';

// ── Config ──────────────────────────────────────────────────────────────
// Fallback mirror of /api/config — lets the app work even if the endpoint
// is missing (older backend). Server response overrides it.
const DEFAULT_CONFIG = {
    tariffs: [
        { days: 3, price: 18, perDay: 6 },
        { days: 30, price: 129, perDay: 4.3 },
        { days: 90, price: 329, perDay: 3.7 },
        { days: 180, price: 599, perDay: 3.3 },
        { days: 365, price: 1149, perDay: 3.1 },
    ],
    dailyPrice: 6,
    minTopUp: 50,
    topUpPresets: [50, 100, 200, 500, 1000, 2000],
    paymentMethods: [
        { id: 'platega_sbp', label: 'СБП', code: 2 },
        { id: 'platega_mir', label: 'МИР', code: 11 },
        { id: 'platega_crypto', label: 'Криптовалюта', code: 13 },
    ],
    referralReward: 50,
    trialDays: 3,
};

const cfg = () => state.config || DEFAULT_CONFIG;

// Presentation-only metadata (prices come from the server)
const _ticon = (body) => `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
const TARIFF_ICONS = {
    zap: _ticon('<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'),
    flame: _ticon('<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>'),
    star: _ticon('<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>'),
    crown: _ticon('<path d="m2 4 3 12h14l3-12-6 7-4-7-4 7-6-7zm3 16h14"/>'),
    gem: _ticon('<path d="M6 3h12l4 6-10 13L2 9Z"/><path d="M11 3 8 9l4 13 4-13-3-6"/><path d="M2 9h20"/>'),
    spark: _ticon('<path d="M12 3l1.9 5.8 5.8 1.9-5.8 1.9L12 18.4l-1.9-5.8L4.3 10.7l5.8-1.9L12 3z"/>'),
};
const TARIFF_META = {
    3:   { icon: TARIFF_ICONS.zap,   badgeCls: 'tb-violet', label: 'Триал',    labelCls: 'tariff-trial-label' },
    30:  { icon: TARIFF_ICONS.flame, badgeCls: 'tb-blue',   label: 'Базовый',  labelCls: 'tariff-rec-label',        featured: 'tariff-recommended' },
    90:  { icon: TARIFF_ICONS.star,  badgeCls: 'tb-cyan',   label: 'Стандарт', labelCls: 'tariff-standard-label' },
    180: { icon: TARIFF_ICONS.crown, badgeCls: 'tb-green',  label: 'Выгодный', labelCls: 'tariff-profitable-label' },
    365: { icon: TARIFF_ICONS.gem,   badgeCls: 'tb-red',    label: 'Лучший',   labelCls: 'tariff-best-label',       featured: 'tariff-best' },
};

const METHOD_ICONS = {
    platega_sbp: '<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="1" y="4" width="22" height="16" rx="2"/><path d="M1 10h22"/></svg>',
    platega_mir: '<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="1" y="4" width="22" height="16" rx="2"/><path d="M3 15c2.5-3 4.5-3 7 0s4.5 3 7 0c1.2-1.4 2.3-1.6 4-1"/></svg>',
    platega_crypto: '<svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 2a10 10 0 100 20 10 10 0 000-20z"/><path d="M9 8h6a2 2 0 010 4H9z"/><path d="M9 12h7a2 2 0 010 4H9z"/><path d="M12 8v8M10 6v2M14 6v2"/></svg>',
};

const POLL_INTERVAL = 30000;
const REFRESH_MIN_GAP = 15000;
const CONNECT_PAGE = '/blackvpn-connect.html';
const RING_C = 2 * Math.PI * 50; // progress ring circumference (r=50)

// ── Elements ────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const els = {
    devNotice: $('dev-notice'),
    balance: $('balance-display'),
    days: $('days-count'),
    daysLbl: $('days-lbl'),
    ringWrap: $('ring-wrap'),
    ringProg: $('ring-prog'),
    priceDaily: $('price-daily-text'),
    statusBadge: $('statusBadge'),
    expiry: $('home-expiry'),
    traffic: $('home-traffic'),
    refReward: $('ref-reward-text'),
    refCount: $('ref-count'),
    refEarned: $('ref-earned'),
    refLinkDisplay: $('ref-link-display'),
    userPhoto: $('user-photo'),
    userPhotoPlaceholder: $('user-avatar-placeholder'),
    userName: $('user-name'),
    userUsername: $('user-username'),
    userId: $('user-id'),
    profileBalance: $('profile-balance'),
    profileSubStart: $('profile-sub-start'),
    profileSubEnd: $('profile-sub-end'),
    bannedOverlay: $('banned-overlay'),
    errorOverlay: $('error-overlay'),
    errorText: $('error-text'),
    tariffList: $('tariff-list'),
    promoInput: $('promo-input'),
    promoBtn: $('promo-btn'),
    promoStatus: $('promo-status'),
    confirmTariffBtn: $('btn-confirm-tariff'),
    amountPresets: $('amount-presets'),
    paymentMethods: $('payment-methods-list'),
    customAmount: $('custom-amount'),
    confirmTopupBtn: $('btn-confirm-topup'),
    devicesContent: $('devices-content'),
    trialOverlay: $('trial-overlay'),
    trialModal: $('trial-modal'),
    trialCancelDialog: $('trial-cancel-dialog'),
    trialBtnActivate: $('trial-btn-activate'),
    trialDontShow: $('trial-dont-show'),
};

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

// ── Render ──────────────────────────────────────────────────────────────
// Pure functions of state → DOM. Idempotent: safe to run on every poll.

function render() {
    renderIdentity();
    if (state.status === 'error' && !state.user) {
        els.errorText.textContent = state.error || 'Не удалось загрузить данные';
        els.errorOverlay.classList.add('active');
        document.body.classList.remove('app-loading');
        return;
    }
    els.errorOverlay.classList.remove('active');
    if (state.user) {
        document.body.classList.remove('app-loading');
        renderSubscription();
        renderReferral();
        renderTraffic();
        renderBanned();
        renderTariffs();
    }
}

function renderIdentity() {
    if (!tgUser) return;
    els.userId.textContent = tgUser.id || '—';
    els.userName.textContent = `${tgUser.first_name || ''} ${tgUser.last_name || ''}`.trim() || 'Пользователь';
    els.userUsername.textContent = tgUser.username ? `@${tgUser.username}` : 'нет никнейма';
    if (tgUser.photo_url && !els.userPhoto.src) {
        els.userPhoto.src = tgUser.photo_url;
        els.userPhoto.style.display = 'block';
        els.userPhotoPlaceholder.style.display = 'none';
    }
}

function renderSubscription() {
    const u = state.user;
    els.balance.textContent = fmt.formatMoney(u.balance);
    els.profileBalance.textContent = `${fmt.formatMoney(u.balance)} ₽`;

    const rest = fmt.remainingParts(u.subscriptionEnd);
    els.days.textContent = rest.value;
    els.daysLbl.textContent = rest.unit;

    els.expiry.textContent = fmt.formatDateShort(u.subscriptionEnd);
    els.profileSubStart.textContent = fmt.formatTs(u.subscriptionStart);
    els.profileSubEnd.textContent = fmt.formatTs(u.subscriptionEnd);
    els.priceDaily.textContent = `от ${cfg().dailyPrice}₽ / день`;

    const st = fmt.subscriptionStatus(u);
    els.statusBadge.textContent = st.text;
    els.statusBadge.className = `badge ${st.cls}`;

    renderRing(u, st);
}

// Subscription progress ring: fraction of the paid period still ahead.
function renderRing(u, st) {
    if (!els.ringProg || !els.ringWrap) return;
    const now = Date.now();
    const start = u.subscriptionStart || 0;
    const end = u.subscriptionEnd || 0;
    let frac = 0;
    if (end > now) {
        frac = end > start
            ? Math.min(1, Math.max(0.02, (end - now) / (end - start)))
            : 1;
    }
    els.ringProg.style.strokeDashoffset = (RING_C * (1 - frac)).toFixed(2);
    const daysLeft = (end - now) / 86400000;
    els.ringWrap.classList.toggle('is-expiring', st.cls === 'b-expiring');
    els.ringWrap.classList.toggle('is-green', end > now && daysLeft > 7 && daysLeft <= 30);
    els.ringWrap.classList.toggle('is-blue', end > now && daysLeft > 30 && daysLeft <= 90);
    els.ringWrap.classList.toggle('is-violet', end > now && daysLeft > 180);
    els.ringWrap.classList.toggle('is-empty', end <= now);
}

function renderReferral() {
    const u = state.user;
    if (!u.referralUrl) return;
    els.refReward.textContent = `${cfg().referralReward}₽`;
    els.refCount.textContent = u.referralCount || 0;
    els.refEarned.textContent = `${fmt.formatMoney(u.referralEarnings || 0)} ₽`;
}

function renderTraffic() {
    if (!state.devices) { els.traffic.textContent = '—'; return; }
    const total = (state.devices.trafficUp || 0) + (state.devices.trafficDown || 0);
    els.traffic.textContent = fmt.formatTraffic(total);
}

function renderBanned() {
    els.bannedOverlay.classList.toggle('active', Boolean(state.user?.banned));
}

// ── Data loading ────────────────────────────────────────────────────────
let refreshing = false;
let lastLoadAt = 0;

async function refresh({ force = false } = {}) {
    if (refreshing) return;
    if (!force && Date.now() - lastLoadAt < REFRESH_MIN_GAP && state.user) return;
    refreshing = true;
    try {
        const user = await api.getUserData();
        lastLoadAt = Date.now();
        const isFirst = !state.user;
        setState({ user, status: 'ready', error: '' });
        if (isFirst) {
            loadDevices();
            maybeShowTrial();
        }
    } catch (e) {
        if (!state.user) {
            setState({ status: 'error', error: e.message });
        } else {
            toast(e.message, 'error');
        }
    } finally {
        refreshing = false;
    }
}

async function loadDevices() {
    try {
        const devices = await api.getDevices();
        setState({ devices });
    } catch { /* traffic cell stays '—' */ }
}

async function loadConfig() {
    try {
        const config = await api.getConfig();
        setState({ config });
        renderTopUp();
    } catch { /* DEFAULT_CONFIG already in place */ }
}

// ── Top-up modal ────────────────────────────────────────────────────────
const topup = { amount: 0, method: '' };

function renderTopUp() {
    const c = cfg();
    els.amountPresets.innerHTML = c.topUpPresets.map((a) => (
        `<button type="button" class="amount-btn${topup.amount === a ? ' active' : ''}" data-action="select-amount" data-amount="${a}">${a} ₽</button>`
    )).join('');

    els.paymentMethods.innerHTML = c.paymentMethods.map((m) => `
        <button type="button" class="method-btn${topup.method === m.id ? ' active' : ''}" data-action="select-method" data-method="${esc(m.id)}">
            <div class="method-icon">${METHOD_ICONS[m.id] || METHOD_ICONS.platega_sbp}</div>
            <div class="method-info"><div>${esc(m.label)}</div></div>
        </button>`
    ).join('');

    els.customAmount.placeholder = `Или введите сумму (мин. ${c.minTopUp}₽)`;
    updateTopupConfirm();
}

function updateTopupConfirm() {
    const ready = topup.amount >= cfg().minTopUp && topup.method;
    els.confirmTopupBtn.disabled = !ready;
    els.confirmTopupBtn.textContent = ready ? `Пополнить на ${fmt.formatMoney(topup.amount)} ₽` : 'Пополнить';
}

function openTopUp() {
    topup.amount = 0;
    topup.method = '';
    els.customAmount.value = '';
    renderTopUp();
    openModal('topup-modal');
}

async function confirmTopUp() {
    const c = cfg();
    if (topup.amount < c.minTopUp || !topup.method) return;
    haptic('medium');

    const method = c.paymentMethods.find((m) => m.id === topup.method);
    const btn = els.confirmTopupBtn;
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Создание счёта...';
    try {
        const data = await api.createPayment({
            amount: topup.amount,
            method: topup.method,
            paymentMethod: method?.code,
        });
        closeModal('topup-modal');
        if (data.paymentUrl) {
            openExternal(data.paymentUrl);
            toast('Счёт создан. После оплаты баланс обновится автоматически');
        } else {
            alertDialog('Счёт создан', 'Оплатите счёт — баланс обновится автоматически.');
        }
    } catch (e) {
        alertDialog('Ошибка', e.message, true);
    } finally {
        btn.disabled = false;
        btn.textContent = original;
    }
}

// ── Tariffs + promo ─────────────────────────────────────────────────────

function isFreeTrial(days) {
    return days === cfg().trialDays && !state.user?.trialUsed;
}

function findPromoPrice(days) {
    const prices = state.promo.tariffPrices || {};
    for (const idx in prices) {
        if (prices[idx].days === days) return prices[idx];
    }
    return null;
}

function finalPrice(days) {
    const t = cfg().tariffs.find((x) => x.days === days);
    if (!t) return null;
    if (isFreeTrial(days)) return { price: 0, original: t.price };
    const promo = findPromoPrice(days);
    if (promo && promo.discounted < t.price) return { price: promo.discounted, original: t.price };
    return { price: t.price, original: t.price };
}

function renderTariffs() {
    if (!els.tariffList) return;
    const selected = state.selection.tariffDays;
    els.tariffList.innerHTML = cfg().tariffs.map((t) => {
        const meta = TARIFF_META[t.days] || { icon: TARIFF_ICONS.spark, badgeCls: '', label: '', labelCls: '', featured: '' };
        const free = isFreeTrial(t.days);
        const fp = finalPrice(t.days);
        const discounted = !free && fp.price < fp.original;
        const priceHtml = free
            ? '0 ₽'
            : discounted
                ? `<span class="old-price">${fp.original} ₽</span> <span class="discount-price">${fp.price} ₽</span>`
                : `${fmt.formatMoney(fp.price)} ₽`;
        const perDay = free ? 'Бесплатно' : `${String(t.perDay).replace('.', ',')} ₽/день`;
        return `
        <div class="tariff-option ${meta.featured || ''}${selected === t.days ? ' active' : ''}" data-action="select-tariff" data-days="${t.days}" role="button" tabindex="0">
            <div class="tariff-badge ${meta.badgeCls || ''}">${meta.icon}</div>
            <div class="tariff-info-block">
                <div class="tariff-days">${t.days} ${fmt.plural(t.days, ['день', 'дня', 'дней'])}</div>
                <div class="tariff-perday">${perDay}</div>
            </div>
            <div class="tariff-price">${priceHtml}</div>
            ${meta.label ? `<div class="${meta.labelCls}">${meta.label}</div>` : ''}
        </div>`;
    }).join('');
    updateTariffConfirm();
}

function updateTariffConfirm() {
    const btn = els.confirmTariffBtn;
    const grant = state.promo.grantDays || 0;
    if (grant > 0) {
        btn.disabled = false;
        btn.textContent = `Активировать +${grant} ${fmt.plural(grant, ['день', 'дня', 'дней'])} подписки`;
        return;
    }
    const days = state.selection.tariffDays;
    if (!days) {
        btn.disabled = true;
        btn.textContent = 'Выберите тариф';
        return;
    }
    const fp = finalPrice(days);
    btn.disabled = false;
    btn.textContent = fp.price === 0 ? 'Активировать триал' : `Купить за ${fmt.formatMoney(fp.price)} ₽`;
}

function openTariffs() {
    state.selection.tariffDays = 0;
    els.promoInput.value = state.promo.code || '';
    setPromoStatus('', '');
    renderTariffs();
    openModal('tariffs-modal');
}

function setPromoStatus(kind, text) {
    els.promoStatus.className = `promo-status${kind ? ` promo-${kind}` : ''}`;
    els.promoStatus.textContent = text;
}

async function applyPromo(silent = false) {
    const code = els.promoInput.value.trim();
    if (!code) {
        resetPromo();
        setPromoStatus('', '');
        renderTariffs();
        return;
    }
    if (!silent) haptic('light');
    els.promoBtn.disabled = true;
    els.promoBtn.textContent = 'Проверка...';
    try {
        const data = await api.applyPromo(code);
        if (data.valid) {
            if (data.grantDays) {
                state.promo = {
                    code,
                    grantDays: data.grantDays,
                    discountPercent: 0,
                    tariffPrices: {},
                };
                setPromoStatus('success', `Промокод дарит ${data.grantDays} ${fmt.plural(data.grantDays, ['день', 'дня', 'дней'])} подписки!`);
            } else {
                state.promo = {
                    code,
                    discountPercent: data.discountPercent,
                    tariffPrices: data.tariffPrices || {},
                    grantDays: 0,
                };
                setPromoStatus('success', `Промокод применён! Скидка ${data.discountPercent}%`);
            }
        } else {
            resetPromo();
            setPromoStatus('error', data.error || 'Промокод недействителен');
        }
    } catch (e) {
        resetPromo();
        setPromoStatus('error', e.message);
    } finally {
        els.promoBtn.disabled = false;
        els.promoBtn.textContent = 'Применить';
        renderTariffs();
    }
}

// ── Purchase flow ───────────────────────────────────────────────────────

async function purchase({ days, price }) {
    try {
        const data = await api.buySubscription({
            days,
            price,
            promoCode: state.promo.code || undefined,
        });
        hapticNotify('success');
        await refresh({ force: true });
        return { ok: true, data };
    } catch (e) {
        return { ok: false, error: e.message };
    }
}

async function afterPurchaseDialog(message) {
    const choice = await showDialog({
        title: 'Готово',
        message,
        icon: 'success',
        buttons: [
            { id: 'connect', text: 'Перейти к подключению', kind: 'primary' },
            { id: 'close', text: 'Закрыть', kind: 'secondary' },
        ],
    });
    if (choice === 'connect') window.location.href = CONNECT_PAGE;
}

async function confirmTariffPurchase() {
    const grant = state.promo.grantDays || 0;
    if (grant > 0) {
        haptic('medium');
        const btn = els.confirmTariffBtn;
        const original = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Активация...';
        const res = await purchase({ days: grant, price: 0 });
        btn.disabled = false;
        btn.textContent = original;
        if (res.ok) {
            resetPromo();
            closeModal('tariffs-modal');
            afterPurchaseDialog(`Промокод активирован! Подписка продлена на ${grant} ${fmt.plural(grant, ['день', 'дня', 'дней'])}.`);
        } else {
            alertDialog('Ошибка', res.error, true);
        }
        return;
    }
    const days = state.selection.tariffDays;
    if (!days) return;
    const fp = finalPrice(days);
    haptic('medium');

    if (fp.price > 0 && (state.user?.balance ?? 0) < fp.price) {
        const choice = await showDialog({
            title: 'Недостаточно средств',
            message: `На балансе ${fmt.formatMoney(state.user?.balance)} ₽. Нужно ${fmt.formatMoney(fp.price)} ₽.\nПополните баланс и повторите попытку.`,
            icon: 'error',
            buttons: [
                { id: 'topup', text: 'Пополнить', kind: 'primary' },
                { id: 'close', text: 'Закрыть', kind: 'secondary' },
            ],
        });
        if (choice === 'topup') {
            closeModal('tariffs-modal');
            openTopUp();
        }
        return;
    }

    const btn = els.confirmTariffBtn;
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Обработка...';
    const res = await purchase({ days, price: fp.price });
    btn.disabled = false;
    btn.textContent = original;

    if (res.ok) {
        resetPromo();
        closeModal('tariffs-modal');
        afterPurchaseDialog(`Тариф успешно активирован на ${days} ${fmt.plural(days, ['день', 'дня', 'дней'])}!`);
    } else {
        alertDialog('Ошибка', res.error, true);
    }
}

async function onBuyDays() {
    haptic('light');
    const price = cfg().dailyPrice;
    const choice = await showDialog({
        title: 'Продление подписки',
        message: `Списать с баланса ${price}₽ для продления на 1 день?`,
        buttons: [
            { id: 'buy', text: 'Купить 1 день', kind: 'primary' },
            { id: 'tariffs', text: 'Тарифы', kind: 'secondary' },
            { id: 'cancel', text: 'Отмена', kind: 'cancel' },
        ],
    });
    if (choice === 'tariffs') return openTariffs();
    if (choice !== 'buy') return;

    if ((state.user?.balance ?? 0) < price) {
        const c = await showDialog({
            title: 'Недостаточно средств',
            message: `На балансе ${fmt.formatMoney(state.user?.balance)} ₽.\nПополните и повторите попытку.`,
            icon: 'error',
            buttons: [
                { id: 'topup', text: 'Пополнить', kind: 'primary' },
                { id: 'close', text: 'Закрыть', kind: 'secondary' },
            ],
        });
        if (c === 'topup') openTopUp();
        return;
    }

    showDialog({ title: 'Продление подписки', message: 'Идёт обработка платежа…', buttons: [] });
    const res = await purchase({ days: 1, price });
    closeModal('dialog-modal');
    if (res.ok) afterPurchaseDialog('Подписка успешно продлена на 1 день!');
    else alertDialog('Ошибка', res.error, true);
}

// ── Devices modal ───────────────────────────────────────────────────────

async function openDevices() {
    openModal('devices-modal');
    els.devicesContent.innerHTML = '<div class="devices-loading">Загрузка...</div>';
    try {
        const d = await api.getDevices();
        setState({ devices: d });
        const total = (d.trafficUp || 0) + (d.trafficDown || 0);
        let html = `
            <div class="devices-status-row">${d.active ? '🟢' : '🔴'} <b>${d.active ? 'Активен' : 'Не активен'}</b></div>
            <div class="devices-info-grid">
                <div class="devices-info-item"><div class="di-label">Последний раз</div><div class="di-value">${fmt.formatLastOnline(d.lastOnline)}</div></div>
                <div class="devices-info-item"><div class="di-label">Загружено</div><div class="di-value">${fmt.formatTraffic(d.trafficUp)}</div></div>
                <div class="devices-info-item"><div class="di-label">Скачано</div><div class="di-value">${fmt.formatTraffic(d.trafficDown)}</div></div>
                <div class="devices-info-item"><div class="di-label">Всего трафика</div><div class="di-value">${fmt.formatTraffic(total)}</div></div>
            </div>`;
        if (d.ips?.length) {
            html += `<div class="devices-ips-label">Подключенные IP:</div><div class="devices-list">${
                d.ips.map((ip, i) => `<div class="device-item"><span class="device-num">${i + 1}.</span>${esc(ip)}</div>`).join('')
            }</div>`;
        }
        els.devicesContent.innerHTML = html;
    } catch {
        els.devicesContent.innerHTML = `
            <div class="devices-empty">Ошибка загрузки</div>
            <button type="button" class="btn-info-link" data-action="open-devices">Повторить</button>`;
    }
}

// ── Trial overlay ───────────────────────────────────────────────────────
let trialHandled = false; // don't re-open during this session after user acted

function maybeShowTrial() {
    if (trialHandled || state.user?.trialUsed) return;
    if (localStorage.getItem('trialDismissed')) return;
    const remindAt = parseInt(localStorage.getItem('trialRemindAt') || '0', 10);
    if (remindAt && Date.now() < remindAt) return;
    openModal('trial-overlay');
}

async function activateTrial() {
    haptic('medium');
    trialHandled = true;
    els.trialBtnActivate.disabled = true;
    els.trialBtnActivate.textContent = 'Активация...';
    const res = await purchase({ days: cfg().trialDays, price: 0 });
    els.trialBtnActivate.disabled = false;
    els.trialBtnActivate.textContent = 'Активировать';
    if (res.ok) {
        closeModal('trial-overlay');
        afterPurchaseDialog('Бесплатный триал активирован на 3 дня!');
    } else {
        alertDialog('Ошибка', res.error || 'Ошибка активации триала', true);
    }
}

function trialRemindLater() {
    trialHandled = true;
    localStorage.setItem('trialRemindAt', String(Date.now() + 86400000));
    closeModal('trial-overlay');
}

function trialCancelConfirm() {
    trialHandled = true;
    if (els.trialDontShow.checked) localStorage.setItem('trialDismissed', '1');
    els.trialCancelDialog.classList.remove('active');
    els.trialModal.style.display = '';
    closeModal('trial-overlay');
}

// ── Tabs ────────────────────────────────────────────────────────────────

function switchTab(tab) {
    for (const name of ['home', 'profile', 'info']) {
        $(`tab-${name}-content`).style.display = name === tab ? 'block' : 'none';
        $(`nav-${name}`).classList.toggle('active', name === tab);
    }
    haptic('light');
}

// ── Misc actions ────────────────────────────────────────────────────────

async function copyReferralLink() {
    const url = state.user?.referralUrl;
    if (!url) return;
    try {
        await navigator.clipboard.writeText(url);
        hapticNotify('success');
        toast('Ссылка скопирована');
    } catch {
        els.refLinkDisplay.textContent = url; // fallback: показать для ручного копирования
    }
}

function showReferralInfo() {
    haptic('light');
    showDialog({
        title: 'Реферальная программа',
        message: `${cfg().referralReward}₽ начисляются после того, как приглашённый друг впервые пополнит баланс.`,
        buttons: [{ id: 'ok', text: 'Понятно', kind: 'primary' }],
    });
}

// ── Action map + delegation ─────────────────────────────────────────────

const actions = {
    'switch-tab': (el) => switchTab(el.dataset.tab),
    'open-topup': () => { haptic('light'); openTopUp(); },
    'open-tariffs': () => { haptic('light'); openTariffs(); },
    'open-devices': () => { haptic('light'); openDevices(); },
    'open-connect': () => { window.location.href = CONNECT_PAGE; },
    'buy-days': () => onBuyDays(),
    'select-amount': (el) => {
        topup.amount = Number(el.dataset.amount);
        els.customAmount.value = '';
        renderTopUp();
    },
    'select-method': (el) => {
        topup.method = el.dataset.method;
        renderTopUp();
    },
    'confirm-topup': () => confirmTopUp(),
    'select-tariff': (el) => {
        state.selection.tariffDays = Number(el.dataset.days);
        renderTariffs();
    },
    'apply-promo': () => applyPromo(),
    'confirm-tariff': () => confirmTariffPurchase(),
    'close-modal': (el) => closeModal(el.dataset.close || el.closest('.modal-overlay')?.id),
    'copy-referral': () => copyReferralLink(),
    'referral-info': () => showReferralInfo(),
    'open-privacy': () => { haptic('light'); openExternal(`${location.origin}/privacy`); },
    'open-terms': () => { haptic('light'); openExternal(`${location.origin}/terms`); },
    'support-tech': () => { haptic('light'); openTelegramLink('https://t.me/Asdzxclop_bot'); },
    'support-online': () => { haptic('light'); openTelegramLink('https://t.me/Judebellengham'); },
    'trial-activate': () => activateTrial(),
    'trial-remind': () => trialRemindLater(),
    'trial-cancel': () => {
        els.trialModal.style.display = 'none';
        els.trialCancelDialog.classList.add('active');
    },
    'trial-cancel-confirm': () => trialCancelConfirm(),
    'trial-cancel-back': () => {
        els.trialCancelDialog.classList.remove('active');
        els.trialModal.style.display = '';
    },
    'retry-load': () => {
        document.body.classList.add('app-loading');
        refresh({ force: true });
    },
};

function bindEvents() {
    document.addEventListener('click', (e) => {
        const el = e.target.closest('[data-action]');
        if (!el) return;
        const fn = actions[el.dataset.action];
        if (fn) fn(el, e);
    });

    els.customAmount.addEventListener('input', () => {
        const val = parseInt(els.customAmount.value, 10);
        topup.amount = val >= cfg().minTopUp ? val : 0;
        renderTopUp();
    });

    els.promoInput.addEventListener('input', () => {
        if (!els.promoInput.value.trim() && state.promo.code) {
            resetPromo();
            renderTariffs();
        }
        setPromoStatus('', '');
    });

    // Keyboard support for div-based tariff options (Enter / Space)
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const el = e.target.closest?.('.tariff-option[data-action]');
        if (el) {
            e.preventDefault();
            actions[el.dataset.action]?.(el, e);
        }
    });

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') refresh();
    });
}

// ── Init ────────────────────────────────────────────────────────────────

function init() {
    initTelegram();
    initTheme();
    initParticles();
    if (!isTelegram) els.devNotice.style.display = 'block';
    document.body.classList.add('app-loading');

    initModals();
    bindEvents();
    subscribe(render);
    render();
    renderTariffs();
    renderTopUp();

    loadConfig();
    refresh({ force: true });
    setInterval(() => {
        if (document.visibilityState === 'visible') refresh();
    }, POLL_INTERVAL);
}

init();
