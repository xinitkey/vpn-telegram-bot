from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command, CommandObject
from aiogram import Dispatcher
from config import settings
from services.db import (
    get_user, get_all_users, get_user_count, get_active_sub_count,
    get_total_balance, get_payments_count, add_balance, set_subscription,
    update_vpn_info, create_user, get_recent_payments, get_revenue,
    get_users_by_id_or_email, get_banned_count, get_trial_used_count,
    update_user
)
from services.xui_api import add_client as xui_add_client, update_client_expiry as xui_update_expiry, build_link_for_email as xui_build_link_for_email
import time
import logging
import csv
import io
import os

router = Router()
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "<b>Admin Panel</b>\n\n"
        "<b>Информация:</b>\n"
        "/stats — статистика\n"
        "/users [страница] — список пользователей\n"
        "/find <code>id</code> — информация о пользователе\n"
        "/search <code>запрос</code> — поиск по ID или email\n\n"
        "<b>Управление:</b>\n"
        "/add <code>id сумма</code> — пополнить баланс\n"
        "/give <code>id дней</code> — выдать подписку\n"
        "/reset <code>id</code> — сбросить подписку\n"
        "/ban <code>id</code> — заблокировать\n"
        "/unban <code>id</code> — разблокировать\n"
        "/notify <code>id текст</code> — личное сообщение\n\n"
        "<b>Платежи и финансы:</b>\n"
        "/payments [количество] — последние платежи\n"
        "/revenue — доходы\n\n"
        "<b>Экспорт и система:</b>\n"
        "/export — выгрузить CSV\n"
        "/backup — скачать БД\n"
        "/xui — статус 3x-UI панели\n\n"
        "<b>Прочее:</b>\n"
        "/broadcast <code>текст</code> — рассылка всем",
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
        lines.append(f"{status} <code>{u.user_id}</code> — {u.balance:.0f}₽ — {u.days_left}дн.{ban}")
    lines.append(f"\n/users {page + 1} — след. страница")
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
    status = "Активна" if user.is_subscription_active else "Не активна"
    ban = "Да" if user.banned else "Нет"
    await message.answer(
        f"<b>Пользователь {user.user_id}</b>\n\n"
        f"Баланс: <code>{user.balance:.0f} ₽</code>\n"
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


@router.message(Command("search"))
async def cmd_search(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    query = (command.args or "").strip()
    if not query:
        await message.answer("Формат: /search <code>id или email</code>", parse_mode='HTML')
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
        lines.append(f"{status} <code>{u.user_id}</code> — {u.balance:.0f}₽ — {u.days_left}дн.{ban}")
    await message.answer("\n".join(lines), parse_mode='HTML')


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
        f"Баланс пополнен на <code>{amount:.0f} ₽</code>\n"
        f"<code>{user_id}</code> — теперь <code>{user.balance:.0f} ₽</code>",
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
    if settings.XUI_URL and settings.XUI_PASSWORD and (settings.XUI_INBOUND_ID is not None or settings.XUI_INBOUND_IDS):
        email = f'user_{user_id}'
        now_ms = int(time.time() * 1000)
        sub = max(user.subscription or now_ms, now_ms) + days * 86400000
        total_days = max(1, (sub - now_ms) // 86400000)
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
            await message.bot.send_message(
                user_id,
                f"<b>Вам выдана подписка BlackVPN!</b>\n\n"
                f"<b>Ваш ключ:</b>\n"
                f"{user.link}\n\n"
                f"<b>Осталось:</b> {user.remaining_str}\n\n"
                f"<b>Инструкция:</b> Выберите и установите приложение из списка поддерживаемых "
                f"и перейдите по ссылке для копирования или подключения ключа\n\n"
                f"<b>Скачать приложения</b>\n\n"
                f"<b>iPhone / iPad:</b>\n"
                f"• Happ — https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973 (рекомендуется)\n"
                f"• Hiddify — https://apps.apple.com/app/hiddify-proxy/id6596777532\n"
                f"• sing-box VT — https://apps.apple.com/ru/app/sing-box-vt/id6673731168\n"
                f"  (App Store, не TestFlight! Profiles → Remote → URL подписки)\n"
                f"• DefaultVPN — https://apps.apple.com/ru/app/defaultvpn/id6744725017\n"
                f"  (+ → Insert → vless-ключ; при необходимости включите Use VLESS protocol)\n"
                f"• V2RayTun — https://apps.apple.com/app/v2raytun/id6476628951\n"
                f"• Streisand — https://apps.apple.com/app/streisand/id6450534064\n"
                f"• Amnezia VPN — https://apps.apple.com/app/amnezia-vpn/id1600529900\n\n"
                f"<b>Android:</b>\n"
                f"• Happ — https://play.google.com/store/apps/details?id=com.happproxy (рекомендуется)\n"
                f"• Hiddify — https://play.google.com/store/apps/details?id=app.hiddify.com\n"
                f"• Amnezia VPN — https://play.google.com/store/apps/details?id=org.amnezia.vpn\n"
                f"• NekoBox — https://github.com/MatsuriDayo/NekoBoxForAndroid/releases\n"
                f"• Sing-box — https://play.google.com/store/apps/details?id=io.nekohasekai.sfa\n\n"
                f"<b>Компьютер (Windows / macOS / Linux):</b>\n"
                f"• Happ — https://github.com/Happ-proxy/happ-desktop/releases (рекомендуется)\n"
                f"• Hiddify — https://github.com/hiddify/hiddify-app/releases\n"
                f"• Amnezia VPN — https://amnezia.org/downloads\n"
                f"• Nekoray — https://github.com/MatsuriDayo/nekoray/releases",
                parse_mode='HTML'
            )
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
    await update_user(user)
    await message.answer(
        f"Подписка пользователя <code>{user_id}</code> сброшена.",
        parse_mode='HTML'
    )


@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
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
    await update_user(user)
    await message.answer(
        f"Пользователь <code>{user_id}</code> заблокирован.",
        parse_mode='HTML'
    )


@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
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
    user.banned = False
    await update_user(user)
    await message.answer(
        f"Пользователь <code>{user_id}</code> разблокирован.",
        parse_mode='HTML'
    )


@router.message(Command("notify"))
async def cmd_notify(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
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


@router.message(Command("revenue"))
async def cmd_revenue(message: Message):
    if not is_admin(message.from_user.id):
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
        f"Рассылкa завершена\n"
        f"Доставлено: <code>{sent}</code>\n"
        f"Ошибок: <code>{failed}</code>",
        parse_mode='HTML'
    )
