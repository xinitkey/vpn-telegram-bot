import asyncio
import uuid as uuid_pkg
import json
import time
import logging
from typing import Optional
from config.settings import settings
from urllib.parse import quote, urlparse
from aiohttp import CookieJar, ClientSession, ClientError

logger = logging.getLogger(__name__)

_inbound_cache: dict[int, dict] = {}
_inbound_cache_ts: dict[int, float] = {}
_INBOUND_CACHE_TTL = 30

_sub_settings_cache: Optional[dict] = None
_sub_settings_cache_ts: float = 0
_SUB_SETTINGS_CACHE_TTL = 300

_session_cookies: Optional[dict] = None
_csrf_token: Optional[str] = None
_session_lock = asyncio.Lock()


def _make_session() -> ClientSession:
    return ClientSession(cookie_jar=CookieJar(unsafe=True))


async def _get_session() -> tuple[dict, str]:
    global _session_cookies, _csrf_token
    base = settings.XUI_URL.rstrip('/')
    async with _session_lock:
        if _session_cookies and _csrf_token:
            return _session_cookies, _csrf_token
        if _session_cookies and not _csrf_token:
            csrf = await _fetch_csrf(_session_cookies)
            if csrf:
                _csrf_token = csrf
                return _session_cookies, csrf

        async with asyncio.timeout(15):
            async with _make_session() as sess:
                async with sess.get(f"{base}/") as resp:
                    html = await resp.text()
                    if 'csrf-token" content="' not in html:
                        raise RuntimeError("CSRF token not found in 3x-UI login page")
                    csrf = html.split('csrf-token" content="')[1].split('"')[0]
                async with sess.post(
                    f"{base}/login",
                    data={"username": settings.XUI_USERNAME, "password": settings.XUI_PASSWORD},
                    headers={
                        "x-csrf-token": csrf,
                        "X-Requested-With": "XMLHttpRequest",
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    },
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"3x-UI login failed ({resp.status}): {text[:200]}")
                    data = await resp.json(content_type=None)
                    if not data.get("success"):
                        raise RuntimeError(f"3x-UI login failed: {data.get('msg', 'unknown')}")

                cookies = {}
                for cookie in sess.cookie_jar:
                    cookies[cookie.key] = cookie.value
                _session_cookies = cookies

                api_csrf = await _fetch_csrf(cookies)
                _csrf_token = api_csrf or ""

                logger.info("3x-UI session established")
                return cookies, _csrf_token


async def _fetch_csrf(cookies: dict) -> str:
    base = settings.XUI_URL.rstrip('/')
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
    try:
        async with _make_session() as sess:
            async with sess.get(
                f"{base}/csrf-token",
                headers={"Cookie": cookie_header, "X-Requested-With": "XMLHttpRequest"},
            ) as resp:
                data = await resp.json(content_type=None)
                token = data.get("obj", "")
                if token:
                    return token
        async with _make_session() as sess:
            async with sess.get(
                f"{base}/panel/",
                headers={"Cookie": cookie_header},
            ) as resp:
                html = await resp.text()
                if 'csrf-token" content="' in html:
                    return html.split('csrf-token" content="')[1].split('"')[0]
    except Exception:
        pass
    return ""


async def _refresh_csrf() -> str:
    global _csrf_token, _session_cookies
    if not _session_cookies:
        return ""
    csrf = await _fetch_csrf(_session_cookies)
    _csrf_token = csrf
    return csrf


async def _invalidate_session():
    global _session_cookies, _csrf_token
    _session_cookies = None
    _csrf_token = None


