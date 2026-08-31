import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import MenuButtonWebApp, WebAppInfo
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

from bot.admin_handlers import router as admin_router
from bot.handlers import register_router
from config import settings
from services.db import close_db, init_db
from web.routes import setup_routes

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def _expire_payments_loop():
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


async def _expiry_notify_loop(bot):
    from services.notify import check_sub_expiry_notifications
    while True:
        try:
            await check_sub_expiry_notifications(bot)
        except Exception as e:
            logger.error("Expiry notification error: %s", e)
        try:
            await asyncio.wait_for(asyncio.sleep(60), timeout=60)
        except asyncio.CancelledError:
            break


def _start_background_tasks(bot) -> list[asyncio.Task]:
    return [
        asyncio.create_task(_expire_payments_loop()),
        asyncio.create_task(_expiry_notify_loop(bot)),
    ]


async def _stop_background_tasks(tasks: list[asyncio.Task]):
    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


async def on_startup(_app):
    await init_db()
    if settings.WEBHOOK_ENABLED:
        bot = _app['bot']
        await bot.delete_webhook(drop_pending_updates=True)
        webhook_url = f"{settings.BASE_URL}/telegram-webhook"
        await bot.set_webhook(webhook_url)
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text=settings.APP_NAME,
                web_app=WebAppInfo(url=f"{settings.BASE_URL}/"),
            )
        )
        logger.info("Webhook set to %s", webhook_url)
        _app['bg_tasks'] = _start_background_tasks(bot)
    else:
        logger.info("Webhook mode disabled; long polling mode active")


async def on_shutdown(_app):
    await _stop_background_tasks(_app.get('bg_tasks', []))
    await close_db()


def _build_dispatcher() -> Dispatcher:
    from aiogram import BaseMiddleware
    from aiogram.types import CallbackQuery, Message, TelegramObject
    from typing import Any, Awaitable, Callable, Dict

    from services.db import update_user_profile

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

    dp = Dispatcher()
    dp.message.middleware(SaveProfileMiddleware())
    dp.callback_query.middleware(SaveProfileMiddleware())
    dp.include_router(admin_router)
    register_router(dp)
    return dp


def main():
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN is not set; the bot will not start.")

    dp = _build_dispatcher()
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN) if settings.TELEGRAM_BOT_TOKEN else None

    if not settings.WEBHOOK_ENABLED:
        # Development mode: Telegram long polling + local web app for the WebApp UI.
        async def _polling():
            await asyncio.sleep(0.5)
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)

        async def _dev_main():
            app = web.Application()
            app['bot'] = bot
            await init_db()
            setup_routes(app, bot, dp)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, settings.HOST, settings.PORT)
            await site.start()
            polling_task = asyncio.create_task(_polling())
            bg_tasks = _start_background_tasks(bot)
            try:
                await asyncio.Event().wait()
            except (KeyboardInterrupt, SystemExit):
                pass
            finally:
                polling_task.cancel()
                await _stop_background_tasks(bg_tasks)
                await close_db()
                await runner.cleanup()

        try:
            asyncio.run(_dev_main())
        except KeyboardInterrupt:
            logger.info("Bot stopped")
        return

    if bot is None:
        logger.error("WEBHOOK_ENABLED requires TELEGRAM_BOT_TOKEN.")
        raise SystemExit(1)

    app = web.Application()
    app['bot'] = bot
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    setup_routes(app, bot, dp)

    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path='/telegram-webhook')

    web.run_app(app, host=settings.HOST, port=settings.PORT)


if __name__ == '__main__':
    main()