import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
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

async def on_startup(bot: Bot):
    await bot.delete_webhook(drop_pending_updates=True)
    await init_db()
    webhook_url = f"{settings.BASE_URL}/telegram-webhook"
    await bot.set_webhook(webhook_url)
    logger.info("Webhook set to %s", webhook_url)

async def on_shutdown(bot: Bot):
    await close_db()

def main():
    _validate_settings()
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    register_router(dp)

    app = web.Application()
    setup_routes(app, bot, dp)

    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path='/telegram-webhook')

    if settings.ADMIN_BOT_TOKEN:
        from aiogram import Bot as AdminBot
        admin_bot = AdminBot(token=settings.ADMIN_BOT_TOKEN)

    web.run_app(app, host=settings.HOST, port=settings.PORT)

if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")