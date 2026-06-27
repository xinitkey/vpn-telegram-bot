import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from bot.handlers import register_router
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
    ('XUI_INBOUND_ID', 'XUI_INBOUND_ID'),
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
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    await init_db()
    webhook_url = f"{settings.BASE_URL}/telegram-webhook"
    await bot.set_webhook(webhook_url)
    logger.info("Webhook set to %s", webhook_url)
    await bot.session.close()

async def on_shutdown(_app):
    await close_db()

def main():
    _validate_settings()
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    register_router(dp)

    app = web.Application()
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