const tg = window.Telegram.WebApp;
tg.expand();
tg.setHeaderColor('#1f0303');

const userId = tg.initDataUnsafe?.user?.id;
const initData = tg.initData || '';
const userRaw = tg.initDataUnsafe?.user;
const workerUrl = window.location.origin;

let selectedAmount = 0;
let selectedMethod = '';
let selectedTariffDays = 0;
let selectedTariffPrice = 0;
let globalUserData = { balance: 0, daysLeft: 0, vpnKey: 'Не создан', dailyPrice: 5 };

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
            document.getElementById('balance-display').innerText = globalUserData.balance + " ₽";
            document.getElementById('profile-balance').innerText = globalUserData.balance + " ₽";
            document.getElementById('days-count').innerHTML = globalUserData.daysLeft + " <span>дней</span>";
            document.getElementById('profile-key').innerText = globalUserData.vpnKey;
            document.getElementById('price-daily-text').innerText = globalUserData.dailyPrice + "₽ / день за устройство";
        }
    } catch (e) { console.error(e); }
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
    const status = globalUserData.daysLeft > 0 ? "🟢 АКТИВНА" : "🔴 НЕ АКТИВНА";
    const infoMessage =
        "Статус: " + status + "\n" +
        "Осталось дней: " + globalUserData.daysLeft + " дн.\n" +
        "Текущий тариф: " + globalUserData.dailyPrice + " ₽ / сутки\n\n" +
        "Ваш ключ доступа:\n\n" + globalUserData.vpnKey;

    tg.showPopup({
        title: "Характеристика подписки",
        message: infoMessage,
        buttons: [{ type: 'ok', text: "Отлично" }]
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
                    const text = await res.text();
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

    try {
        const response = await fetch(workerUrl + "/api/create-payment", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ userId, amount: selectedAmount, method: selectedMethod, initData })
        });

        if (response.ok) {
            const data = await response.json();
            closeTopUpModal();

            if (selectedMethod === 'stars') {
                tg.sendData(JSON.stringify({ action: "create_payment", amount: selectedAmount, method: selectedMethod }));
                tg.close();
            } else if (data.paymentUrl) {
                tg.openLink(data.paymentUrl);
            }
        } else {
            tg.showAlert("Не удалось сформировать счет на оплату.");
        }
    } catch {
        tg.showAlert("Произошла ошибка при соединении с сервером.");
    }
}

function openDevices() {
    tg.showPopup({ title: "Устройства", message: "Раздел находится в разработке", buttons: [{type: 'ok'}] });
}
function openInstructions() {
    tg.showPopup({ title: "Инструкция", message: "Скопируйте ваш VLESS-ключ из вкладки Профиль и вставьте в клиент (v2rayNG, NekoBox или Amnezia)", buttons: [{type: 'ok'}] });
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
}

function closeTariffsModal() {
    document.getElementById('tariffs-modal').classList.remove('active');
}

function selectTariff(days, price) {
    selectedTariffDays = days;
    selectedTariffPrice = price;
    document.querySelectorAll('.tariff-option').forEach(b => b.classList.remove('active'));
    // Find and highlight the clicked option
    document.querySelectorAll('.tariff-option').forEach(b => {
        if (parseInt(b.getAttribute('onclick').match(/selectTariff\((\d+)/)?.[1]) === days) {
            b.classList.add('active');
        }
    });
    const btn = document.getElementById('btn-confirm-tariff');
    btn.disabled = false;
    btn.innerText = 'Купить за ' + price + ' ₽';
}

async function confirmTariffPurchase() {
    if (!selectedTariffDays || !selectedTariffPrice) return;
    tg.HapticFeedback.impactOccurred('medium');

    if (globalUserData.balance < selectedTariffPrice) {
        tg.showPopup({
            title: "Недостаточно средств",
            message: "На балансе " + globalUserData.balance + " ₽. Нужно " + selectedTariffPrice + " ₽.\nПополните баланс и повторите попытку.",
            buttons: [{ type: 'ok', text: "Пополнить" }]
        });
        closeTariffsModal();
        openTopUpModal();
        return;
    }

    try {
        const res = await fetch(workerUrl + "/api/buy-subscription", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ userId, days: selectedTariffDays, price: selectedTariffPrice, initData })
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
    }
}