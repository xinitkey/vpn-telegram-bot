from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command, CommandObject
from aiogram import Dispatcher
from config import settings
from services.db import (
    get_user, get_all_users, get_user_count, get_active_sub_count,
    get_total_balance, get_payments_count, add_balance, set_subscription,
    update_vpn_info, create_user
)
from services.xui_api import add_client as xui_add_client, update_client_expiry as xui_update_expiry
import time
import logging

router = Router()
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "<b>🛠 Admin Panel</b>\n\n"
        "Команды:\n"
        "• /stats — статистика\n"
        "• /users — список пользователей\n"
        "• /find <code>id</code> — информация о пользователе\n"
        "• /add <code>id сумма</code> — пополнить баланс\n"
        "• /give <code>id дней</code> — выдать подписку\n"
        "• /broadcast <code>текст</code> — рассылка всем",
        parse_mode='HTML'
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    total_users = await get_user_count()
    active_subs = await get_active_sub_count()
    total_bal = await get_total_balance()
    payments = await get_payments_count()
    text = (
        f"<b>📊 Статистика</b>\n\n"
        f"👤 Всего пользователей: <code>{total_users}</code>\n"
        f"✅ Активных подписок: <code>{active_subs}</code>\n"
        f"💰 Баланс всех: <code>{total_bal:.0f} ₽</code>\n"
        f"💳 Всего платежей: <code>{payments['total']}</code>\n"
        f"✔ Успешных: <code>{payments['completed']}</code>\n"
        f"❌ Ожидают: <code>{payments['total'] - payments['completed']}</code>"
    )
    await message.answer(text, parse_mode='HTML')


@router.message(Command("users"))
async def cmd_users(message: Message):
    if not is_admin(message.from_user.id):
        return
    users = await get_all_users()
    now_ms = int(time.time() * 1000)
    lines = [f"<b>📋 Пользователи ({len(users)})</b>\n"]
    for u in users[-20:]:
        status = "🟢" if u.subscription and u.subscription > now_ms else "🔴"
        lines.append(f"{status} <code>{u.user_id}</code> — {u.balance:.0f}₽ — {u.days_left}дн.")
    await message.answer("\n".join(lines), parse_mode='HTML')


@router.message(Command("find"))
async def cmd_find(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    args = command.args
    if not args or not args.strip().isdigit():
        await message.answer("Формат: /find <code>user_id</code>", parse_mode='HTML')
        return
    user_id = int(args.strip())
    user = await get_user(user_id)
    if user is None:
        await message.answer(f"Пользователь <code>{user_id}</code> не найден.", parse_mode='HTML')
        return
    status = "🟢 Активна" if user.is_subscription_active else "🔴 Не активна"
    await message.answer(
        f"<b>👤 Пользователь {user.user_id}</b>\n\n"
        f"💰 Баланс: <code>{user.balance:.0f} ₽</code>\n"
        f"📅 Подписка: {status} ({user.days_left} дн.)\n"
        f"🔑 Ключ: <code>{user.link or 'нет'}</code>\n"
        f"📧 Email: <code>{user.xui_email or 'нет'}</code>",
        parse_mode='HTML'
    )


@router.message(Command("add"))
async def cmd_add_balance(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    args = command.args
    if not args:
        await message.answer("Формат: /add <code>user_id сумма</code>", parse_mode='HTML')
        return
    parts = args.strip().split()
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].lstrip('-').replace('.', '').isdigit():
        await message.answer("Формат: /add <code>user_id сумма</code>", parse_mode='HTML')
        return
    user_id = int(parts[0])
    amount = float(parts[1])
    user = await get_user(user_id)
    if user is None:
        await create_user(user_id)
    await add_balance(user_id, amount)
    user = await get_user(user_id)
    await message.answer(
        f"✅ Баланс пополнен на <code>{amount:.0f} ₽</code>\n"
        f"👤 <code>{user_id}</code> — теперь <code>{user.balance:.0f} ₽</code>",
        parse_mode='HTML'
    )


@router.message(Command("give"))
async def cmd_give_sub(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    args = command.args
    if not args:
        await message.answer("Формат: /give <code>user_id дней</code>", parse_mode='HTML')
        return
    parts = args.strip().split()
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await message.answer("Формат: /give <code>user_id дней</code>", parse_mode='HTML')
        return
    user_id = int(parts[0])
    days = int(parts[1])
    user = await get_user(user_id)
    if user is None:
        await create_user(user_id)
        user = await get_user(user_id)
    await set_subscription(user_id, days)
    if settings.XUI_URL and settings.XUI_API_TOKEN and settings.XUI_INBOUND_ID is not None:
        email = f'user_{user_id}'
        now_ms = int(time.time() * 1000)
        sub = max(user.subscription or now_ms, now_ms) + days * 86400000
        total_days = max(1, (sub - now_ms) // 86400000)
        try:
            if user.xui_email:
                await xui_update_expiry(user.xui_email, total_days)
            else:
                client = await xui_add_client(email, total_days)
                await update_vpn_info(user_id, uuid=client['uuid'], email=client['email'], link=client['link'])
        except Exception as e:
            logger.error(f"3x-UI error in give: {e}")
    user = await get_user(user_id)
    await message.answer(
        f"✅ Выдано <code>{days}</code> дн. подписки\n"
        f"👤 <code>{user_id}</code> — осталось <code>{user.days_left}</code> дн.",
        parse_mode='HTML'
    )


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    text = command.args
    if not text:
        await message.answer("Формат: /broadcast <code>текст</code>", parse_mode='HTML')
        return
    users = await get_all_users()
    sent = 0
    failed = 0
    for u in users:
        try:
            await message.bot.send_message(u.user_id, text, parse_mode='HTML')
            sent += 1
        except Exception:
            failed += 1
    await message.answer(
        f"📨 Рассылка завершена\n"
        f"✅ Доставлено: <code>{sent}</code>\n"
        f"❌ Ошибок: <code>{failed}</code>",
        parse_mode='HTML'
    )
