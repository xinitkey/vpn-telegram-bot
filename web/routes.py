from aiohttp import web
import json
import logging
import time
from collections import defaultdict
from aiogram import Bot, Dispatcher
from services.db import (
    get_user, create_user, update_user, add_balance,
    create_payment, get_payment, update_payment_status
)
from services.xui_api import (
    add_client as xui_add_client,
    update_client_expiry as xui_update_expiry,
    build_link_for_email as xui_build_link_for_email,
)
from services.payment import generate_payment_id
from services.auth import verify_telegram_init_data, verify_cryptomus_signature
from config import settings

log = logging.getLogger(__name__)

RATE_LIMIT = 60
RATE_WINDOW = 60
_rate_store = defaultdict(list)


def _rate_middleware():
    @web.middleware
    async def middleware(request, handler):
        path = request.path
        if not path.startswith('/api/'):
            return await handler(request)
        ip = request.remote or 'unknown'
        now = time.time()
        window = _rate_store[ip]
        while window and window[0] < now - RATE_WINDOW:
            window.pop(0)
        if len(window) >= RATE_LIMIT:
            return web.json_response({'error': 'Too many requests'}, status=429)
        window.append(now)
        return await handler(request)
    return middleware


def _get_user_id_from_request(request, data: dict | None = None) -> int | None:
    init_data = request.headers.get('X-Init-Data') or (data or {}).get('initData', '')
    if init_data:
        verified = verify_telegram_init_data(init_data, settings.TELEGRAM_BOT_TOKEN)
        if verified and isinstance(verified.get('user'), dict):
            return verified['user'].get('id')
    return None


