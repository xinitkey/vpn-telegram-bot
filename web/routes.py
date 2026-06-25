from aiohttp import web
import json
import logging
import time
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from services.db import (
    get_user, create_user, update_user, add_balance, set_subscription,
    create_payment, get_payment, update_payment_status
)
from services.xui_api import (
    add_client as xui_add_client,
    update_client_expiry as xui_update_expiry,
)
from config import settings

log = logging.getLogger(__name__)

def setup_routes(app: web.Application, bot: Bot, dp: Dispatcher):
    # Root endpoint
    async def index(request):
        return web.Response(text="BlackVPN API Operational", content_type='text/plain')
    app.router.add_get('/', index)

    # API: get user data
    async def api_user_data(request):
        try:
            user_id = int(request.query.get('user_id', 0))
        except ValueError:
            return web.json_response({'error': 'Invalid user_id'}, status=400)
        if user_id == 0:
            return web.json_response({'error': 'Missing user_id'}, status=400)
        user = await get_user(user_id)
        if user is None:
            await create_user(user_id)
            user = await get_user(user_id)
        return web.json_response({
            'balance': user.balance,
            'daysLeft': user.days_left,
            'vpnKey': user.link or 'Не создан',
            'dailyPrice': settings.TARIFF_DAILY_PRICE
        })

    # API: buy subscription with balance
    async def api_buy_subscription(request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON'}, status=400)
        user_id = int(data.get('userId', 0))
        days = int(data.get('days', 0))
        price = data.get('price')
        if not user_id or days <= 0:
            return web.json_response({'error': 'Invalid data'}, status=400)
        user = await get_user(user_id)
        if user is None:
            return web.json_response({'error': 'User not found'}, status=404)
        total_price = price if price is not None else days * settings.TARIFF_DAILY_PRICE
        if user.balance < total_price:
            return web.json_response(
                {'error': f'Недостаточно средств. Нужно {total_price}₽'}, status=400
            )
        # Deduct balance
        user.balance -= total_price
        # Update subscription timestamp
        now_ms = int(time.time() * 1000)
        add_ms = days * 86400000
        new_sub = user.subscription + add_ms if user.subscription and user.subscription > now_ms else now_ms + add_ms
        user.subscription = new_sub
        # Update 3x-UI if configured
        if settings.XUI_URL and settings.XUI_API_TOKEN and settings.XUI_INBOUND_ID is not None:
            email = f'user_{user_id}'
            total_days = max(1, (new_sub - now_ms) // 86400000)
            if user.xui_email:
                await xui_update_expiry(user.xui_email, total_days)
            else:
                client = await xui_add_client(email, total_days)
                user.xui_uuid = client['uuid']
                user.xui_email = client['email']
                user.link = client['link']
                user.vpn_key = client['link']
        await update_user(user)
        return web.json_response({
            'success': True,
            'balance': user.balance,
            'subscription': user.subscription,
            'link': user.link or ''
        })

    # API: create payment (returns payment ID)
    async def api_create_payment(request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON'}, status=400)
        user_id = int(data.get('userId', 0))
        amount = float(data.get('amount', 0))
        method = data.get('method', '')
        if not user_id or amount < 50:
            return web.json_response({'error': 'Invalid data. Minimum 50₽'}, status=400)
        user = await get_user(user_id)
        if user is None:
            await create_user(user_id)
            user = await get_user(user_id)
        import uuid
        payment_id = f'pay_{int(time.time())}_{uuid.uuid4().hex[:8]}'
        await create_payment(payment_id, user_id, amount, method)
        return web.json_response({
            'success': True,
            'paymentId': payment_id,
            'amount': amount
        })

    app.router.add_get('/api/user-data', api_user_data)
    app.router.add_post('/api/buy-subscription', api_buy_subscription)
    app.router.add_post('/api/create-payment', api_create_payment)

    # Telegram webhook
    async def telegram_webhook(request):
        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400)
        update = Update(**data)
        await dp.feed_update(bot, update)
        return web.Response(text='OK')

    # Cryptomus webhook
    async def cryptomus_webhook(request):
        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400)
        amount = float(data.get('amount', 0))
        txn_id = data.get('txn_id', '')
        if not txn_id:
            return web.Response(status=400)
        payment = await get_payment(txn_id)
        if not payment:
            return web.Response(status=404)
        if payment['status'] != 'pending':
            return web.Response(text='OK')
        if amount < payment['amount']:
            return web.Response(text='OK')
        # Mark as completed and add balance
        await update_payment_status(txn_id, 'completed')
        await add_balance(payment['user_id'], amount)
        # Notify user
        try:
            await bot.send_message(
                payment['user_id'],
                f"💰 Баланс пополнен через Cryptomus!\nСумма: {amount} ₽\nСтатус: Успешно",
                parse_mode='HTML'
            )
        except Exception as e:
            log.error(f"Failed to notify user: {e}")
        return web.Response(text='OK')

    app.router.add_post('/telegram-webhook', telegram_webhook)
    app.router.add_post('/cryptomus-webhook', cryptomus_webhook)

    # Serve privacy and terms pages (extensionless)
    async def serve_privacy(request):
        try:
            with open('web/static/privacy.html', 'rb') as f:
                data = f.read()
        except FileNotFoundError:
            raise web.HTTPNotFound()
        return web.Response(body=data, content_type='text/html')

    async def serve_terms(request):
        try:
            with open('web/static/terms.html', 'rb') as f:
                data = f.read()
        except FileNotFoundError:
            raise web.HTTPNotFound()
        return web.Response(body=data, content_type='text/html')

    app.router.add_get('/privacy', serve_privacy)
    app.router.add_get('/terms', serve_terms)

    # Serve static files (must be last)
    async def serve_static(request):
        filename = request.match_info.get('filename', 'index.html')
        # Basic security
        if '..' in filename or '/' in filename:
            raise web.HTTPNotFound()
        try:
            with open(f'web/static/{filename}', 'rb') as f:
                data = f.read()
        except FileNotFoundError:
            raise web.HTTPNotFound()
        ct = 'application/octet-stream'
        if filename.endswith('.css'):
            ct = 'text/css'
        elif filename.endswith('.js'):
            ct = 'application/javascript'
        elif filename.endswith('.html'):
            ct = 'text/html'
        return web.Response(body=data, content_type=ct)

    app.router.add_get('/{filename:.*}', serve_static)

    return app