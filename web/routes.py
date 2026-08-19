import os
import secrets
from aiohttp import web, ClientSession, ClientTimeout
import json
import logging
import time
import hmac
import hashlib
from collections import defaultdict
from aiogram import Bot, Dispatcher
from services.db import (
    get_user, create_user, update_user, add_balance,
    create_payment, get_payment, update_payment_status,
    get_promocode, increment_promocode_uses, validate_promocode,
    discounted_price, record_promocode_use, user_used_promocode,
    clear_sub_notifications,
    TARIFF_INDEX_MAP, TARIFF_PRICE_MAP,
)
from services.xui_api import (
    add_client as xui_add_client,
    update_client_expiry as xui_update_expiry,
    sync_or_create_client as xui_sync_or_create,
    get_client_activity as xui_get_client_activity,
)
from services.payment import generate_payment_id
from services.auth import verify_telegram_init_data
from services.sub_convert import convert as sub_convert
from config import settings

log = logging.getLogger(__name__)

RATE_LIMIT = 60
RATE_WINDOW = 60
_rate_store = defaultdict(list)
_sub_cache: dict[str, str] = {}


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


def _require_user_id(request, data: dict | None = None) -> int | None:
    """Authenticated user id: verified Telegram initData, or plain userId in DEV_MODE only."""
    user_id = _get_user_id_from_request(request, data)
    if user_id is not None:
        return user_id
    if settings.DEV_MODE:
        try:
            raw = (data or {}).get('userId') or request.query.get('userId', 0)
            return int(raw) or None
        except (ValueError, TypeError):
            return None
    return None


