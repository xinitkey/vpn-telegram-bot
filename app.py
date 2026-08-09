import asyncio
import logging
import os
import time
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import MenuButtonWebApp, WebAppInfo
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from bot.handlers import register_router
from bot.admin_handlers import router as admin_router
from web.routes import setup_routes
from config import settings
from services.db import init_db, close_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

_REQUIRED_ENV = [
    ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_BOT_TOKEN'),
    ('XUI_URL', 'XUI_URL'),
    ('XUI_API_TOKEN', 'XUI_API_TOKEN'),
    ('XUI_INBOUND_IDS', 'XUI_INBOUND_IDS'),
    ('XUI_PASSWORD', 'XUI_PASSWORD'),
    ('BASE_URL', 'BASE_URL'),
]

def _validate_settings():
    missing = []
    for name, attr in _REQUIRED_ENV:
        if not getattr(settings, attr, None):
            missing.append(name)
    if missing:
        logger.warning("Missing required env vars: %s", ', '.join(missing))

async def on_startup(_app):
    bot = _app['bot']
    await bot.delete_webhook(drop_pending_updates=True)
    await init_db()
    webhook_url = f"{settings.BASE_URL}/telegram-webhook"
    await bot.set_webhook(webhook_url)
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="BlackVPN", web_app=WebAppInfo(url=f"{settings.BASE_URL}/"))
    )
    logger.info("Webhook set to %s", webhook_url)
    _app['bg_tasks'] = []
    _app['bg_tasks'].append(asyncio.create_task(_expire_payments_loop(_app)))
    _app['bg_tasks'].append(asyncio.create_task(_backup_loop(_app)))
    _app['bg_tasks'].append(asyncio.create_task(_expiry_notify_loop(_app)))

async def _expiry_notify_loop(_app):
    from services.notify import check_sub_expiry_notifications
    bot = _app['bot']
    while True:
        try:
            await check_sub_expiry_notifications(bot)
        except Exception as e:
            logger.error("Expiry notification error: %s", e)
        try:
            await asyncio.wait_for(asyncio.sleep(60), timeout=60)
        except asyncio.CancelledError:
            break

async def _expire_payments_loop(_app):
    from services.db import expire_old_payments
    while True:
        try:
            await expire_old_payments(30)
        except Exception as e:
            logger.error("Expire payments error: %s", e)
        try:
            await asyncio.wait_for(asyncio.sleep(300), timeout=300)
        except asyncio.CancelledError:
            break

async def _backup_loop(_app):
    import shutil
    from aiogram.types import BufferedInputFile
    from services.db import DB_PATH
    bot = _app['bot']
    admin_ids = settings.ADMIN_IDS
    backup_dir = os.path.join(os.path.dirname(DB_PATH or 'data'), 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    while True:
        try:
            if DB_PATH and os.path.exists(DB_PATH):
                ts = int(time.time())
                dst = os.path.join(backup_dir, f'bot_backup_{ts}.db')
                shutil.copy2(DB_PATH, dst)
                # Keep only last 48 backups
                backups = sorted([f for f in os.listdir(backup_dir) if f.startswith('bot_backup_')])
                while len(backups) > 48:
                    os.remove(os.path.join(backup_dir, backups.pop(0)))
                # Send silently to all admins
                for admin_id in admin_ids:
                    try:
                        with open(dst, 'rb') as f:
                            await bot.send_document(
                                admin_id,
                                BufferedInputFile(f.read(), filename=f'backup_{ts}.db'),
                                disable_notification=True
                            )
                    except Exception as e:
                        logger.warning("Failed to send backup to admin %s: %s", admin_id, e)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Backup error: %s", e)
        await asyncio.sleep(3600)

async def on_shutdown(_app):
    for task in _app.get('bg_tasks', []):
        task.cancel()
    await close_db()

def main():
    _validate_settings()
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    from aiogram import BaseMiddleware
    from aiogram.types import Message, CallbackQuery, TelegramObject
    from services.db import update_user_profile
    from typing import Callable, Dict, Any, Awaitable

    class SaveProfileMiddleware(BaseMiddleware):
        async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
        ) -> Any:
            user = None
            if isinstance(event, Message) and event.from_user:
                user = event.from_user
            elif isinstance(event, CallbackQuery) and event.from_user:
                user = event.from_user
            if user:
                await update_user_profile(
                    user.id,
                    username=user.username,
                    first_name=user.first_name,
                )
            return await handler(event, data)

    dp.message.middleware(SaveProfileMiddleware())
    dp.callback_query.middleware(SaveProfileMiddleware())
    dp.include_router(admin_router)
    register_router(dp)

    app = web.Application()
    app['bot'] = bot
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    setup_routes(app, bot, dp)

    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path='/telegram-webhook')

    if settings.ADMIN_BOT_TOKEN:
        from aiogram import Bot as AdminBot
        AdminBot(token=settings.ADMIN_BOT_TOKEN)

    web.run_app(app, host=settings.HOST, port=settings.PORT)

if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")