async def _request(method: str, path: str, data: dict | None = None, retries: int = 2) -> dict:
    base = settings.XUI_URL.rstrip('/')
    url = f"{base}{path}"
    is_mutation = method.upper() in ("POST", "PUT", "PATCH", "DELETE")
    for attempt in range(1 + retries):
        try:
            cookies, csrf = await _get_session()
            if not cookies:
                raise RuntimeError("3x-UI session invalid (empty cookies)")
            cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
            headers = {
                "Cookie": cookie_header,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/json",
            }
            if is_mutation and csrf:
                headers["X-CSRF-Token"] = csrf
            async with _make_session() as sess:
                async with sess.request(method, url, headers=headers, json=data) as resp:
                    text = await resp.text()
                    if resp.status == 403:
                        new_csrf = await _refresh_csrf()
                        if new_csrf and is_mutation:
                            headers["X-CSRF-Token"] = new_csrf
                            async with _make_session() as retry_sess:
                                async with retry_sess.request(method, url, headers=headers, json=data) as retry_resp:
                                    text = await retry_resp.text()
                                    if retry_resp.status == 403:
                                        await _invalidate_session()
                                        if attempt < retries:
                                            logger.warning("3x-UI CSRF expired, re-logging in...")
                                            continue
                                        raise RuntimeError(f"3x-UI access denied after CSRF refresh: {text[:200]}")
                                    resp = retry_resp
                        else:
                            await _invalidate_session()
                            if attempt < retries:
                                logger.warning("3x-UI session expired, re-logging in...")
                                continue
                            raise RuntimeError(f"3x-UI access denied: {text[:200]}")
                    if resp.status >= 500:
                        raise RuntimeError(f"3x-UI server error ({resp.status}): {text[:300]}")
                    if not text:
                        return {}
                    result = json.loads(text)
                    if not result.get("success"):
                        msg = result.get('msg', 'unknown')
                        raise RuntimeError(f"3x-UI error: {msg}")
                    obj = result.get("obj")
                    return obj if obj is not None else {}
        except (ClientError, asyncio.TimeoutError, RuntimeError) as e:
            if attempt < retries and "login" not in str(e).lower() and "session invalid" not in str(e).lower():
                wait = 2 ** attempt
                logger.warning("3x-UI request failed (attempt %d/%d): %s. Retrying in %ds...", attempt + 1, retries, e, wait)
                await asyncio.sleep(wait)
            else:
                raise


async def get_client_activity(email: str) -> dict:
    """Return dict with activity info: active, lastOnline, trafficUp, trafficDown, ips."""
    result = {"active": False, "lastOnline": 0, "trafficUp": 0, "trafficDown": 0, "ips": []}

    # 1. Try clientIps endpoint
    try:
        data = await _request("POST", f"/panel/api/inbounds/clientIps/{quote(email)}")
        if isinstance(data, dict):
            ips = data.get("ips", data.get("obj", []))
            if isinstance(ips, list):
                result["ips"] = [str(ip) for ip in ips if ip]
    except Exception:
        pass

    # 2. Get activity from clientStats
    now_ms = int(time.time() * 1000)
    for iid in settings.XUI_INBOUND_IDS:
        inbound = await get_inbound_info(iid)
        for client in inbound.get("clientStats", []):
            if isinstance(client, dict) and client.get("email") == email:
                result["trafficUp"] = client.get("up", 0)
                result["trafficDown"] = client.get("down", 0)
                last = client.get("lastOnline", 0)
                result["lastOnline"] = last if isinstance(last, (int, float)) else 0
                if not result["ips"]:
                    for field in ("ips", "ip"):
                        raw = client.get(field)
                        if isinstance(raw, list):
                            result["ips"] = [str(ip) for ip in raw if ip]
                            break
                        if isinstance(raw, str) and raw:
                            result["ips"] = [raw]
                            break
                break

    # Active = has traffic in last 24h or has IPs
    total = result["trafficUp"] + result["trafficDown"]
    result["active"] = bool(result["ips"]) or (total > 0 and result["lastOnline"] > now_ms - 86400000)
    return result


async def add_client(email: str, days: int, inbound_id: int | None = None) -> dict[str, str]:
    ids = settings.XUI_INBOUND_IDS
    if not ids:
        raise RuntimeError("No inbounds configured (XUI_INBOUND_IDS)")
    uid = str(uuid_pkg.uuid4())
    sub_id = str(uuid_pkg.uuid4())[:16]
    expiry = int(time.time() * 1000) + days * 86400000
    client = {
        "email": email,
        "subId": sub_id,
        "id": uid,
        "flow": "",
        "totalGB": 0,
        "expiryTime": expiry,
        "enable": True,
        "limitIp": 0,
        "tgId": 0,
    }
    payload = {
        "client": client,
        "inboundIds": ids,
    }
    try:
        await _request("POST", "/panel/api/clients/add", data=payload)
    except RuntimeError as e:
        err_str = str(e)
        if "email already in use" in err_str or "already exists" in err_str:
            logger.warning("Email %s already exists in panel, removing and retrying...", email)
            try:
                await _request("POST", f"/panel/api/clients/del/{quote(email)}")
            except Exception:
                pass
            await _request("POST", "/panel/api/clients/add", data=payload)
        else:
            raise
    link = await _build_link(uid, email, sub_id)
    return {"uuid": uid, "email": email, "link": link, "inbound_id": ids[0]}


