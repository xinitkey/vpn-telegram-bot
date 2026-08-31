from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command, CommandObject
from aiogram import Dispatcher
from config import settings
from services.db import (
    get_user, get_all_users, get_active_users, get_user_count, get_active_sub_count,
    get_total_balance, get_payments_count, add_balance, set_subscription,
    update_vpn_info, create_user, get_recent_payments, get_all_completed_payments,
    get_user_payments, get_revenue,
    get_users_by_id_or_email, get_banned_count, get_trial_used_count,
    update_user, create_promocode, delete_promocode, get_all_promocodes,
    reset_trial, wipe_user,
)
from services.vpn import get_provider
import time
import logging

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
        "/giveallactive <code>дни</code> [комментарий] — добавить дни активным\n"
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
        "<b>Система:</b>\n"
        "/vpn — статус VPN-провайдера\n"
        "/resync <code>id</code> — пересоздать клиента у провайдера\n\n"
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
    panel_note = ""
    if user.xui_email:
        try:
            from services.xui_api import get_client_expiry
            panel_expiry = await get_client_expiry(user.xui_email)
            if panel_expiry is not None and panel_expiry != user.subscription:
                user.subscription = panel_expiry
                from services.db import update_user
                await update_user(user)
                panel_note = f"\n⚠ Панель: {user.remaining_str} (БД скорректирована)"
        except Exception as e:
            logging.warning(f"Failed to fetch panel expiry for {user.xui_email}: {e}")
            panel_note = "\n⚠ Ошибка синхронизации с панелью"
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
        f"Email: <code>{user.xui_email or 'нет'}</code>"
        f"{panel_note}",
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
    provider = get_provider()
    if provider.enabled:
        email = f'user_{user_id}'
        now_ms = int(time.time() * 1000)
        total_days = max(1, (user.subscription - now_ms) // 86400000) if user.subscription and user.subscription > now_ms else days
        try:
            if user.xui_email:
                result = await provider.sync_or_create_client(user.xui_email, total_days, user.xui_inbound_id or None)
                await update_vpn_info(user_id, email=result['email'], link=result['link'])
                if result.get('recreated'):
                    u_upd = await get_user(user_id)
                    if u_upd:
                        u_upd.xui_uuid = result.get('uuid', u_upd.xui_uuid)
                        u_upd.xui_inbound_id = result.get('inbound_id', u_upd.xui_inbound_id)
                        await update_user(u_upd)
            else:
                client = await provider.add_client(email, total_days, user.xui_inbound_id or None)
                await update_vpn_info(user_id, uuid=client['uuid'], email=client['email'], link=client['link'])
                u = await get_user(user_id)
                if u:
                    u.xui_inbound_id = client['inbound_id']
                    await update_user(u)
        except Exception as e:
            logger.error(f"VPN provider error in give: {e}")
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
        try:
            await get_provider().update_client_expiry(user.xui_email, 0)
        except Exception as e:
            logger.warning(f"Failed to zero provider client expiry for {user_id}: {e}")
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
            await get_provider().remove_client(user.xui_email)
        except Exception as e:
            logger.warning(f"Failed to remove VPN client on wipe for {user_id}: {e}")
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
            await get_provider().remove_client(user.xui_email)
        except Exception as e:
            logger.warning(f"Failed to remove VPN client for {user_id}: {e}")
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
            provider = get_provider()
            if user.xui_email:
                try:
                    await provider.remove_client(user.xui_email)
                except Exception:
                    pass
            client = await provider.add_client(email, total_days, user.xui_inbound_id or None)
            user.xui_uuid = client['uuid']
            user.xui_email = client['email']
            user.link = client['link']
            user.xui_inbound_id = client['inbound_id']
            key_restored = True
        except Exception as e:
            logger.error(f"Failed to recreate VPN client for {user_id}: {e}")
    user.banned = False
    await update_user(user)
    msg = f"Пользователь <code>{user_id}</code> разблокирован."
    if key_restored:
        msg += " Ключ восстановлен."
    elif user.subscription and user.subscription > now_ms:
        msg += " Не удалось восстановить ключ (ошибка VPN-провайдера)."
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


@router.message(Command("vpn"))
async def cmd_vpn(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    provider = get_provider()
    lines = [
        f"<b>VPN-провайдер</b>\n",
        f"Тип: <code>{provider.name}</code>",
        f"Активен: <code>{'да' if provider.enabled else 'нет'}</code>",
        f"Inbounds: <code>{provider.inbound_ids or '—'}</code>",
    ]
    if not provider.enabled:
        lines.append("\nПровайдер не настроен. Используйте VPN_PROVIDER и связанные настройки.")
    await message.answer("\n".join(lines), parse_mode='HTML')


@router.message(Command("resync"))
async def cmd_resync(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    args = command.args.strip() if command.args else ""
    if not args or not args.isdigit():
        await message.answer("Использование: /resync <user_id>")
        return
    user_id = int(args)
    user = await get_user(user_id)
    if user is None:
        await message.answer("Пользователь не найден")
        return
    email = f'user_{user_id}'
    try:
        client = await get_provider().add_client(email, 1, user.xui_inbound_id or None)
        user.xui_uuid = client['uuid']
        user.xui_email = client['email']
        user.link = client['link']
        user.xui_inbound_id = client['inbound_id']
        await update_user(user)
        await message.answer(
            f"Клиент пересоздан.\nEmail: {client['email']}\nСсылка: {client['link']}",
            parse_mode='HTML'
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}", parse_mode='HTML')


@router.message(Command("addpromo"))
async def cmd_addpromo(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    args = (command.args or "").strip().split()
    if len(args) < 2:
        await message.answer(
            "Формат: /addpromo <code>код процент [тарифы] [макс_исп] [дата_до]</code>\n"
            "или: <code>/addpromo код days N [макс_исп] [дата_до]</code> — промокод дарит N дней подписки\n\n"
            "Примеры:\n"
            "/addpromo WELCOME20 20 — 20% на все тарифы без ограничений\n"
            "/addpromo SUMMER 30 2,3,5 100 — 30% на тарифы 2,3,5 на 100 активаций\n"
            "/addpromo GIFT7 days 7 50 2026-12-31 — 7 дней подписки, 50 активаций, до 31.12.2026\n\n"
            "Нумерация тарифов: 1=3д, 2=30д, 3=90д, 4=180д, 5=365д",
            parse_mode='HTML'
        )
        return
    code = args[0].upper()
    if args[1].lower() == 'days':
        if len(args) < 3 or not args[2].isdigit():
            await message.answer("Укажите количество дней: /addpromo <code>код days N</code>", parse_mode='HTML')
            return
        grant_days = int(args[2])
        if grant_days < 1:
            await message.answer("Количество дней должно быть больше 0", parse_mode='HTML')
            return
        discount = 0
        tariff_ids = None
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
    else:
        if not args[1].isdigit():
            await message.answer("Процент скидки должен быть числом", parse_mode='HTML')
            return
        discount = int(args[1])
        if discount < 1 or discount > 99:
            await message.answer("Процент скидки от 1 до 99", parse_mode='HTML')
            return
        grant_days = 0
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
    ok = await create_promocode(code, discount, tariff_ids, max_uses, expires_at, grant_days)
    if ok:
        parts = [f"Промокод <code>{code}</code> создан"]
        if grant_days:
            parts.append(f"Дарит дней: {grant_days}")
        else:
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
        info = f"{status} <code>{p['code']}</code>"
        if p.get('grant_days'):
            info += f" — дарит {p['grant_days']} дн."
        else:
            info += f" — {p['discount_percent']}%"
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
            if get_provider().enabled:
                email = f'user_{u.user_id}'
                now_ms = int(time.time() * 1000)
                total_days = max(1, (u.subscription - now_ms) // 86400000) if u.subscription and u.subscription > now_ms else days
                try:
                    if u.xui_email:
                        await get_provider().update_client_expiry(u.xui_email, total_days)
                        link = await get_provider().build_link_for_email(u.xui_email, u.xui_inbound_id or None)
                        await update_vpn_info(u.user_id, link=link)
                    else:
                        client = await get_provider().add_client(email, total_days, u.xui_inbound_id or None)
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


@router.message(Command("giveallactive"))
async def cmd_giveallactive(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer(_NOT_ADMIN_MSG)
        return
    args = command.args
    if not args:
        await message.answer("Формат: /giveallactive <code>дни</code> [комментарий]", parse_mode='HTML')
        return
    parts = args.strip().split(maxsplit=1)
    if not parts or not parts[0].isdigit():
        await message.answer("Формат: /giveallactive <code>дни</code> [комментарий]", parse_mode='HTML')
        return
    days = int(parts[0])
    comment = parts[1] if len(parts) > 1 else ''
    users = await get_active_users()
    done = 0
    for u in users:
        try:
            await set_subscription(u.user_id, days)
            u = await get_user(u.user_id)
            if get_provider().enabled:
                email = f'user_{u.user_id}'
                now_ms = int(time.time() * 1000)
                total_days = max(1, (u.subscription - now_ms) // 86400000) if u.subscription and u.subscription > now_ms else days
                try:
                    if u.xui_email:
                        await get_provider().update_client_expiry(u.xui_email, total_days)
                        link = await get_provider().build_link_for_email(u.xui_email, u.xui_inbound_id or None)
                        await update_vpn_info(u.user_id, link=link)
                    else:
                        client = await get_provider().add_client(email, total_days, u.xui_inbound_id or None)
                        await update_vpn_info(u.user_id, uuid=client['uuid'], email=client['email'], link=client['link'])
                        upd = await get_user(u.user_id)
                        if upd:
                            upd.xui_inbound_id = client['inbound_id']
                            await update_user(upd)
                except Exception:
                    pass
            if comment:
                try:
                    await message.bot.send_message(u.user_id, comment, parse_mode='HTML')
                except Exception:
                    pass
            done += 1
        except Exception:
            pass
    result = f"Подписка добавлена <code>{done}/{len(users)}</code> активным пользователям\nКаждому: +<code>{days}</code> дн."
    if comment:
        result += f"\nКомментарий отправлен"
    await message.answer(result, parse_mode='HTML')


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