def setup_routes(app: web.Application, bot: Bot, dp: Dispatcher):
    app.middlewares.append(_rate_middleware())

    async def index(request):
        try:
            with open('web/static/index.html', 'rb') as f:
                return web.Response(body=f.read(), content_type='text/html')
        except FileNotFoundError:
            return web.Response(text="BlackVPN API Operational", content_type='text/plain')
    app.router.add_get('/', index)

    async def api_user_data(request):
        user_id = _get_user_id_from_request(request)
        if user_id is None:
            try:
                user_id = int(request.query.get('userId', 0))
            except ValueError:
                return web.json_response({'error': 'Invalid user_id'}, status=400)
            if user_id == 0:
                return web.json_response({'error': 'Missing authentication'}, status=401)

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

    async def api_buy_subscription(request):
        try:
            raw = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        verified_id = _get_user_id_from_request(request, raw)
        user_id = verified_id or int(raw.get('userId', 0))
        days = int(raw.get('days', 0))
        price = raw.get('price')
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
        user.balance -= total_price
        now_ms = int(time.time() * 1000)
        add_ms = days * 86400000
        new_sub = user.subscription + add_ms if user.subscription and user.subscription > now_ms else now_ms + add_ms
        user.subscription = new_sub
        xui_error = None
        if settings.XUI_URL and settings.XUI_PASSWORD and settings.XUI_INBOUND_ID is not None:
            email = f'user_{user_id}'
            total_days = max(1, (new_sub - now_ms) // 86400000)
            try:
                if user.xui_email:
                    await xui_update_expiry(user.xui_email, total_days)
                    user.link = await xui_build_link_for_email(user.xui_email)
                else:
                    client = await xui_add_client(email, total_days)
                    user.xui_uuid = client['uuid']
                    user.xui_email = client['email']
                    user.link = client['link']
            except Exception as e:
                log.error(f"3x-UI error for user {user_id}: {e}")
                xui_error = str(e)
                user.balance += total_price
                user.subscription = user.subscription - add_ms if user.subscription else 0
                await update_user(user)
                return web.json_response(
                    {'error': f'Ошибка VPN-панели: {xui_error}'}, status=502
                )
        await update_user(user)
        try:
            await bot.send_message(
                user_id,
                f"<b>Тариф успешно активирован!</b>\n\n"
                f"<b>Ваш ключ:</b>\n"
                f"{user.link or '—'}\n\n"
                f"<b>Дней осталось:</b> {user.days_left}\n\n"
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
            log.error(f"Failed to send key to user {user_id}: {e}")
        resp = {
            'success': True,
            'balance': user.balance,
            'subscription': user.subscription,
            'link': user.link or ''
        }
        if xui_error:
            resp['xui_warning'] = xui_error
        return web.json_response(resp)

    async def api_create_payment(request):
        try:
            raw = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        verified_id = _get_user_id_from_request(request, raw)
        user_id = verified_id or int(raw.get('userId', 0))
        amount = float(raw.get('amount', 0))
        method = raw.get('method', '')
        if not user_id or amount < 50:
            return web.json_response({'error': 'Invalid data. Minimum 50₽'}, status=400)

        user = await get_user(user_id)
        if user is None:
            await create_user(user_id)

        payment_id = generate_payment_id()
        await create_payment(payment_id, user_id, amount, method)

        payment_url = None
        if method == 'crypto':
            payment_url = f"https://t.me/CryptoBot?start={payment_id}"
        elif method == 'cryptomus' and settings.CRYPTOMUS_LINK:
            base = settings.CRYPTOMUS_LINK.rstrip('/')
            payment_url = f"{base}?amount={amount}&order_id={payment_id}"

        return web.json_response({
            'success': True,
            'paymentId': payment_id,
            'amount': amount,
            'paymentUrl': payment_url or ''
        })

    app.router.add_get('/api/user-data', api_user_data)
    app.router.add_post('/api/buy-subscription', api_buy_subscription)
    app.router.add_post('/api/create-payment', api_create_payment)

    async def cryptomus_webhook(request):
        try:
            raw = await request.json()
        except Exception:
            return web.Response(status=400)

        if settings.CRYPTOMUS_SECRET_KEY:
            body_copy = dict(raw)
            if not verify_cryptomus_signature(body_copy, settings.CRYPTOMUS_SECRET_KEY):
                log.warning("Cryptomus webhook: invalid signature")
                return web.Response(status=403)

        amount = float(raw.get('amount', 0))
        txn_id = raw.get('txn_id', '')
        if not txn_id:
            return web.Response(status=400)

        payment = await get_payment(txn_id)
        if not payment:
            return web.Response(status=404)
        if payment['status'] != 'pending':
            return web.Response(text='OK')
        if amount < payment['amount']:
            return web.Response(text='OK')

        await update_payment_status(txn_id, 'completed')
        await add_balance(payment['user_id'], amount)
        try:
            await bot.send_message(
                payment['user_id'],
                f"💰 Баланс пополнен через Cryptomus!\nСумма: {amount} ₽\nСтатус: Успешно",
                parse_mode='HTML'
            )
        except Exception as e:
            log.error(f"Failed to notify user: {e}")
        return web.Response(text='OK')

    async def cryptobot_webhook(request):
        try:
            raw = await request.json()
        except Exception:
            return web.Response(status=400)

        update = raw.get('payload', {})
        status = update.get('status', '')
        payload_id = update.get('payload', '')
        if status == 'active' and payload_id:
            payment = await get_payment(payload_id)
            if payment and payment['status'] == 'pending':
                amount = float(update.get('amount', payment['amount']))
                await update_payment_status(payload_id, 'completed')
                await add_balance(payment['user_id'], amount)
                try:
                    await bot.send_message(
                        payment['user_id'],
                        f"💰 Баланс пополнен через CryptoBot!\nСумма: {amount} USD\nСтатус: Успешно",
                    )
                except Exception as e:
                    log.error(f"Failed to notify user: {e}")
        return web.Response(text='OK')

    app.router.add_post('/cryptomus-webhook', cryptomus_webhook)
    app.router.add_post('/cryptobot-webhook', cryptobot_webhook)

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

    async def serve_static(request):
        filename = request.match_info.get('filename', 'index.html') or 'index.html'
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