async def sync_or_create_client(email: str, days: int, inbound_id: int | None = None) -> dict[str, str]:
    """Try to update client expiry. If client was deleted from panel, re-create it."""
    try:
        await update_client_expiry(email, days)
        link = await build_link_for_email(email, inbound_id)
        return {"email": email, "link": link, "recreated": False}
    except (RuntimeError, Exception) as e:
        err = str(e).lower()
        if "record not found" in err or "client not found" in err:
            logger.warning("Client %s not found in panel, re-creating...", email)
            # Remove stale email if partial data exists, then create fresh
            try:
                await _request("POST", f"/panel/api/clients/del/{quote(email)}")
            except Exception:
                pass
            result = await add_client(email, days, inbound_id)
            result["recreated"] = True
            return result
        raise


async def update_client_expiry(email: str, days: int):
    expiry = int(time.time() * 1000) + days * 86400000
    payload = {
        "email": email,
        "enable": True,
        "expiryTime": expiry,
    }
    await _request("POST", f"/panel/api/clients/update/{quote(email)}", data=payload)


async def remove_client(email: str):
    await _request("POST", f"/panel/api/clients/del/{quote(email)}")


async def get_client_subid(email: str, inbound_id: int | None = None) -> str | None:
    ids = [inbound_id] if inbound_id else settings.XUI_INBOUND_IDS
    for iid in ids:
        inbound = await get_inbound_info(iid)
        clients = inbound.get("clientStats", [])
        if not clients:
            raw = inbound.get("settings", "")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = {}
            clients = raw.get("clients", []) if isinstance(raw, dict) else []
        for client in clients:
            if isinstance(client, dict) and client.get("email") == email:
                return str(client.get("subId", ""))
    return None


async def get_client_expiry(email: str, inbound_id: int | None = None) -> int | None:
    ids = [inbound_id] if inbound_id else settings.XUI_INBOUND_IDS
    for iid in ids:
        inbound = await get_inbound_info(iid)
        clients = inbound.get("clientStats", [])
        if not clients:
            raw = inbound.get("settings", "")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = {}
            clients = raw.get("clients", []) if isinstance(raw, dict) else []
        for client in clients:
            if isinstance(client, dict) and client.get("email") == email:
                et = client.get("expiryTime")
                if et:
                    return int(et)
    return None


async def build_link_for_email(email: str, inbound_id: int | None = None) -> str:
    sub_id = await get_client_subid(email, inbound_id)
    if not sub_id:
        raise RuntimeError(f"Client not found in panel: {email}")
    return await _build_link("", email, sub_id)


async def get_inbound_info(inbound_id: int) -> dict:
    global _inbound_cache, _inbound_cache_ts
    now = time.time()
    cached = _inbound_cache.get(inbound_id)
    if cached is not None and (now - _inbound_cache_ts.get(inbound_id, 0)) < _INBOUND_CACHE_TTL:
        return cached
    data = await _request("GET", f"/panel/api/inbounds/get/{inbound_id}")
    _inbound_cache[inbound_id] = data
    _inbound_cache_ts[inbound_id] = now
    return data


async def _get_sub_settings() -> dict:
    global _sub_settings_cache, _sub_settings_cache_ts
    now = time.time()
    if _sub_settings_cache is not None and (now - _sub_settings_cache_ts) < _SUB_SETTINGS_CACHE_TTL:
        return _sub_settings_cache
    try:
        data = await _request("GET", "/panel/api/settings")
        if data:
            _sub_settings_cache = data
            _sub_settings_cache_ts = now
        return data
    except Exception as e:
        logger.warning(f"Failed to get panel settings: {e}")
        return _sub_settings_cache or {}


async def _build_link(uuid: str, email: str, sub_id: str) -> str:
    if settings.XUI_SUB_URL:
        return f"{settings.XUI_SUB_URL}/{sub_id}"
    sub_settings = await _get_sub_settings()
    sub_url = (sub_settings.get("subURL") or "").rstrip('/')
    if sub_url:
        return f"{sub_url}/{sub_id}"
    parsed = urlparse(settings.XUI_URL)
    scheme = parsed.scheme or "http"
    host = sub_settings.get("webDomain") or sub_settings.get("subDomain") or parsed.hostname or ""
    if not host:
        host = sub_settings.get("webDomain") or sub_settings.get("subDomain") or parsed.hostname or "127.0.0.1"
    port = sub_settings.get("subPort") or 2096
    sub_path = (sub_settings.get("subPath") or "/use_happ/").strip('/')
    return f"{scheme}://{host}:{port}/{sub_path}/{sub_id}"
