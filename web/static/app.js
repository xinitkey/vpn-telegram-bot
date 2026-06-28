const tg = window.Telegram?.WebApp || {
    expand: () => {},
    setHeaderColor: () => {},
    initDataUnsafe: { user: { id: 1, first_name: 'Dev', last_name: 'User', username: 'dev' } },
    initData: '',
    sendData: function(data) { console.log('sendData:', data); },
    openLink: (url) => window.open(url, '_blank'),
    openTelegramLink: (url) => window.open(url, '_blank'),
    showPopup: (params, cb) => { if (cb) cb('ok'); },
    showAlert: (msg) => alert(msg),
    HapticFeedback: { impactOccurred: () => {}, notificationOccurred: () => {} },
    ready: () => {}
};
const isBrowser = !tg.initData;
if (isBrowser) {
    document.getElementById('dev-notice').style.display = 'block';
}
if (window.Telegram?.WebApp) {
    tg.expand();
    tg.setHeaderColor('#1f0303');
}

const userId = tg.initDataUnsafe?.user?.id;
const initData = tg.initData || '';
const userRaw = tg.initDataUnsafe?.user;
const workerUrl = window.location.origin;

function formatTs(ts) {
  if (!ts || ts <= 0) return '—';
  const d = new Date(ts);
  const pad = n => String(n).padStart(2, '0');
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function openLink(url) {
  if (window.Telegram?.WebApp?.openLink) {
    window.Telegram.WebApp.openLink(url);
  } else {
    window.open(url, '_blank');
  }
}

function formatLink(url) {
  if (!url || url === 'Не создан') return url || 'Не создан';
  const text = url.length > 60 ? url.slice(0, 57) + '...' : url;
  return `<a href="#" onclick="openLink('${url.replace(/'/g, "\\'")}'); return false;">${text}</a>`;
}

let selectedAmount = 0;
let selectedMethod = '';
let selectedTariffDays = 0;
let selectedTariffPrice = 0;
let globalUserData = { balance: 0, daysLeft: 0, vpnKey: 'Не создан', dailyPrice: 5, trialUsed: false };
let activePromoCode = '';
let activePromoDiscount = 0;
let activePromoTariffPrices = {};

if (userRaw) {
    document.getElementById('user-id').innerText = userRaw.id || "Не определен";
    document.getElementById('user-name').innerText = (userRaw.first_name || "") + " " + (userRaw.last_name || "");
    document.getElementById('user-username').innerText = userRaw.username ? "@" + userRaw.username : "нет никнейма";
    if (userRaw.photo_url) {
        const img = document.getElementById('user-photo');
        img.src = userRaw.photo_url;
        img.style.display = 'block';
        document.getElementById('user-avatar-placeholder').style.display = 'none';
    }
}

async function loadUserData() {
    if (!userId) return;
    try {
        const response = await fetch(workerUrl + "/api/user-data?userId=" + userId, {
            headers: { "X-Init-Data": initData }
        });
        if (response.ok) {
            globalUserData = await response.json();
            // Check ban status
            if (globalUserData.banned) {
                document.getElementById('banned-overlay').classList.add('active');
                document.querySelectorAll('.btn-pay, .btn-primary-action, .btn-confirm').forEach(b => b.disabled = true);
            } else {
                document.getElementById('banned-overlay').classList.remove('active');
            }
            document.getElementById('balance-display').innerText = globalUserData.balance + " ₽";
            document.getElementById('profile-balance').innerText = globalUserData.balance + " ₽";
            document.getElementById('days-count').innerHTML = globalUserData.remainingStr || globalUserData.daysLeft + " <span>дней</span>";
            document.getElementById('profile-key').innerHTML = formatLink(globalUserData.vpnKey);
            document.getElementById('profile-sub-start').innerText = formatTs(globalUserData.subscriptionStart);
            document.getElementById('profile-sub-end').innerText = formatTs(globalUserData.subscriptionEnd);
            document.getElementById('price-daily-text').innerText = globalUserData.dailyPrice + "₽ / день за устройство";
            // Referral
            if (globalUserData.referralUrl) {
                document.getElementById('ref-count').innerText = globalUserData.referralCount || 0;
                document.getElementById('ref-earned').innerText = (globalUserData.referralEarnings || 0) + " ₽";
                window._referralUrl = globalUserData.referralUrl;
            }
            // Trial status — update 3-day tariff pricing
            const trialOpt = document.querySelector('.tariff-option[data-days="3"]');
            if (globalUserData.trialUsed) {
                trialOpt.setAttribute('onclick', "selectTariff(3, 15)");
                trialOpt.setAttribute('data-price', '15');
                trialOpt.querySelector('.tariff-price').innerHTML = '15 &#x20BD;';
                trialOpt.querySelector('.tariff-perday').innerHTML = '5 ₽/день';
            } else {
                trialOpt.setAttribute('onclick', "selectTariff(3, 0)");
                trialOpt.setAttribute('data-price', '0');
                trialOpt.querySelector('.tariff-price').innerHTML = '0 ₽';
                trialOpt.querySelector('.tariff-perday').innerHTML = 'Бесплатно';
            }
        }
    } catch (e) { console.error(e); }
}

function copyReferralLink() {
    const url = window._referralUrl;
    if (!url) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(() => {
            document.getElementById('ref-link-display').innerText = "Ссылка скопирована!";
            setTimeout(() => document.getElementById('ref-link-display').innerText = '', 3000);
        });
    } else {
        document.getElementById('ref-link-display').innerText = url;
    }
    tg.HapticFeedback.notificationOccurred('success');
}

