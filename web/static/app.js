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
let globalUserData = { balance: 0, daysLeft: 0, vpnKey: 'Не создан', dailyPrice: 6, trialUsed: false };
let activePromoCode = '';
let activePromoDiscount = 0;
let activePromoTariffPrices = {};
let hideKey = true;

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
            document.getElementById('balance-display').textContent = globalUserData.balance;
            var now = Date.now();
            var remaining = globalUserData.subscriptionEnd - now;
            var daysEl = document.getElementById('days-count');
            var lblEl = document.querySelector('.days-lbl');
            if (remaining <= 0) {
                daysEl.textContent = '0';
                lblEl.textContent = 'дн.';
            } else if (remaining >= 86400000) {
                daysEl.textContent = Math.floor(remaining / 86400000);
                lblEl.textContent = 'дн.';
            } else if (remaining >= 3600000) {
                daysEl.textContent = Math.floor(remaining / 3600000);
                lblEl.textContent = 'ч';
            } else {
                daysEl.textContent = Math.floor(remaining / 60000);
                lblEl.textContent = 'мин';
            }
            document.getElementById('profile-balance').innerText = globalUserData.balance + " ₽";
            document.getElementById('home-username').textContent = (userRaw?.username ? "@" + userRaw.username : globalUserData.username) || "—";
            document.getElementById('home-expiry').textContent = formatTs(globalUserData.subscriptionEnd);
            fetch(workerUrl + "/api/user-devices?userId=" + userId, { headers: { "X-Init-Data": initData } })
                .then(function(r){ return r.json(); })
                .then(function(d){
                    var total = (d.trafficUp || 0) + (d.trafficDown || 0);
                    document.getElementById('home-traffic').textContent = formatTraffic(total);
                })
                .catch(function(){});
            var sb = document.getElementById('statusBadge');
            if (globalUserData.daysLeft > 30) { sb.textContent = '\u25CF Активна'; sb.className = 'badge b-active'; }
            else if (globalUserData.daysLeft > 7) { sb.textContent = '\u25CF Активна'; sb.className = 'badge b-active'; }
            else if (globalUserData.daysLeft > 0) { sb.textContent = '\u25CF Скоро истекает'; sb.className = 'badge b-expiring'; }
            else if (globalUserData.subscriptionEnd && globalUserData.subscriptionEnd > now) { sb.textContent = '\u25CF Скоро истекает'; sb.className = 'badge b-expiring'; }
            else if (globalUserData.subscriptionEnd && globalUserData.subscriptionEnd > 0) { sb.textContent = '\u25CF Истекла'; sb.className = 'badge b-inactive'; }
            else { sb.textContent = '\u25CF Нет подписки'; sb.className = 'badge b-inactive'; }
            const keyRow = document.getElementById('profile-key-row');
            const keyValue = document.getElementById('profile-key-value');
            if (globalUserData.vpnKey && globalUserData.vpnKey !== 'Не создан') {
                keyRow.style.display = '';
                keyValue.dataset.key = globalUserData.vpnKey;
                keyValue.innerText = hideKey ? '•'.repeat(20) : globalUserData.vpnKey;
                keyValue.classList.toggle('key-hidden', hideKey);
                
                keyValue.classList.toggle('key-hidden', hideKey);
                document.getElementById('key-toggle-btn').innerText = hideKey ? 'показать' : 'скрыть';
            } else {
                keyRow.style.display = 'none';
            }
            document.getElementById('profile-sub-start').innerText = formatTs(globalUserData.subscriptionStart);
            document.getElementById('profile-sub-end').innerText = formatTs(globalUserData.subscriptionEnd);
            document.getElementById('price-daily-text').innerText = globalUserData.dailyPrice + "₽ / день";
            // Referral
            if (globalUserData.referralUrl) {
                document.getElementById('ref-count').innerText = globalUserData.referralCount || 0;
                document.getElementById('ref-earned').innerText = (globalUserData.referralEarnings || 0) + " ₽";
                window._referralUrl = globalUserData.referralUrl;
            }
            // Trial status — update 3-day tariff pricing
            const trialOpt = document.querySelector('.tariff-option[data-days="3"]');
            if (globalUserData.trialUsed) {
                trialOpt.setAttribute('onclick', "selectTariff(3, 18)");
                trialOpt.setAttribute('data-price', '18');
                trialOpt.querySelector('.tariff-price').innerHTML = '18 &#x20BD;';
                trialOpt.querySelector('.tariff-perday').innerHTML = '6 ₽/день';
            } else {
                trialOpt.setAttribute('onclick', "selectTariff(3, 0)");
                trialOpt.setAttribute('data-price', '0');
                trialOpt.querySelector('.tariff-price').innerHTML = '0 &#x20BD;';
                trialOpt.querySelector('.tariff-perday').innerHTML = 'Бесплатно';
            }
            checkTrialOffer();
        }
    } catch (e) { console.error(e); }
}

function checkTrialOffer() {
    if (globalUserData.trialUsed) return;
    if (localStorage.getItem('trialDismissed')) return;
    var remindAt = localStorage.getItem('trialRemindAt');
    if (remindAt && Date.now() < parseInt(remindAt)) return;
    document.getElementById('trial-overlay').classList.add('active');
}

