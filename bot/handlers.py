from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, LabeledPrice, PreCheckoutQuery
from aiogram.filters import CommandStart
from aiogram import Dispatcher
from config import settings
from services.db import add_balance, create_payment as db_create_payment, get_payment, update_payment_status
import json
import logging

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть BlackVPN App", web_app=WebAppInfo(url=f"{settings.BASE_URL}/app"))]
    ])
    await message.answer(
        f"Добро пожаловать в <b>BlackVPN</b>!\n"
        f"Ваш ID: <code>{message.from_user.id}</code>\n"
        f"Нажмите кнопку ниже, чтобы открыть приложение управления VPN:",
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