function showReferralInfo(event) {
    tg.showPopup({
        title: "Реферальная программа",
        message: "50₽ начисляются после того, как приглашённый друг впервые пополнит баланс.",
        buttons: [{ type: 'ok', text: "Понятно" }]
    });
}

loadUserData();
setInterval(loadUserData, 10000);

function switchTab(tab) {
    const homeContent = document.getElementById('tab-home-content');
    const profileContent = document.getElementById('tab-profile-content');
    const infoContent = document.getElementById('tab-info-content');
    const navHome = document.getElementById('nav-home');
    const navProfile = document.getElementById('nav-profile');
    const navInfo = document.getElementById('nav-info');

    // Скрываем все
    homeContent.style.display = 'none';
    profileContent.style.display = 'none';
    infoContent.style.display = 'none';
    navHome.classList.remove('active');
    navProfile.classList.remove('active');
    navInfo.classList.remove('active');

    if (tab === 'home') {
        homeContent.style.display = 'block';
        navHome.classList.add('active');
    } else if (tab === 'profile') {
        profileContent.style.display = 'block';
        navProfile.classList.add('active');
    } else if (tab === 'info') {
        infoContent.style.display = 'block';
        navInfo.classList.add('active');
    }
}

function showSubscriptionInfo() {
    tg.HapticFeedback.impactOccurred('light');
    const status = globalUserData.daysLeft > 0 ? "АКТИВНА" : "НЕ АКТИВНА";
    const key = globalUserData.vpnKey;
    const infoMessage =
        "Статус: " + status + "\n" +
        "Осталось: " + (globalUserData.remainingStr || globalUserData.daysLeft + " дн.") + "\n" +
        "Начало: " + formatTs(globalUserData.subscriptionStart) + "\n" +
        "Заканчивается: " + formatTs(globalUserData.subscriptionEnd);

    const buttons = [{ type: 'ok', text: "Отлично" }];
    if (key && key !== 'Не создан') {
        buttons.unshift({ type: 'default', id: 'open_key', text: "Открыть ключ" });
    }

    tg.showPopup({
        title: "Характеристика подписки",
        message: infoMessage,
        buttons: buttons
    }, function(buttonId) {
        if (buttonId === 'open_key') openLink(key);
    });
}

