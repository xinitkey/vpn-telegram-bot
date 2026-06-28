from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, LabeledPrice, PreCheckoutQuery
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram import Dispatcher
from config import settings
from services.db import add_balance, create_payment as db_create_payment, get_payment, update_payment_status, get_user, create_user
from models.user import _base36_decode
import json
import logging

router = Router()
logger = logging.getLogger(__name__)

APPS_STORE = {
    "iphone": (
        "<b>Приложения для iPhone / iPad:</b>\n\n"
        "• Happ — https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973 (рекомендуется)\n"
        "• Incy — https://apps.apple.com/us/app/incy/id6756943388\n"
        "• Hiddify — https://apps.apple.com/app/hiddify-proxy/id6596777532\n"
        "• sing-box VT — https://apps.apple.com/ru/app/sing-box-vt/id6673731168\n"
        "  (App Store, не TestFlight! Profiles → Remote → URL подписки)\n"
        "• DefaultVPN — https://apps.apple.com/ru/app/defaultvpn/id6744725017\n"
        "  (+ → Insert → vless-ключ; при необходимости включите Use VLESS protocol)\n"
        "• V2RayTun — https://apps.apple.com/app/v2raytun/id6476628951\n"
        "• Streisand — https://apps.apple.com/app/streisand/id6450534064\n"
        "• Amnezia VPN — https://apps.apple.com/app/amnezia-vpn/id1600529900"
    ),
    "android": (
        "<b>Приложения для Android:</b>\n\n"
        "• Happ — https://play.google.com/store/apps/details?id=com.happproxy (рекомендуется)\n"
        "• Incy — https://play.google.com/store/apps/details?id=llc.itdev.incy&hl=ru\n"
        "• Hiddify — https://play.google.com/store/apps/details?id=app.hiddify.com\n"
        "• Amnezia VPN — https://play.google.com/store/apps/details?id=org.amnezia.vpn\n"
        "• NekoBox — https://github.com/MatsuriDayo/NekoBoxForAndroid/releases\n"
        "• Sing-box — https://play.google.com/store/apps/details?id=io.nekohasekai.sfa"
    ),
    "computer": (
        "<b>Приложения для компьютера (Windows / macOS / Linux):</b>\n\n"
        "• Happ — https://github.com/Happ-proxy/happ-desktop/releases (рекомендуется)\n"
        "• Incy — https://github.com/INCY-DEV/incy-platforms/releases\n"
        "• Hiddify — https://github.com/hiddify/hiddify-app/releases\n"
        "• Amnezia VPN — https://amnezia.org/downloads\n"
        "• Nekoray — https://github.com/MatsuriDayo/nekoray/releases"
    ),
}

PLATFORM_BUTTONS = [
    ("iphone", "IOS"),
    ("android", "Android"),
    ("computer", "PC"),
]

_APPS_SEP = "\n\n---\n\n"


def _platform_keyboard(selected: str = None):
    buttons = []
    for key, label in PLATFORM_BUTTONS:
        text = f"✅ {label}" if selected == key else label
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"platform_{key}")])
    buttons.append([InlineKeyboardButton(text="🚀 Открыть BlackVPN App", web_app=WebAppInfo(url=f"{settings.BASE_URL}/"))])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def send_key_with_platforms(bot, chat_id: int, key: str, remaining_str: str):
    header = (
        f"<b>Тариф успешно активирован!</b>\n\n"
        f"<b>Ваш ключ:</b>\n"
        f"{key}\n\n"
        f"<b>Осталось:</b> {remaining_str}\n\n"
        f"<b>Инструкция:</b> Выберите и установите приложение из списка "
        f"поддерживаемых и перейдите по ссылке для копирования или подключения ключа\n\n"
        f"<b>Выберите платформу:</b>"
    )
    await bot.send_message(
        chat_id,
        header,
        reply_markup=_platform_keyboard(),
        parse_mode='HTML'
    )


@router.callback_query(F.data.startswith("platform_"))
async def cb_platform(callback: CallbackQuery):
    await callback.answer()
    platform = callback.data[len("platform_"):]
    apps_text = APPS_STORE.get(platform)
    if not apps_text:
        return
    message_text = callback.message.text or ""
    base = message_text.split(_APPS_SEP)[0] if _APPS_SEP in message_text else message_text
    await callback.message.edit_text(
        base + _APPS_SEP + apps_text,
        reply_markup=_platform_keyboard(selected=platform),
        parse_mode='HTML',
        disable_web_page_preview=True,
    )


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject = None):
    user = await get_user(message.from_user.id)
    if user and user.banned:
        await message.answer("Вы заблокированы.")
        return

    referred_by = None
    arg = command.args if command else None
    if arg and arg.startswith('ref_'):
        try:
            ref_code = arg[4:]
            referred_id = _base36_decode(ref_code)
            if referred_id and referred_id != message.from_user.id:
                referred_by = referred_id
        except (ValueError, IndexError):
            pass

    if not user:
        await create_user(message.from_user.id, referred_by=referred_by)
    elif referred_by and not user.referred_by:
        from services.db import _get_db, _db_lock
        async with _db_lock:
            db = await _get_db()
            await db.execute('UPDATE users SET referred_by = ? WHERE user_id = ?', (referred_by, message.from_user.id))
            await db.commit()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть BlackVPN App", web_app=WebAppInfo(url=f"{settings.BASE_URL}/"))]
    ])
    await message.answer(
        f"Добро пожаловать в <b>BlackVPN</b>!\n"
        f"Ваш ID: <code>{message.from_user.id}</code>\n"
        f"Нажмите кнопку ниже, чтобы открыть приложение управления VPN:",
        reply_markup=keyboard,
        parse_mode='HTML'
    )