function activateTrial() {
    tg.HapticFeedback.impactOccurred('medium');
    document.getElementById('trial-btn-activate').disabled = true;
    document.getElementById('trial-btn-activate').textContent = 'Активация...';
    fetch(workerUrl + '/api/buy-subscription', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId, days: 3, price: 0, initData })
    })
    .then(function(r){ return r.json(); })
    .then(function(data){
        if (data.success) {
            tg.HapticFeedback.notificationOccurred('success');
            document.getElementById('trial-overlay').classList.remove('active');
            loadUserData();
        } else {
            tg.showAlert(data.error || 'Ошибка активации триала');
            document.getElementById('trial-btn-activate').disabled = false;
            document.getElementById('trial-btn-activate').textContent = 'Активировать';
        }
    })
    .catch(function(){
        tg.showAlert('Сбой сети');
        document.getElementById('trial-btn-activate').disabled = false;
        document.getElementById('trial-btn-activate').textContent = 'Активировать';
    });
}

function trialRemindLater() {
    localStorage.setItem('trialRemindAt', Date.now() + 86400000);
    document.getElementById('trial-overlay').classList.remove('active');
}

function trialCancel() {
    document.getElementById('trial-modal').style.display = 'none';
    document.getElementById('trial-cancel-dialog').classList.add('active');
}

function trialCancelConfirm() {
    if (document.getElementById('trial-dont-show').checked) {
        localStorage.setItem('trialDismissed', '1');
    }
    document.getElementById('trial-overlay').classList.remove('active');
    document.getElementById('trial-cancel-dialog').classList.remove('active');
    document.getElementById('trial-modal').style.display = '';
}

function trialCancelBack() {
    document.getElementById('trial-cancel-dialog').classList.remove('active');
    document.getElementById('trial-modal').style.display = '';
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

function toggleKeyVisibility() {
    hideKey = !hideKey;
    const el = document.getElementById('profile-key-value');
    const btn = document.getElementById('key-toggle-btn');
    if (hideKey) {
        el.innerText = '•'.repeat(20);
        el.classList.add('key-hidden');
        btn.innerText = 'показать';
    } else {
        el.innerText = el.dataset.key || globalUserData.vpnKey;
        el.classList.remove('key-hidden');
        btn.innerText = 'скрыть';
    }
}

function copyKey() {
    const key = globalUserData.vpnKey;
    if (!key || key === 'Не создан') return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(key).then(() => {
            tg.HapticFeedback.notificationOccurred('success');
            tg.showAlert('Ключ скопирован');
        });
    }
}

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

// ── CUSTOM MODALS ──────────────────────────────────────────────────────
function showConfirmModal(title, message, buttons) {
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').textContent = message;
    var container = document.getElementById('confirm-buttons');
    container.innerHTML = '';
    buttons.forEach(function(b) {
        var btn = document.createElement('button');
        btn.textContent = b.text;
        var cls = 'custom-modal-btn';
        if (b.primary) cls += ' custom-modal-btn-primary';
        else if (b.cancel) cls += ' custom-modal-btn-cancel';
        else cls += ' custom-modal-btn-secondary';
        btn.className = cls;
        btn.onclick = function() {
            closeConfirmModal();
            if (b.onClick) b.onClick();
        };
        container.appendChild(btn);
    });
    document.getElementById('confirm-modal').classList.add('active');
}
function closeConfirmModal() {
    document.getElementById('confirm-modal').classList.remove('active');
}

function showAlertModal(title, message, buttons, isError) {
    document.getElementById('alert-title').textContent = title;
    document.getElementById('alert-message').textContent = message;
    var icon = document.getElementById('alert-icon');
    if (isError) {
        icon.innerHTML = '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#e74c3c" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
    } else {
        icon.innerHTML = '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#27ae60" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>';
    }
    var container = document.getElementById('alert-buttons');
    container.innerHTML = '';
    buttons.forEach(function(b) {
        var btn = document.createElement('button');
        btn.textContent = b.text;
        var cls = 'custom-modal-btn';
        if (b.primary) cls += ' custom-modal-btn-primary';
        else cls += ' custom-modal-btn-secondary';
        btn.className = cls;
        btn.onclick = function() {
            closeAlertModal();
            if (b.onClick) b.onClick();
        };
        container.appendChild(btn);
    });
    document.getElementById('alert-modal').classList.add('active');
}
function closeAlertModal() {
    document.getElementById('alert-modal').classList.remove('active');
}