function buyDaysModal() {
    tg.showPopup({
        title: "Продление подписки",
        message: "Списать с баланса средства для продления подписки на 1 день (" + globalUserData.dailyPrice + "₽)?",
        buttons: [{ type: 'ok', id: 'buy_sub', text: 'Купить 1 день' }, { type: 'cancel', text: 'Отмена' }]
    }, async (buttonId) => {
        if (buttonId === 'buy_sub') {
            if (globalUserData.balance < globalUserData.dailyPrice) {
                tg.showAlert("Недостаточно средств. Пополните ваш баланс.");
                return;
            }
            try {
                const res = await fetch(workerUrl + "/api/buy-subscription", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ userId, days: 1, initData })
                });
                if (res.ok) {
                    tg.HapticFeedback.notificationOccurred('success');
                    tg.showAlert("Подписка успешно продлена на 1 день!");
                    loadUserData();
                } else {
            const text = await response.text();
                    let errData;
                    try { errData = JSON.parse(text); } catch { errData = { error: text }; }
                    tg.showAlert(errData.error || "Ошибка проведения платежа");
                }
            } catch {
                tg.showAlert("Сбой сети.");
            }
        }
    });
}

function openTopUpModal() {
    document.getElementById('topup-modal').classList.add('active');
    selectedAmount = 0;
    selectedMethod = '';
    document.getElementById('custom-amount').value = '';
    document.querySelectorAll('.amount-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.method-btn').forEach(b => b.classList.remove('active'));
    updateConfirmButton();
}

function closeTopUpModal() {
    document.getElementById('topup-modal').classList.remove('active');
}

function selectAmount(amount) {
    selectedAmount = amount;
    document.getElementById('custom-amount').value = '';
    document.querySelectorAll('.amount-btn').forEach(b => {
        b.classList.toggle('active', parseInt(b.textContent) === amount);
    });
    updateConfirmButton();
}

function onCustomAmount() {
    const val = parseInt(document.getElementById('custom-amount').value);
    if (val >= 50) {
        selectedAmount = val;
        document.querySelectorAll('.amount-btn').forEach(b => b.classList.remove('active'));
    } else {
        selectedAmount = 0;
    }
    updateConfirmButton();
}

function selectMethod(method) {
    selectedMethod = method;
    document.querySelectorAll('.method-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('method-' + method).classList.add('active');
    updateConfirmButton();
}

function updateConfirmButton() {
    const btn = document.getElementById('btn-confirm-topup');
    btn.disabled = !(selectedAmount >= 50 && selectedMethod);
    if (selectedAmount >= 50 && selectedMethod) {
        btn.innerText = "Пополнить на " + selectedAmount + " ₽";
    } else {
        btn.innerText = 'Пополнить';
    }
}

async function confirmTopUp() {
    if (selectedAmount < 50 || !selectedMethod) return;
    tg.HapticFeedback.impactOccurred('medium');

    const btn = document.getElementById('btn-confirm-topup');
    const originalText = btn.innerText;
    btn.disabled = true;
    btn.innerText = 'Создание счёта...';

    const body = { userId, amount: selectedAmount, method: selectedMethod, initData };
    const pm = { platega_sbp: 2, platega_crypto: 13 }[selectedMethod];
    if (pm) body.paymentMethod = pm;

    try {
        const response = await fetch(workerUrl + "/api/create-payment", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });

        if (response.ok) {
            const data = await response.json();
            closeTopUpModal();

            if (data.paymentUrl) {
                tg.openLink(data.paymentUrl);
            }
        } else {
            const text = await response.text();
            let errData;
            try { errData = JSON.parse(text); } catch { errData = { error: text }; }
            tg.showAlert(errData.error || "Не удалось сформировать счет на оплату.");
        }
    } catch {
        tg.showAlert("Произошла ошибка при соединении с сервером.");
    } finally {
        btn.disabled = false;
        btn.innerText = originalText;
    }
}