def setup_routes(app: web.Application, bot: Bot, dp: Dispatcher):
    app.middlewares.append(_rate_middleware())

    async def index(request):
        try:
            with open('web/static/index.html', 'rb') as f:
                return web.Response(
                    body=f.read(), content_type='text/html',
                    headers={'Cache-Control': 'no-cache'},
                )
        except FileNotFoundError:
            return web.Response(text="BlackVPN API Operational", content_type='text/plain')
    app.router.add_get('/', index)

    async def api_user_data(request):
        user_id = _require_user_id(request)
        if user_id is None:
            return web.json_response({'error': 'Missing authentication'}, status=401)
        init_data = request.headers.get('X-Init-Data') or ''
        verified = verify_telegram_init_data(init_data, settings.TELEGRAM_BOT_TOKEN)
        telegram_user = verified['user'] if verified and isinstance(verified.get('user'), dict) else None

        user = await get_user(user_id)
        if user is None:
            await create_user(user_id)
            user = await get_user(user_id)
        if telegram_user:
            from services.db import update_user_profile
            await update_user_profile(
                user_id,
                username=telegram_user.get('username'),
                first_name=telegram_user.get('first_name'),
            )
        from services.db import get_referral_stats
        ref_stats = await get_referral_stats(user_id) if user else {'referrals': 0, 'earned': 0}
        # Subscription content is heavy (external fetch) — only on explicit request
        sub_content = ''
        if user and user.link and request.query.get('withSub') == '1':
            try:
                async with ClientSession() as sess:
                    async with sess.get(user.link, timeout=ClientTimeout(total=10)) as r:
                        if r.status == 200:
                            sub_content = await r.text()
            except Exception as e:
                log.warning("Failed to fetch sub content for user %s: %s", user_id, e)
        return web.json_response({
            'balance': user.balance,
            'daysLeft': user.days_left,
            'remainingStr': user.remaining_str,
            'subscriptionEnd': user.subscription or 0,
            'subscriptionStart': user.subscription_start or 0,
            'vpnKey': user.link or 'Не создан',
            'subContent': sub_content,
            'dailyPrice': settings.TARIFF_DAILY_PRICE,
            'banned': user.banned,
            'username': user.telegram_username if user else '',
            'firstName': user.first_name if user else '',
            'referralUrl': user.referral_url if user else '',
            'referralCount': ref_stats['referrals'],
            'referralEarnings': user.referral_earnings if user else 0,
            'trialUsed': user.trial_used if user else False,
        })

    async def api_config(request):
        """Public frontend config: single source of truth for tariffs/limits."""
        tariffs = [
            {
                'days': days,
                'price': TARIFF_PRICE_MAP[days],
                'perDay': round(TARIFF_PRICE_MAP[days] / days, 1),
            }
            for days in sorted(TARIFF_PRICE_MAP)
        ]
        return web.json_response({
            'tariffs': tariffs,
            'dailyPrice': settings.TARIFF_DAILY_PRICE,
            'minTopUp': 50,
            'topUpPresets': [50, 100, 200, 500, 1000, 2000],
            'paymentMethods': [
                {'id': 'platega_sbp', 'label': 'СБП', 'code': 2},
                {'id': 'platega_mir', 'label': 'МИР', 'code': 11},
                {'id': 'platega_crypto', 'label': 'Криптовалюта', 'code': 13},
            ],
            'referralReward': settings.REFERRAL_REWARD,
            'trialDays': 3,
        })

    async def api_user_devices(request):
        user_id = _require_user_id(request)
        if user_id is None:
            return web.json_response({'error': 'Missing authentication'}, status=401)
        user = await get_user(user_id)
        if user is None or not user.xui_email or not user.is_subscription_active:
            return web.json_response({
                'active': False, 'lastOnline': 0,
                'trafficUp': 0, 'trafficDown': 0, 'ips': [], 'devices': 0,
            })
        try:
            info = await xui_get_client_activity(user.xui_email)
        except Exception as e:
            log.warning(f"Failed to get client activity for {user.xui_email}: {e}")
            info = {"active": False, "lastOnline": 0, "trafficUp": 0, "trafficDown": 0, "ips": []}
        info["devices"] = len(info["ips"])
        return web.json_response(info)

    async def api_apply_promo(request):
        try:
            raw = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON'}, status=400)
        user_id = _require_user_id(request, raw)
        if user_id:
            user = await get_user(user_id)
            if user and user.banned:
                return web.json_response({'error': 'Вы заблокированы'}, status=403)
        code = raw.get('code', '').strip()
        if not code:
            return web.json_response({'error': 'Введите промокод'}, status=400)
        promo = await get_promocode(code)
        if promo is None:
            return web.json_response({'error': 'Промокод не найден'}, status=404)
        now = int(time.time() * 1000)
        if promo['expires_at'] and now > promo['expires_at']:
            return web.json_response({'error': 'Срок действия промокода истёк'}, status=400)
        if promo['max_uses'] is not None and promo['used_count'] >= promo['max_uses']:
            return web.json_response({'error': 'Промокод исчерпал лимит использований'}, status=400)
        if user_id and await user_used_promocode(code, user_id):
            return web.json_response({'error': 'Вы уже использовали этот промокод'}, status=400)
        grant_days = int(promo.get('grant_days') or 0)
        if grant_days:
            return web.json_response({
                'valid': True,
                'grantDays': grant_days,
            })
        discount = promo['discount_percent']
        applicable = []
        if promo['tariff_ids']:
            idxes = [int(x.strip()) for x in promo['tariff_ids'].split(',') if x.strip()]
        else:
            idxes = list(TARIFF_INDEX_MAP.keys())
        tariff_prices = {}
        for idx in idxes:
            days = TARIFF_INDEX_MAP.get(idx)
            if days:
                original = TARIFF_PRICE_MAP.get(days, 0)
                disc = discounted_price(days, discount)
                applicable.append(idx)
                tariff_prices[str(idx)] = {'days': days, 'original': original, 'discounted': disc}
        return web.json_response({
            'valid': True,
            'discountPercent': discount,
            'applicableTariffs': applicable,
            'tariffPrices': tariff_prices,
        })

    async def api_buy_subscription(request):
        try:
            raw = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        user_id = _require_user_id(request, raw)
        if user_id is None:
            return web.json_response({'error': 'Missing authentication'}, status=401)
        try:
            days = int(raw.get('days', 0))
        except (ValueError, TypeError):
            days = 0
        price = raw.get('price')
        promo_code = raw.get('promoCode', '').strip()
        if days <= 0:
            return web.json_response({'error': 'Invalid data'}, status=400)
        user = await get_user(user_id)
        if user is None:
            return web.json_response({'error': 'User not found'}, status=404)
        if user.banned:
            return web.json_response({'error': 'Вы заблокированы'}, status=403)
        promo = None
        if promo_code:
            promo = await get_promocode(promo_code)
            if promo is None:
                return web.json_response({'error': 'Промокод не найден'}, status=400)
            valid, err = await validate_promocode(promo, days, user_id)
            if not valid:
                return web.json_response({'error': err}, status=400)
        grant_days = int(promo.get('grant_days') or 0) if promo else 0
        is_grant = grant_days > 0
        if is_grant:
            days = grant_days
            total_price = 0
        elif days == 3 and (price is None or price == 0) and not user.trial_used:
            total_price = 0
        else:
            # Price is ALWAYS computed server-side; client-provided price is ignored
            total_price = TARIFF_PRICE_MAP.get(days) or days * settings.TARIFF_DAILY_PRICE
            # Apply promo code discount
            if promo_code and promo:
                discounted = discounted_price(days, promo['discount_percent'])
                if discounted > 0:
                    total_price = discounted
            if user.balance < total_price:
                return web.json_response(
                    {'error': f'Недостаточно средств. Нужно {total_price}₽'}, status=400
                )
            user.balance -= total_price
        now_ms = int(time.time() * 1000)
        add_ms = days * 86400000
        is_extension = bool(user.subscription and user.subscription > now_ms)
        new_sub = user.subscription + add_ms if is_extension else now_ms + add_ms
        user.subscription = new_sub
        if not is_extension:
            user.subscription_start = now_ms
        xui_error = None
        if settings.XUI_URL and settings.XUI_PASSWORD and (settings.XUI_INBOUND_ID is not None or settings.XUI_INBOUND_IDS):
            email = f'user_{user_id}'
            total_days = max(1, (new_sub - now_ms) // 86400000)
            try:
                if user.xui_email:
                    result = await xui_sync_or_create(user.xui_email, total_days, user.xui_inbound_id or None)
                    user.xui_email = result['email']
                    user.link = result['link']
                    if result.get('recreated'):
                        user.xui_uuid = result.get('uuid', user.xui_uuid)
                        user.xui_inbound_id = result.get('inbound_id', user.xui_inbound_id)
                else:
                    client = await xui_add_client(email, total_days, user.xui_inbound_id or None)
                    user.xui_uuid = client['uuid']
                    user.xui_email = client['email']
                    user.link = client['link']
                    user.xui_inbound_id = client['inbound_id']
            except Exception as e:
                log.error(f"3x-UI error for user {user_id}: {e}")
                xui_error = str(e)
                if total_price > 0:
                    user.balance += total_price
                user.subscription = user.subscription - add_ms if user.subscription else 0
                if not is_extension:
                    user.subscription_start = 0
                await update_user(user)
                return web.json_response(
                    {'error': f'Ошибка VPN-панели: {xui_error}'}, status=502
                )
        if not is_grant and days == 3 and (price is None or price == 0) and not user.trial_used:
            user.trial_used = True
        if promo_code:
            await increment_promocode_uses(promo_code)
            await record_promocode_use(promo_code, user_id)
        await update_user(user)
        await clear_sub_notifications(user_id)
        try:
            from bot.handlers import send_key_with_platforms
            if user.link:
                await send_key_with_platforms(bot, user_id, user.link, user.remaining_str)
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

        user_id = _require_user_id(request, raw)
        if user_id is None:
            return web.json_response({'error': 'Missing authentication'}, status=401)
        try:
            amount = float(raw.get('amount', 0))
        except (ValueError, TypeError):
            amount = 0
        method = raw.get('method', '')
        pay_method = raw.get('paymentMethod', 0)
        if amount < 50 or amount > 1000000:
            return web.json_response({'error': 'Invalid data. Minimum 50₽'}, status=400)

        user = await get_user(user_id)
        if user is None:
            await create_user(user_id)
        elif user.banned:
            return web.json_response({'error': 'Вы заблокированы'}, status=403)

        payment_id = generate_payment_id()
        await create_payment(payment_id, user_id, amount, method)

        payment_url = None
        if method.startswith('platega') and settings.PLATEGA_MERCHANT_ID and settings.PLATEGA_SECRET:
            try:
                from services.platega import create_transaction as platega_create
                desc = f"Пополнение BlackVPN на {amount}₽"
                result = await platega_create(
                    payment_id=payment_id,
                    amount=amount,
                    description=desc,
                    payment_method=pay_method,
                )
                payment_url = result.get("redirect", "")
            except Exception as e:
                log.error(f"Platega error: {e}")
                return web.json_response({'error': f'Ошибка платежной системы: {e}'}, status=502)

        return web.json_response({
            'success': True,
            'paymentId': payment_id,
            'amount': amount,
            'paymentUrl': payment_url or ''
        })

    app.router.add_get('/api/user-data', api_user_data)
    app.router.add_get('/api/config', api_config)
    app.router.add_get('/api/user-devices', api_user_devices)
    app.router.add_post('/api/apply-promo', api_apply_promo)
    app.router.add_post('/api/buy-subscription', api_buy_subscription)
    app.router.add_post('/api/create-payment', api_create_payment)

    async def api_sub_convert(request):
        user_id = _get_user_id_from_request(request)
        if user_id is None:
            try:
                user_id = int(request.query.get('userId', 0))
            except ValueError:
                pass
        if not user_id:
            try:
                user_id = int(request.match_info.get('user_id', 0))
            except (ValueError, TypeError):
                user_id = 0
        if not user_id:
            return web.json_response({'error': 'Missing auth'}, status=401)
        user = await get_user(user_id)
        if not user or not user.link:
            return web.json_response({'error': 'No subscription'}, status=404)
        try:
            async with ClientSession() as session:
                yaml = await sub_convert(session, user.link)
        except Exception as e:
            log.error("Sub convert error for user %s: %s", user_id, e)
            return web.json_response({'error': 'Conversion failed'}, status=500)
        if not yaml:
            return web.Response(text='No nodes found', status=404)
        return web.Response(text=yaml, content_type='text/plain; charset=utf-8')

    app.router.add_get('/api/sub-convert', api_sub_convert)
    app.router.add_get('/api/sub-convert/{user_id:[0-9]+}', api_sub_convert)

    async def api_sub_store_get(request):
        token = request.match_info.get('token', '')
        yaml = _sub_cache.get(token)
        if yaml is None:
            return web.Response(text='Not found', status=404)
        return web.Response(text=yaml, content_type='text/plain; charset=utf-8')

    async def api_sub_store_post(request):
        yaml = await request.text()
        if not yaml or len(yaml) < 10:
            return web.json_response({'error': 'Invalid YAML'}, status=400)
        token = secrets.token_hex(8)
        _sub_cache[token] = yaml
        return web.json_response({'token': token})

    app.router.add_get('/api/sub-store/{token}', api_sub_store_get)
    app.router.add_post('/api/sub-store', api_sub_store_post)

    async def api_sub_test(request):
        test_yaml = '''\
port: 7890
mode: Rule
proxies:
  - name: Test
    type: ss
    server: 127.0.0.1
    port: 8080
    cipher: chacha20-ietf-poly1305
    password: test
proxy-groups:
  - name: Proxy
    type: select
    proxies:
      - Test
      - DIRECT
  - name: DIRECT
    type: select
    proxies:
      - DIRECT
rules:
  - MATCH,Proxy
'''
        return web.Response(text=test_yaml, content_type='text/plain; charset=utf-8')

    app.router.add_get('/api/sub-test', api_sub_test)

    async def platega_webhook(request):
        # Rate-limit webhook (10 requests/minute/IP)
        ip = request.remote or 'unknown'
        now = time.time()
        wh_window = _rate_store[f'wh_{ip}']
        while wh_window and wh_window[0] < now - 60:
            wh_window.pop(0)
        if len(wh_window) >= 10:
            log.warning(f"Platega webhook rate limit exceeded from {ip}")
            return web.Response(status=429)
        wh_window.append(now)

        # Token verification
        if settings.PLATEGA_WEBHOOK_TOKEN:
            token = request.query.get('token', '')
            if not hmac.compare_digest(token, settings.PLATEGA_WEBHOOK_TOKEN):
                log.error(f"Platega webhook invalid token from {ip}")
                return web.Response(status=403)

        body_bytes = await request.read()
        if not body_bytes:
            log.warning(f"Platega webhook empty body from {ip}")
            return web.Response(status=400)

        if settings.PLATEGA_WEBHOOK_VERIFY and settings.PLATEGA_WEBHOOK_SECRET:
            sig_header = (
                request.headers.get('X-Signature', '')
                or request.headers.get('X-Webhook-Signature', '')
                or request.headers.get('Webhook-Signature', '')
                or ''
            )
            if not sig_header:
                log.warning("Platega webhook missing signature header (X-Signature / X-Webhook-Signature / Webhook-Signature)")
                return web.Response(status=400)

            expected = hmac.new(
                settings.PLATEGA_WEBHOOK_SECRET.encode(),
                body_bytes,
                hashlib.sha256,
            ).hexdigest()

            # Try hex match first, then base64
            match = hmac.compare_digest(expected, sig_header)
            if not match:
                try:
                    expected_b64 = hmac.new(
                        settings.PLATEGA_WEBHOOK_SECRET.encode(),
                        body_bytes,
                        hashlib.sha256,
                    ).digest()
                    import base64
                    match = hmac.compare_digest(base64.b64encode(expected_b64).decode(), sig_header)
                except Exception:
                    pass

            if not match:
                log.error("Platega webhook signature verification failed")
                return web.Response(status=400)

        try:
            raw = json.loads(body_bytes)
        except Exception:
            return web.Response(status=400)

        status = raw.get("status", "")
        payload_id = raw.get("payload", "")
        if status == "CONFIRMED" and payload_id:
            payment = await get_payment(payload_id)
            if not payment:
                return web.json_response({'error': 'Payment not found'}, status=404)
            if payment['status'] != 'pending':
                return web.json_response({'error': 'Already processed'}, status=409)
            wh_amount = float(raw.get("paymentDetails", {}).get("amount", 0))
            if wh_amount and abs(wh_amount - payment['amount']) > 0.01:
                log.error(f"Platega amount mismatch for {payload_id}: expected {payment['amount']}, got {wh_amount}")
                return web.Response(status=400)
            amount = wh_amount or payment['amount']
            await update_payment_status(payload_id, 'completed')
            user = await add_balance(payment['user_id'], amount)
            try:
                await bot.send_message(
                    payment['user_id'],
                    f"Баланс пополнен через Platega!\nСумма: {amount} ₽\nСтатус: Успешно",
                    parse_mode='HTML'
                )
            except Exception as e:
                log.error(f"Failed to notify user: {e}")
            # Notify referrer if this user was referred
            if user.referred_by:
                referrer = await get_user(user.referred_by)
                if referrer:
                    try:
                        reward = settings.REFERRAL_REWARD
                        await bot.send_message(
                            referrer.user_id,
                            f"Вам начислено {reward} ₽ за пополнение баланса приглашённым пользователем!",
                        )
                    except Exception as e:
                        log.error(f"Failed to notify referrer {referrer.user_id}: {e}")
        return web.Response(text='OK')

    app.router.add_post('/platega-webhook', platega_webhook)

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

    static_root = os.path.abspath('web/static')

    async def serve_static(request):
        rel = request.match_info.get('filename', 'index.html') or 'index.html'
        path = os.path.abspath(os.path.join(static_root, rel))
        if not path.startswith(static_root + os.sep):
            raise web.HTTPNotFound()
        try:
            with open(path, 'rb') as f:
                data = f.read()
        except (FileNotFoundError, IsADirectoryError):
            raise web.HTTPNotFound()
        filename = os.path.basename(path)
        ct = 'application/octet-stream'
        if filename.endswith('.css'):
            ct = 'text/css'
        elif filename.endswith('.js'):
            ct = 'application/javascript'
        elif filename.endswith('.html'):
            ct = 'text/html'
        # HTML revalidates every load; css/js are cacheable (bump query ?v= on deploy)
        cache = 'no-cache' if ct == 'text/html' else 'public, max-age=3600'
        return web.Response(body=data, content_type=ct, headers={'Cache-Control': cache})

    app.router.add_get('/{filename:.*}', serve_static)

    return app