function buyDaysModal() {
    showConfirmModal(
        "Продление подписки",
        "Списать с баланса " + globalUserData.dailyPrice + "₽ для продления на 1 день?",
        [
            { text: "Купить 1 день", primary: true, onClick: async function() {
                if (globalUserData.balance < globalUserData.dailyPrice) {
                    showAlertModal(
                        "Недостаточно средств",
                        "На балансе " + globalUserData.balance + " ₽.\nПополните и повторите попытку.",
                        [{ text: "Пополнить", primary: true, onClick: function() { openTopUpModal(); } }],
                        true
                    );
                    return;
                }
                try {
                    const res = await fetch(workerUrl + "/api/buy-subscription", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ userId, days: 1, price: globalUserData.dailyPrice, initData })
                    });
                    if (res.ok) {
                        tg.HapticFeedback.notificationOccurred('success');
                        loadUserData();
                        showAlertModal(
                            "Подписка продлена",
                            "Подписка успешно продлена на 1 день!",
                            [
                                { text: "Перейти к подключению", primary: true, onClick: function() { window.location.href = '/blackvpn-connect.html'; } },
                                { text: "Закрыть" }
                            ]
                        );
                    } else {
                        const text = await res.text();
                        let errData;
                        try { errData = JSON.parse(text); } catch { errData = { error: text }; }
                        showAlertModal("Ошибка", errData.error || "Ошибка проведения платежа", [{ text: "Закрыть" }], true);
                    }
                } catch {
                    showAlertModal("Ошибка", "Сбой сети.", [{ text: "Закрыть" }], true);
                }
            }},
            { text: "Тарифы", onClick: function() { openTariffsModal(); } },
            { text: "Отмена", cancel: true }
        ]
    );
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

function formatTraffic(bytes) {
    if (!bytes || bytes <= 0) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
    return (bytes / 1073741824).toFixed(2) + ' GB';
}

function formatLastOnline(ts) {
    if (!ts || ts <= 0) return '—';
    const d = new Date(ts);
    const now = Date.now();
    const diff = now - d.getTime();
    if (diff < 60000) return 'только что';
    if (diff < 3600000) return Math.floor(diff / 60000) + ' мин. назад';
    if (diff < 86400000) return Math.floor(diff / 3600000) + ' ч. назад';
    return formatTs(ts);
}

function openDevices() {
    document.getElementById('devices-modal').classList.add('active');
    const container = document.getElementById('devices-content');
    container.innerHTML = '<div class="devices-loading">Загрузка...</div>';
    fetch(workerUrl + "/api/user-devices?userId=" + userId, {
        headers: { "X-Init-Data": initData }
    })
    .then(r => r.json())
    .then(data => {
        const activeIcon = data.active ? '🟢' : '🔴';
        const activeText = data.active ? 'Активен' : 'Не активен';
        const totalTraffic = (data.trafficUp || 0) + (data.trafficDown || 0);
        let html = '<div class="devices-status-row"><span class="devices-status-icon">' + activeIcon + '</span> <b>' + activeText + '</b></div>';
        html += '<div class="devices-info-grid">';
        html += '<div class="devices-info-item"><div class="di-label">Последний раз</div><div class="di-value">' + formatLastOnline(data.lastOnline) + '</div></div>';
        html += '<div class="devices-info-item"><div class="di-label">Загружено</div><div class="di-value">' + formatTraffic(data.trafficUp) + '</div></div>';
        html += '<div class="devices-info-item"><div class="di-label">Скачано</div><div class="di-value">' + formatTraffic(data.trafficDown) + '</div></div>';
        html += '<div class="devices-info-item"><div class="di-label">Всего трафика</div><div class="di-value">' + formatTraffic(totalTraffic) + '</div></div>';
        html += '</div>';
        if (data.ips && data.ips.length > 0) {
            html += '<div class="devices-ips-label">Подключенные IP:</div><div class="devices-list">';
            data.ips.forEach((ip, i) => {
                html += '<div class="device-item"><span class="device-num">' + (i + 1) + '.</span> ' + ip + '</div>';
            });
            html += '</div>';
        }
        container.innerHTML = html;
    })
    .catch(() => {
        container.innerHTML = '<div class="devices-empty">Ошибка загрузки</div>';
    });
}

function closeDevicesModal() {
    document.getElementById('devices-modal').classList.remove('active');
}
function openInstructions() {
    window.location.href = '/blackvpn-connect.html';
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
            body: JSON.stringify({ code, userId, initData })
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
        showAlertModal(
            "Недостаточно средств",
            "На балансе " + globalUserData.balance + " ₽. Нужно " + selectedTariffPrice + " ₽.\nПополните баланс и повторите попытку.",
            [{ text: "Пополнить", primary: true, onClick: function() { closeTariffsModal(); openTopUpModal(); } }],
            true
        );
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
            clearPromoCode();
            closeTariffsModal();
            loadUserData();
            showAlertModal(
                "Тариф активирован",
                "Тариф успешно активирован на " + selectedTariffDays + " дней!",
                [
                    { text: "Перейти к подключению", primary: true, onClick: function() { window.location.href = '/blackvpn-connect.html'; } },
                    { text: "Закрыть" }
                ]
            );
        } else {
            const text = await res.text();
            let errData;
            try { errData = JSON.parse(text); } catch { errData = { error: text }; }
            showAlertModal("Ошибка", errData.error || "Ошибка при покупке тарифа", [{ text: "Закрыть" }], true);
        }
    } catch {
        showAlertModal("Ошибка", "Сбой сети.", [{ text: "Закрыть" }], true);
    } finally {
        btn.disabled = false;
        btn.innerText = originalText;
    }
}