function openDevices() {
    tg.showPopup({ title: "Устройства", message: "Раздел находится в разработке", buttons: [{type: 'ok'}] });
}
function openInstructions() {
    tg.showPopup({ title: "Инструкция", message: "Выберите и установите приложение из списка поддерживаемых и перейдите по ссылке для копирования или подключения ключа", buttons: [{type: 'ok'}] });
}
function openPrivacyPage() {
    tg.HapticFeedback.impactOccurred('light');
    tg.openLink(workerUrl + "/privacy");
}
function openTermsPage() {
    tg.HapticFeedback.impactOccurred('light');
    tg.openLink(workerUrl + "/terms");
}
function openSupportTech() {
    tg.HapticFeedback.impactOccurred('light');
    tg.openTelegramLink("https://t.me/Asdzxclop_bot");
}
function openSupportOnline() {
    tg.HapticFeedback.impactOccurred('light');
    tg.openTelegramLink("https://t.me/Judebellengham");
}

function openTariffsModal() {
    document.getElementById('tariffs-modal').classList.add('active');
    selectedTariffDays = 0;
    selectedTariffPrice = 0;
    document.querySelectorAll('.tariff-option').forEach(b => b.classList.remove('active'));
    document.getElementById('btn-confirm-tariff').disabled = true;
    document.getElementById('btn-confirm-tariff').innerText = 'Выберите тариф';
    document.getElementById('promo-input').value = '';
    document.getElementById('promo-status').innerHTML = '';
    document.getElementById('promo-status').className = 'promo-status';
    document.getElementById('promo-btn').disabled = false;
    if (activePromoCode) {
        document.getElementById('promo-input').value = activePromoCode;
        applyPromoCode(true);
    }
}

function onPromoInput() {
    const status = document.getElementById('promo-status');
    status.innerHTML = '';
    status.className = 'promo-status';
}

