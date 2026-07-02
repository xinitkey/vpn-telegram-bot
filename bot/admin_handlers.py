from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command, CommandObject
from aiogram import Dispatcher
from config import settings
from services.db import (
    get_user, get_all_users, get_user_count, get_active_sub_count,
    get_total_balance, get_payments_count, add_balance, set_subscription,
    update_vpn_info, create_user, get_recent_payments, get_all_completed_payments,
    get_user_payments, get_revenue,
    get_users_by_id_or_email, get_banned_count, get_trial_used_count,
    update_user, create_promocode, delete_promocode, get_all_promocodes,
    reset_trial, wipe_user,
)
from services.xui_api import add_client as xui_add_client, update_client_expiry as xui_update_expiry, build_link_for_email as xui_build_link_for_email, get_client_ips as xui_get_client_ips
import time
import logging
import csv
import io
import os

router = Router()
logger = logging.getLogger(__name__)

_NOT_ADMIN_MSG = "Команда доступна только администраторам."

def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


@router.message(Command("admins"))
async def cmd_admins(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Команда доступна только администраторам.")
        return
    if not settings.ADMIN_IDS:
        await message.answer("Нет администраторов.")
        return
    lines = [f"<b>Администраторы ({len(settings.ADMIN_IDS)})</b>"]
    for uid in settings.ADMIN_IDS:
        lines.append(f"• <code>{uid}</code>")
    await message.answer("\n".join(lines), parse_mode='HTML')


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    await message.answer(
        "<b>Admin Panel</b>\n\n"
        "<b>Информация:</b>\n"
        "/stats — статистика\n"
        "/users [страница] — список пользователей\n"
        "/find <code>id</code> — информация о пользователе\n"
        "/history <code>id</code> — история платежей пользователя\n"
        "/search <code>запрос</code> — поиск по ID или email\n"
        "/admins — список администраторов\n\n"
        "<b>Управление:</b>\n"
        "/add <code>id сумма</code> — пополнить баланс\n"
        "/give <code>id дней</code> — выдать подписку\n"
        "/giveall <code>дни</code> — добавить дни всем\n"
        "/reset <code>id</code> — сбросить подписку\n"
        "/wipe <code>id</code> — полностью стереть пользователя\n"
        "/resettrial <code>id</code> — обнулить триал\n"
        "/resettrial all — обнулить триал всем\n"
        "/ban <code>id</code> — заблокировать\n"
        "/unban <code>id</code> — разблокировать\n"
        "/notify <code>id текст</code> — личное сообщение\n\n"
        "<b>Платежи и финансы:</b>\n"
        "/payments [количество] — последние платежи\n"
        "/paymentsall — все успешные платежи (сводка)\n"
        "/revenue — доходы\n\n"
        "<b>Экспорт и система:</b>\n"
        "/export — выгрузить CSV\n"
        "/backup — скачать БД\n"
        "/xui — статус 3x-UI панели\n\n"
        "<b>Промокоды:</b>\n"
        "/addpromo <code>код процент [тарифы] [макс] [дата]</code>\n"
        "/delpromo <code>код</code>\n"
        "/promos — список промокодов\n\n"
        "<b>Прочее:</b>\n"
        "/broadcast <code>текст</code> — рассылка всем",
        parse_mode='HTML'
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    total_users = await get_user_count()
    active_subs = await get_active_sub_count()
    total_bal = await get_total_balance()
    payments = await get_payments_count()
    banned = await get_banned_count()
    trials = await get_trial_used_count()
    now_ms = int(time.time() * 1000)
    text = (
        f"<b>Статистика</b>\n\n"
        f"Всего пользователей: <code>{total_users}</code>\n"
        f"Активных подписок: <code>{active_subs}</code>\n"
        f"Забанено: <code>{banned}</code>\n"
        f"Использовали триал: <code>{trials}</code>\n"
        f"Баланс всех: <code>{total_bal:.0f} ₽</code>\n"
        f"Платежей всего: <code>{payments['total']}</code>\n"
        f"Успешных: <code>{payments['completed']}</code>\n"
        f"В ожидании: <code>{payments['pending']}</code>\n"
        f"Просрочено: <code>{payments['expired']}</code>"
    )
    await message.answer(text, parse_mode='HTML')


@router.message(Command("users"))
async def cmd_users(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    users = await get_all_users()
    now_ms = int(time.time() * 1000)
    page = 1
    if command.args and command.args.strip().isdigit():
        page = max(1, int(command.args.strip()))
    per_page = 20
    total_pages = max(1, (len(users) + per_page - 1) // per_page)
    page = min(page, total_pages)
    start = (page - 1) * per_page
    batch = users[start:start + per_page]
    lines = [f"<b>Пользователи ({len(users)}) — стр. {page}/{total_pages}</b>\n"]
    for u in batch:
        status = "+" if u.subscription and u.subscription > now_ms else "-"
        ban = " [x]" if u.banned else ""
        name = u.first_name or ''
        tag = f" @{u.telegram_username}" if u.telegram_username else ''
        lines.append(f"{status} <code>{u.user_id}</code> {name}{tag} — {u.balance:.0f}₽ — {u.days_left}дн.{ban}")
    lines.append(f"\n/users {page + 1} — след. страница")
    await message.answer("\n".join(lines), parse_mode='HTML')


@router.message(Command("find"))
async def cmd_find(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
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
    status = "Активна" if user.is_subscription_active else "Не активна"
    ban = "Да" if user.banned else "Нет"
    await message.answer(
        f"<b>Пользователь {user.user_id}</b>\n\n"
        f"Баланс: <code>{user.balance:.0f} ₽</code>\n"
        f"Имя: {user.first_name or '—'}\n"
        f"Username: @{user.telegram_username or '—'}\n"
        f"Забанен: <code>{ban}</code>\n"
        f"Триал: {'использован' if user.trial_used else 'доступен'}\n"
        f"Подписка: {status}\n"
        f"Осталось: {user.remaining_str}\n"
        f"Начало: {user.subscription_start_str}\n"
        f"Заканчивается: {user.subscription_end_str}\n"
        f"Ключ: <code>{user.link or 'нет'}</code>\n"
        f"Email: <code>{user.xui_email or 'нет'}</code>",
        parse_mode='HTML'
    )


@router.message(Command("history"))
async def cmd_history(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    args = command.args
    if not args or not args.strip().isdigit():
        await message.answer("Формат: /history <code>user_id</code>", parse_mode='HTML')
        return
    user_id = int(args.strip())
    user = await get_user(user_id)
    payments = await get_user_payments(user_id)
    if not payments:
        name = f"Пользователь <code>{user_id}</code>" if user else f"Неизвестный <code>{user_id}</code>"
        await message.answer(f"{name} — платежей нет.", parse_mode='HTML')
        return
    total = sum(p['amount'] for p in payments)
    completed = sum(1 for p in payments if p['status'] == 'completed')
    pending = sum(1 for p in payments if p['status'] == 'pending')
    lines = [
        f"<b>Платежи пользователя {user_id}</b>\n",
        f"Всего: <code>{len(payments)}</code> | "
        f"Успешно: <code>{completed}</code> | "
        f"В ожидании: <code>{pending}</code>",
        f"Сумма успешных: <code>{total:.0f} ₽</code>\n",
    ]
    for p in payments:
        ts = time.strftime('%d.%m.%Y %H:%M', time.localtime(p['created_at']))
        emoji = {'completed': '✅', 'pending': '⏳', 'expired': '❌'}.get(p['status'], '❓')
        lines.append(
            f"{emoji} <code>{p['payment_id'][:24]:24}</code> "
            f"{p['amount']:>6.0f}₽ "
            f"{p['method'] or '?':12} "
            f"{ts}"
        )
    await message.answer("\n".join(lines), parse_mode='HTML')


@router.message(Command("search"))
async def cmd_search(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    query = (command.args or "").strip()
    if not query:
        await message.answer("Формат: /search <code>id, email или @username</code>", parse_mode='HTML')
        return
    users = await get_users_by_id_or_email(query)
    if not users:
        await message.answer(f"Ничего не найдено по запросу <code>{query}</code>.", parse_mode='HTML')
        return
    now_ms = int(time.time() * 1000)
    lines = [f"<b>Результаты поиска: {query}</b>\n"]
    for u in users:
        status = "+" if u.subscription and u.subscription > now_ms else "-"
        ban = " [x]" if u.banned else ""
        user_str = f"@{u.telegram_username}" if u.telegram_username else str(u.user_id)
        lines.append(f"{status} <code>{u.user_id:>8}</code> {user_str:20} {u.balance:.0f}₽ {u.days_left}дн.{ban}")
    await message.answer("\n".join(lines), parse_mode='HTML')


@router.message(Command("add"))
async def cmd_add_balance(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
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
        f"Баланс пополнен на <code>{amount:.0f} ₽</code>\n"
        f"<code>{user_id}</code> — теперь <code>{user.balance:.0f} ₽</code>",
        parse_mode='HTML'
    )
    try:
        await message.bot.send_message(
            user_id,
            f"Ваш баланс пополнен на {amount:.0f} ₽ администратором.\n"
            f"Текущий баланс: {user.balance:.0f} ₽",
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")


@router.message(Command("give"))
async def cmd_give_sub(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
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
    user = await get_user(user_id)
    if settings.XUI_URL and settings.XUI_PASSWORD and (settings.XUI_INBOUND_ID is not None or settings.XUI_INBOUND_IDS):
        email = f'user_{user_id}'
        now_ms = int(time.time() * 1000)
        total_days = max(1, (user.subscription - now_ms) // 86400000) if user.subscription and user.subscription > now_ms else days
        try:
            if user.xui_email:
                await xui_update_expiry(user.xui_email, total_days)
                link = await xui_build_link_for_email(user.xui_email, user.xui_inbound_id or None)
                await update_vpn_info(user_id, link=link)
            else:
                client = await xui_add_client(email, total_days, user.xui_inbound_id or None)
                await update_vpn_info(user_id, uuid=client['uuid'], email=client['email'], link=client['link'])
                u = await get_user(user_id)
                if u:
                    u.xui_inbound_id = client['inbound_id']
                    await update_user(u)
        except Exception as e:
            logger.error(f"3x-UI error in give: {e}")
    user = await get_user(user_id)
    if user.link:
        try:
            from bot.handlers import send_key_with_platforms
            await send_key_with_platforms(message.bot, user_id, user.link, user.remaining_str)
        except Exception as e:
            logger.error(f"Failed to send key to user {user_id}: {e}")
    await message.answer(
        f"Выдано <code>{days}</code> дн. подписки\n"
        f"<code>{user_id}</code> — осталось <code>{user.days_left}</code> дн.",
        parse_mode='HTML'
    )


@router.message(Command("reset"))
async def cmd_reset_sub(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    args = command.args
    if not args or not args.strip().isdigit():
        await message.answer("Формат: /reset <code>user_id</code>", parse_mode='HTML')
        return
    user_id = int(args.strip())
    user = await get_user(user_id)
    if user is None:
        await message.answer(f"Пользователь <code>{user_id}</code> не найден.", parse_mode='HTML')
        return
    user.subscription = 0
    user.subscription_start = 0
    user.trial_used = False
    if user.xui_email:
        # Set expiry to now (0 days) in panel but keep the email reference
        try:
            from services.xui_api import update_client_expiry
            await update_client_expiry(user.xui_email, 0)
        except Exception as e:
            logger.warning(f"Failed to zero XUI client expiry for {user_id}: {e}")
    await update_user(user)
    await message.answer(
        f"Подписка пользователя <code>{user_id}</code> сброшена.",
        parse_mode='HTML'
    )


@router.message(Command("wipe"))
async def cmd_wipe(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    args = command.args
    if not args or not args.strip().isdigit():
        await message.answer("Формат: /wipe <code>user_id</code>", parse_mode='HTML')
        return
    user_id = int(args.strip())
    user = await get_user(user_id)
    if user is None:
        await message.answer(f"Пользователь <code>{user_id}</code> не найден.", parse_mode='HTML')
        return
    if user.xui_email:
        try:
            from services.xui_api import remove_client
            await remove_client(user.xui_email)
        except Exception as e:
            logger.warning(f"Failed to remove XUI client on wipe for {user_id}: {e}")
    await wipe_user(user_id)
    await message.answer(
        f"Пользователь <code>{user_id}</code> полностью стёрт.\n"
        f"Баланс, подписка, платежи, рефералы — удалены.",
        parse_mode='HTML'
    )


@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    args = command.args
    if not args or not args.strip().isdigit():
        await message.answer("Формат: /ban <code>user_id</code>", parse_mode='HTML')
        return
    user_id = int(args.strip())
    user = await get_user(user_id)
    if user is None:
        await message.answer(f"Пользователь <code>{user_id}</code> не найден.", parse_mode='HTML')
        return
    user.banned = True
    # Revoke VPN key
    if user.xui_email:
        try:
            from services.xui_api import remove_client
            await remove_client(user.xui_email)
        except Exception as e:
            logger.warning(f"Failed to remove XUI client for {user_id}: {e}")
    user.xui_email = ''
    user.xui_uuid = ''
    user.link = ''
    await update_user(user)
    await message.answer(
        f"Пользователь <code>{user_id}</code> заблокирован. Ключ отозван.",
        parse_mode='HTML'
    )


@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    args = command.args
    if not args or not args.strip().isdigit():
        await message.answer("Формат: /unban <code>user_id</code>", parse_mode='HTML')
        return
    user_id = int(args.strip())
    user = await get_user(user_id)
    if user is None:
        await message.answer(f"Пользователь <code>{user_id}</code> не найден.", parse_mode='HTML')
        return
    now_ms = int(time.time() * 1000)
    key_restored = False
    if user.subscription and user.subscription > now_ms:
        email = f'user_{user_id}'
        total_days = max(1, (user.subscription - now_ms) // 86400000)
        try:
            from services.xui_api import add_client, build_link_for_email, remove_client
            if user.xui_email:
                try:
                    await remove_client(user.xui_email)
                except Exception:
                    pass
            client = await add_client(email, total_days, user.xui_inbound_id or None)
            user.xui_uuid = client['uuid']
            user.xui_email = client['email']
            user.link = client['link']
            user.xui_inbound_id = client['inbound_id']
            key_restored = True
        except Exception as e:
            logger.error(f"Failed to recreate XUI client for {user_id}: {e}")
    user.banned = False
    await update_user(user)
    msg = f"Пользователь <code>{user_id}</code> разблокирован."
    if key_restored:
        msg += " Ключ восстановлен."
    elif user.subscription and user.subscription > now_ms:
        msg += " Не удалось восстановить ключ (ошибка XUI)."
    await message.answer(msg, parse_mode='HTML')


@router.message(Command("notify"))
async def cmd_notify(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    args = command.args
    if not args:
        await message.answer("Формат: /notify <code>id текст</code>", parse_mode='HTML')
        return
    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer("Формат: /notify <code>id текст</code>", parse_mode='HTML')
        return
    user_id = int(parts[0])
    text = parts[1]
    try:
        await message.bot.send_message(user_id, text, parse_mode='HTML')
        await message.answer(f"Сообщение отправлено <code>{user_id}</code>.", parse_mode='HTML')
    except Exception as e:
        await message.answer(f"Ошибка отправки <code>{user_id}</code>: {e}", parse_mode='HTML')


@router.message(Command("payments"))
async def cmd_payments(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    limit = 20
    if command.args and command.args.strip().isdigit():
        limit = max(1, min(100, int(command.args.strip())))
    payments = await get_recent_payments(limit)
    if not payments:
        await message.answer("Платежей нет.", parse_mode='HTML')
        return
    lines = [f"<b>Последние {len(payments)} платежей</b>\n"]
    for p in payments:
        status = "+" if p['status'] == 'completed' else "?"
        ts = time.strftime('%d.%m %H:%M', time.localtime(p['created_at']))
        lines.append(f"{status} <code>{p['user_id']}</code> {p['amount']:.0f}₽ {p['method']} ({ts})")
    await message.answer("\n".join(lines), parse_mode='HTML')


@router.message(Command("paymentsall"))
async def cmd_payments_all(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    payments = await get_all_completed_payments()
    if not payments:
        await message.answer("Успешных платежей нет.", parse_mode='HTML')
        return
    total_amount = sum(p['amount'] for p in payments)
    by_method = {}
    for p in payments:
        m = p['method'] or 'unknown'
        by_method[m] = by_method.get(m, 0) + p['amount']
    lines = [
        f"<b>Успешные платежи — {len(payments)} шт.</b>\n",
        f"На общую сумму: <code>{total_amount:.0f} ₽</code>\n",
    ]
    if len(by_method) > 1:
        lines.append("По методам:")
        for method, total in sorted(by_method.items(), key=lambda x: -x[1]):
            lines.append(f"  {method}: <code>{total:.0f} ₽</code>")
    lines.append("")
    for p in payments:
        ts = time.strftime('%d.%m.%Y %H:%M', time.localtime(p.get('completed_at') or p['created_at']))
        user_bal = p.get('user_balance', 0) or 0
        lines.append(
            f"<code>{p['payment_id'][:20]:20}</code> "
            f"<code>{p['user_id']:>8}</code> "
            f"{p['amount']:>6.0f}₽ "
            f"{p['method'] or '?':12} "
            f"{ts}"
        )
    if len(lines) > 50:
        text = "\n".join(lines)
        import io
        buf = io.StringIO(text)
        from aiogram.types import BufferedInputFile
        await message.answer_document(
            BufferedInputFile(buf.getvalue().encode('utf-8-sig'), filename=f"payments_{int(time.time())}.txt"),
            caption=f"Успешные платежи: {len(payments)} шт., {total_amount:.0f} ₽"
        )
    else:
        await message.answer("\n".join(lines), parse_mode='HTML')


@router.message(Command("revenue"))
async def cmd_revenue(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    rev = await get_revenue()
    text = [
        f"<b>Доходы</b>\n",
        f"Всего: <code>{rev['total']:.0f} ₽</code>\n"
    ]
    if rev['by_method']:
        text.append("\nПо методам:")
        for method, total in rev['by_method'].items():
            text.append(f"  {method}: <code>{total:.0f} ₽</code>")
    await message.answer("\n".join(text), parse_mode='HTML')


@router.message(Command("export"))
async def cmd_export(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    users = await get_all_users()
    now_ms = int(time.time() * 1000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['user_id', 'balance', 'sub_active', 'days_left', 'trial_used', 'banned', 'link', 'email', 'sub_start', 'sub_end'])
    for u in users:
        w.writerow([
            u.user_id, u.balance,
            1 if u.is_subscription_active else 0,
            u.days_left, int(u.trial_used), int(u.banned),
            u.link, u.xui_email,
            u.subscription_start_str, u.subscription_end_str
        ])
    data = buf.getvalue().encode('utf-8-sig')
    await message.answer_document(
        BufferedInputFile(data, filename=f"blackvpn_users_{int(time.time())}.csv"),
        caption=f"Экспорт пользователей: {len(users)} записей"
    )


@router.message(Command("backup"))
async def cmd_backup(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    db_path = settings.DB_URL.replace('sqlite+aiosqlite:///', '')
    if not os.path.isfile(db_path):
        await message.answer("Файл БД не найден.")
        return
    with open(db_path, 'rb') as f:
        data = f.read()
    await message.answer_document(
        BufferedInputFile(data, filename=f"blackvpn_backup_{int(time.time())}.db"),
        caption=f"Бэкап БД"
    )


@router.message(Command("xui"))
async def cmd_xui(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    if not settings.XUI_URL:
        await message.answer("XUI не настроен.")
        return
    try:
        from services.xui_api import get_inbound_info
        lines = [f"<b>3x-UI Статус</b>\n"]
        for iid in settings.XUI_INBOUND_IDS:
            inbound = await get_inbound_info(iid)
            port = inbound.get("port", "?")
            protocol = inbound.get("protocol", "?")
            remark = inbound.get("remark", "?")
            clients = inbound.get("clientStats", [])
            lines.append(
                f"#{iid} <code>{remark}</code> ({protocol}:{port}) — "
                f"<code>{len(clients)}</code> клиентов"
            )
        await message.answer("\n".join(lines), parse_mode='HTML')
    except Exception as e:
        await message.answer(f"Ошибка: {e}", parse_mode='HTML')


@router.message(Command("devices"))
async def cmd_devices(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    args = command.args.strip() if command.args else ""
    if not args:
        await message.answer("Использование: /devices <user_id>")
        return
    try:
        user_id = int(args.split()[0])
    except ValueError:
        await message.answer("Неверный ID пользователя")
        return
    user = await get_user(user_id)
    if user is None:
        await message.answer("Пользователь не найден")
        return
    if not user.xui_email:
        await message.answer(f"У пользователя {user_id} нет email в XUI")
        return

    from services.xui_api import _request, get_inbound_info
    email = user.xui_email
    lines = [f"<b>Диагностика устройств</b>\nUser: {user_id}\nEmail: {email}\n"]

    async def try_r(method: str, path: str, tag: str):
        try:
            import json
            data = await _request(method, path)
            lines.append(f"<b>{tag}:</b> <code>{json.dumps(data, default=str)[:400]}</code>")
        except Exception as e:
            lines.append(f"<b>{tag}:</b> <code>{str(e)[:200]}</code>")

    await try_r("POST", f"/panel/api/inbounds/clientIps/{email}", "clientIps path POST")
    await try_r("GET", f"/panel/api/inbounds/clientIps/{email}", "clientIps path GET")
    await try_r("POST", f"/panel/api/inbounds/clientIps?email={email}", "clientIps query POST")
    await try_r("POST", "/panel/api/inbounds/onlines", "onlines POST")
    await try_r("GET", "/panel/api/inbounds/onlines", "onlines GET")
    await try_r("POST", "/panel/api/inbounds/onlines?email={email}", "onlines with email POST")
    await try_r("GET", "/panel/api/inbounds/list", "inbounds list")
    # Show a couple other clients to compare structure
    inbounds_data = await _request("GET", "/panel/api/inbounds/list")
    if inbounds_data:
        for ib in inbounds_data if isinstance(inbounds_data, list) else []:
            for cl in ib.get("clientStats", [])[:3]:
                if isinstance(cl, dict) and cl.get("email") != email:
                    import json
                    lines.append(f"<b>other client:</b> <code>{json.dumps(cl, default=str)[:400]}</code>")
                    break

    for iid in settings.XUI_INBOUND_IDS:
        inbound = await get_inbound_info(iid)
        for cl in inbound.get("clientStats", []):
            if isinstance(cl, dict) and cl.get("email") == email:
                import json
                lines.append(f"<b>clientStats:</b> <code>{json.dumps(cl, default=str)[:600]}</code>")
                break

    await message.answer("\n".join(lines), parse_mode='HTML')


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
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
        f"Рассылкa завершена\n"
        f"Доставлено: <code>{sent}</code>\n"
        f"Ошибок: <code>{failed}</code>",
        parse_mode='HTML'
    )


@router.message(Command("addpromo"))
async def cmd_addpromo(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    args = (command.args or "").strip().split()
    if len(args) < 2:
        await message.answer(
            "Формат: /addpromo <code>код процент [тарифы] [макс_исп] [дата_до]\n\n"
            "Примеры:\n"
            "/addpromo WELCOME20 20 — 20% на все тарифы без ограничений\n"
            "/addpromo SUMMER 30 2,3,5 100 — 30% на тарифы 2,3,5 на 100 активаций\n"
            "/addpromo VIP10 10 '' 50 2026-12-31 — 10% на всё, 50 активаций, до 31.12.2026\n\n"
            "Нумерация тарифов: 1=3д, 2=30д, 3=90д, 4=180д, 5=365д",
            parse_mode='HTML'
        )
        return
    code = args[0].upper()
    if not args[1].isdigit():
        await message.answer("Процент скидки должен быть числом", parse_mode='HTML')
        return
    discount = int(args[1])
    if discount < 1 or discount > 99:
        await message.answer("Процент скидки от 1 до 99", parse_mode='HTML')
        return
    tariff_ids = args[2] if len(args) > 2 and args[2] and args[2].strip("'\"") else None
    max_uses = int(args[3]) if len(args) > 3 and args[3].isdigit() else None
    expires_at = None
    if len(args) > 4 and args[4]:
        from datetime import datetime
        try:
            dt = datetime.strptime(args[4], '%Y-%m-%d')
            expires_at = int(dt.timestamp() * 1000) + 86400000
        except ValueError:
            await message.answer("Неверный формат даты. Используйте ГГГГ-ММ-ДД", parse_mode='HTML')
            return
    ok = await create_promocode(code, discount, tariff_ids, max_uses, expires_at)
    if ok:
        parts = [f"Промокод <code>{code}</code> создан"]
        parts.append(f"Скидка: {discount}%")
        if tariff_ids:
            parts.append(f"Тарифы: {tariff_ids}")
        if max_uses:
            parts.append(f"Макс. активаций: {max_uses}")
        if expires_at:
            parts.append(f"Действует до: {args[4]}")
        await message.answer("\n".join(parts), parse_mode='HTML')
    else:
        await message.answer(f"Промокод <code>{code}</code> уже существует", parse_mode='HTML')


@router.message(Command("delpromo"))
async def cmd_delpromo(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    code = (command.args or "").strip().upper()
    if not code:
        await message.answer("Формат: /delpromo <code>код</code>", parse_mode='HTML')
        return
    ok = await delete_promocode(code)
    if ok:
        await message.answer(f"Промокод <code>{code}</code> удалён", parse_mode='HTML')
    else:
        await message.answer(f"Промокод <code>{code}</code> не найден", parse_mode='HTML')


@router.message(Command("promos"))
async def cmd_promos(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    promos = await get_all_promocodes()
    if not promos:
        await message.answer("Нет промокодов", parse_mode='HTML')
        return
    lines = [f"<b>Промокоды ({len(promos)})</b>\n"]
    now = int(time.time() * 1000)
    for p in promos:
        expired = p['expires_at'] and now > p['expires_at']
        exhausted = p['max_uses'] is not None and p['used_count'] >= p['max_uses']
        status = '❌' if expired or exhausted else '✅'
        active_str = f"{p['used_count']}"
        if p['max_uses']:
            active_str += f"/{p['max_uses']}"
        info = f"{status} <code>{p['code']}</code> — {p['discount_percent']}%"
        if p['tariff_ids']:
            info += f" [тарифы {p['tariff_ids']}]"
        info += f" | {active_str}"
        if expired:
            info += " <b>(просрочен)</b>"
        lines.append(info)
    await message.answer("\n".join(lines), parse_mode='HTML')


@router.message(Command("giveall"))
async def cmd_giveall(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    args = command.args
    if not args or not args.strip().isdigit():
        await message.answer("Формат: /giveall <code>дни</code>", parse_mode='HTML')
        return
    days = int(args.strip())
    users = await get_all_users()
    done = 0
    for u in users:
        try:
            await set_subscription(u.user_id, days)
            u = await get_user(u.user_id)
            if settings.XUI_URL and settings.XUI_PASSWORD and (settings.XUI_INBOUND_ID is not None or settings.XUI_INBOUND_IDS):
                email = f'user_{u.user_id}'
                now_ms = int(time.time() * 1000)
                total_days = max(1, (u.subscription - now_ms) // 86400000) if u.subscription and u.subscription > now_ms else days
                try:
                    if u.xui_email:
                        await xui_update_expiry(u.xui_email, total_days)
                        link = await xui_build_link_for_email(u.xui_email, u.xui_inbound_id or None)
                        await update_vpn_info(u.user_id, link=link)
                    else:
                        client = await xui_add_client(email, total_days, u.xui_inbound_id or None)
                        await update_vpn_info(u.user_id, uuid=client['uuid'], email=client['email'], link=client['link'])
                        upd = await get_user(u.user_id)
                        if upd:
                            upd.xui_inbound_id = client['inbound_id']
                            await update_user(upd)
                except Exception:
                    pass
            done += 1
        except Exception:
            pass
    await message.answer(
        f"Подписка добавлена <code>{done}/{len(users)}</code> пользователям\n"
        f"Каждому: +<code>{days}</code> дн.",
        parse_mode='HTML'
    )


@router.message(Command("resettrial"))
async def cmd_resettrial(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    arg = (command.args or "").strip()
    if not arg:
        await message.answer("Формат: /resettrial <code>id</code> или <code>all</code>", parse_mode='HTML')
        return
    if arg == 'all':
        await reset_trial()
        count = await get_trial_used_count()
        await message.answer(
            f"Триал обнулён всем пользователям.\n"
            f"Теперь использовали триал: <code>{count}</code>",
            parse_mode='HTML'
        )
    elif arg.isdigit():
        user_id = int(arg)
        user = await get_user(user_id)
        if user is None:
            await message.answer(f"Пользователь <code>{user_id}</code> не найден.", parse_mode='HTML')
            return
        await reset_trial(user_id)
        await message.answer(
            f"Триал обнулён для <code>{user_id}</code>.",
            parse_mode='HTML'
        )
    else:
        await message.answer("Формат: /resettrial <code>id</code> или <code>all</code>", parse_mode='HTML')