@router.message(Command('referral'))
async def cmd_referral(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await create_user(message.from_user.id)
        user = await get_user(message.from_user.id)

    from services.db import get_referral_stats
    stats = await get_referral_stats(message.from_user.id) if user else {'referrals': 0, 'earned': 0}

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Поделиться ссылкой", url=f"https://t.me/share/url?url={user.referral_url}&text=BlackVPN — быстрый и надёжный VPN! Попробуй по моей ссылке!")],
        [InlineKeyboardButton(text="🚀 Открыть BlackVPN App", web_app=WebAppInfo(url=f"{settings.BASE_URL}/"))]
    ])
    await message.answer(
        f"<b>Реферальная программа</b>\n\n"
        f"Приглашайте друзей и получайте <b>50₽</b> за каждого, кто пополнит баланс!\n\n"
        f"<b>Ваша ссылка:</b>\n"
        f"<code>{user.referral_url}</code>\n\n"
        f"<b>Статистика:</b>\n"
        f"• Приглашено: <b>{stats['referrals']}</b>\n"
        f"• Заработано: <b>{stats['earned']} ₽</b>\n"
        f"• Всего заработано: <b>{user.referral_earnings} ₽</b>",
        reply_markup=keyboard,
        parse_mode='HTML'
    )


@router.callback_query(F.data == "back_to_menu")
async def cb_back_to_menu(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        f"Вы вернулись в главное меню.\nВаш ID: <code>{callback.from_user.id}</code>\n"
        f"Используйте кнопку ниже для быстрого доступа к приложению!",
        reply_markup=callback.message.reply_markup,
        parse_mode='HTML'
    )


@router.message(lambda msg: msg.web_app_data is not None)
async def web_app_data_handler(message: Message):
    user = await get_user(message.from_user.id)
    if user and user.banned:
        return
    try:
        data = json.loads(message.web_app_data.data)
    except Exception as e:
        logger.error(f"Failed to parse web_app_data: {e}")
        await message.answer("⚠️ Ошибка обработки данных приложения.")
        return

    action = data.get("action")
    if action == "create_payment":
        amount = float(data.get("amount", 0))
        method = data.get("method")
        user_id = message.from_user.id
        if amount < 50 or not method:
            await message.answer("⚠️ Некорректные данные для оплаты.")
            return

        if method == "stars":
            try:
                await message.bot.send_invoice(
                    chat_id=user_id,
                    title="Пополнение BlackVPN",
                    description=f"Пополнение личного баланса на {amount} ₽",
                    payload=f"topup_{user_id}_{amount}",
                    provider_token="",
                    currency="XTR",
                    prices=[LabeledPrice(label="Пополнение BlackVPN", amount=int(amount))],
                    need_name=False,
                    need_phone_number=False,
                    need_email=False,
                    need_shipping_address=False,
                    is_flexible=False
                )
            except Exception as e:
                logger.error(f"Failed to send invoice: {e}")
                await message.answer("⚠️ Не удалось создать счёт на оплату Stars.")
        else:
            await message.answer("✅ Счёт создан, проверьте ваш веб‑app для завершения оплаты.")
    else:
        await message.answer("⚠️ Неизвестное действие.")


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout: PreCheckoutQuery):
    await pre_checkout.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    if not payload.startswith("topup_"):
        await message.answer("⚠️ Ошибка: неизвестный платёж.")
        return
    parts = payload.split("_")
    if len(parts) < 3:
        return
    user_id = int(parts[1])
    amount = float(parts[2])
    stars_amount = payment.total_amount / 1

    await add_balance(user_id, amount)
    try:
        await db_create_payment(
            payment_id=f"stars_{payment.telegram_payment_charge_id}",
            user_id=user_id,
            amount=amount,
            method="stars"
        )
        p = await get_payment(f"stars_{payment.telegram_payment_charge_id}")
        if p:
            await update_payment_status(p['payment_id'], 'completed')
    except Exception as e:
        logger.error(f"Failed to save Stars payment: {e}")

    await message.answer(
        f"✅ Баланс пополнен на {amount} ₽ через Telegram Stars!\n"
        f"Списано звёзд: {stars_amount} ⭐",
        parse_mode='HTML'
    )


def register_router(dp: Dispatcher):
    dp.include_router(router)