async function applyPromoCode(silent) {
    const code = document.getElementById('promo-input').value.trim();
    const btn = document.getElementById('promo-btn');
    const status = document.getElementById('promo-status');
    if (!code) {
        clearPromoCode();
        return;
    }
    if (!silent) tg.HapticFeedback.impactOccurred('light');
    btn.disabled = true;
    btn.innerText = 'Проверка...';
    try {
        const res = await fetch(workerUrl + '/api/apply-promo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        const data = await res.json();
        if (res.ok && data.valid) {
            activePromoCode = code;
            activePromoDiscount = data.discountPercent;
            activePromoTariffPrices = data.tariffPrices || {};
            status.className = 'promo-status promo-success';
            status.innerHTML = 'Промокод применён! Скидка ' + data.discountPercent + '%';
            updateTariffPrices(data);
        } else {
            clearPromoCode();
            status.className = 'promo-status promo-error';
            status.innerHTML = data.error || 'Промокод недействителен';
        }
    } catch {
        clearPromoCode();
        status.className = 'promo-status promo-error';
        status.innerHTML = 'Ошибка проверки промокода';
    } finally {
        btn.disabled = false;
        btn.innerText = 'Применить';
    }
}

function clearPromoCode() {
    activePromoCode = '';
    activePromoDiscount = 0;
    activePromoTariffPrices = {};
    document.querySelectorAll('.tariff-option').forEach(el => {
        const origPrice = parseInt(el.getAttribute('data-price'));
        el.querySelector('.tariff-price').innerHTML = origPrice + ' &#x20BD;';
    });
}

function updateTariffPrices(data) {
    const prices = data.tariffPrices || {};
    document.querySelectorAll('.tariff-option').forEach(el => {
        const days = parseInt(el.getAttribute('data-days'));
        const origPrice = parseInt(el.getAttribute('data-price'));
        const isFreeTrial = days === 3 && !globalUserData.trialUsed;
        let discountInfo = null;
        if (!isFreeTrial) {
            for (const idx in prices) {
                if (prices[idx].days === days) {
                    discountInfo = prices[idx];
                    break;
                }
            }
        }
        const priceEl = el.querySelector('.tariff-price');
        if (discountInfo && discountInfo.discounted < origPrice) {
            priceEl.innerHTML = '<span class="old-price">' + origPrice + ' &#x20BD;</span> <span class="discount-price">' + discountInfo.discounted + ' &#x20BD;</span>';
        } else {
            priceEl.innerHTML = origPrice + ' &#x20BD;';
        }
    });
    // Re-select the currently selected tariff to update button text
    if (selectedTariffDays) {
        const origPrice = parseInt(document.querySelector('.tariff-option.active')?.getAttribute('data-price') || '0');
        const days = selectedTariffDays;
        const isFreeTrial = days === 3 && !globalUserData.trialUsed;
        let discounted = null;
        if (!isFreeTrial) {
            for (const idx in prices) {
                if (prices[idx].days === days) {
                    discounted = prices[idx].discounted;
                    break;
                }
            }
        }
        if (discounted !== null && discounted < origPrice) {
            selectedTariffPrice = discounted;
            const btn = document.getElementById('btn-confirm-tariff');
            btn.innerText = 'Купить за ' + discounted + ' &#x20BD;';
        }
    }
}

function closeTariffsModal() {
    document.getElementById('tariffs-modal').classList.remove('active');
}

function selectTariff(days, price) {
    selectedTariffDays = days;
    // Check if promo discount applies (skip for free trial)
    let finalPrice = price;
    const isFreeTrial = days === 3 && !globalUserData.trialUsed;
    if (activePromoCode && activePromoDiscount > 0 && !isFreeTrial) {
        for (const idx in activePromoTariffPrices) {
            if (activePromoTariffPrices[idx].days === days) {
                finalPrice = activePromoTariffPrices[idx].discounted;
                break;
            }
        }
    }
    selectedTariffPrice = finalPrice;
    document.querySelectorAll('.tariff-option').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tariff-option').forEach(b => {
        if (parseInt(b.getAttribute('data-days')) === days) {
            b.classList.add('active');
        }
    });
    const btn = document.getElementById('btn-confirm-tariff');
    btn.disabled = false;
    btn.innerText = finalPrice === 0 ? 'Активировать триал' : 'Купить за ' + finalPrice + ' ₽';
}

async function confirmTariffPurchase() {
    if (!selectedTariffDays || selectedTariffPrice === undefined) return;
    tg.HapticFeedback.impactOccurred('medium');

    if (selectedTariffPrice > 0 && globalUserData.balance < selectedTariffPrice) {
        tg.showPopup({
            title: "Недостаточно средств",
            message: "На балансе " + globalUserData.balance + " ₽. Нужно " + selectedTariffPrice + " ₽.\nПополните баланс и повторите попытку.",
            buttons: [{ type: 'ok', text: "Пополнить" }]
        });
        closeTariffsModal();
        openTopUpModal();
        return;
    }

    const btn = document.getElementById('btn-confirm-tariff');
    const originalText = btn.innerText;
    btn.disabled = true;
    btn.innerText = 'Обработка...';

    const body = { userId, days: selectedTariffDays, price: selectedTariffPrice, initData };
    if (activePromoCode) body.promoCode = activePromoCode;

    try {
        const res = await fetch(workerUrl + "/api/buy-subscription", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });

        if (res.ok) {
            tg.HapticFeedback.notificationOccurred('success');
            tg.showAlert("Тариф успешно активирован на " + selectedTariffDays + " дней!");
            closeTariffsModal();
            loadUserData();
        } else {
            const text = await res.text();
            let errData;
            try { errData = JSON.parse(text); } catch { errData = { error: text }; }
            tg.showAlert(errData.error || "Ошибка при покупке тарифа");
        }
    } catch {
        tg.showAlert("Сбой сети.");
    } finally {
        btn.disabled = false;
        btn.innerText = originalText;
    }
}