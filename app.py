import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from bot.handlers import register_router
from web.routes import setup_routes
from config import settings
from services.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def on_startup(bot: Bot):
    await bot.delete_webhook(drop_pending_updates=True)
    # Initialize database
    await init_db()
    # Set webhook (if using webhook mode)
    webhook_url = f"{settings.BASE_URL}/telegram-webhook"
    await bot.set_webhook(webhook_url)
    logger.info(f"Webhook set to {webhook_url}")

def main():
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    # Register routers/handlers
    register_router(dp)

    # Create aiohttp application for serving static files and API routes
    app = web.Application()
    setup_routes(app, bot, dp)

    # Setup aiogram webhook handler
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path='/telegram-webhook')

    # Optional admin bot webhook (if separate token)
    if settings.ADMIN_BOT_TOKEN:
        from aiogram import Bot as AdminBot
        admin_bot = AdminBot(token=settings.ADMIN_BOT_TOKEN)
        # For simplicity we can reuse same dispatcher but filter by admin ID via middleware
        # We'll skip for now.

    # Start web server
    web.run_app(app, host=settings.HOST, port=settings.PORT)

if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")