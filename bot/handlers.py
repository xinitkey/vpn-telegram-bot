from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, LabeledPrice
from aiogram.filters import CommandStart
from config import settings
from aiogram.types import Message
import json
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    webapp_url = f"https://{settings.HOST}:{settings.PORT}/app" if settings.HOST != '0.0.0.0" else f"http://localhost:{settings.PORT}/app"
    # If behind domain, better to use env var BASE_URL; we'll just use request origin later via middleware.
    # For simplicity, we'll use a placeholder that will be replaced by frontend via workerUrl.
    # We'll just use a generic URL; the frontend will compute workerUrl from window.location.origin.
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть BlackVPN App", web_app=WebAppInfo(url=f"{settings.BASE_URL}/app"))]
    ])
    await message.answer(
        f"Добро пожаловать в <b>BlackVPN</b>!\n"
        f"Ваш ID: <code>{user_id}</code>\n"
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

# Handle data sent from WebApp via tg.sendData
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
        # For now just acknowledge; actual payment URL will be provided by the webapp after calling /api/create-payment
        # The webapp already called /api/create-payment before sending data? In original flow:
        # user clicks pay -> webapp calls /api/create-payment -> gets paymentUrl -> if stars -> sendData
        # So we just need to send the invoice.
        if method == "stars":
            # Create invoice via bot
            from aiogram.types import LabeledPrice
            prices = [LabeledPrice(label="Пополнение BlackVPN", amount=int(amount * 100))]  # stars are integer
            try:
                await message.bot.send_invoice(
                    chat_id=user_id,
                    title="Пополнение BlackVPN",
                    description=f"Пополнение личного баланса на {amount} ₽",
                    payload=f"topup_{user_id}_{amount}",
                    provider_token="",  # empty for Stars
                    currency="XTR",
                    prices=prices,
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
            # For other methods, the webapp already opened link via tg.openLink after receiving paymentUrl
            # So we just acknowledge.
            await message.answer("✅ Счёт создан, проверьте ваш веб‑app для завершения оплаты.")
    else:
        await message.answer("⚠️ Неизвестное действие.")

def register_router(dp: Dispatcher):
    dp.include_router(router)