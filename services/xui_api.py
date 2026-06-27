import asyncio
import uuid as uuid_pkg
import json
import time
import logging
from typing import Optional
from config.settings import settings
from urllib.parse import quote, urlparse

logger = logging.getLogger(__name__)

_inbound_cache: Optional[dict] = None
_inbound_cache_ts: float = 0
_INBOUND_CACHE_TTL = 300

_session_cookies: Optional[dict] = None
_session_lock = asyncio.Lock()


async def _get_session() -> dict:
    global _session_cookies
    base = settings.XUI_URL.rstrip('/')
    async with _session_lock:
        if _session_cookies:
            return _session_cookies
        async with asyncio.timeout(15):
            import aiohttp
            async with aiohttp.ClientSession() as sess:
                async with sess.get(f"{base}/") as resp:
                    html = await resp.text()
                    csrf = html.split('csrf-token" content="')[1].split('"')[0]
                async with sess.post(
                    f"{base}/login",
                    json={"username": settings.XUI_USERNAME, "password": settings.XUI_PASSWORD},
                    headers={"x-csrf-token": csrf, "Content-Type": "application/json"},
                ) as resp:
                    data = await resp.json()
                    if not data.get("success"):
                        raise RuntimeError(f"3x-UI login failed: {data.get('msg', 'unknown')}")
                cookies = {}
                for cookie in sess.cookie_jar:
                    cookies[cookie.key] = cookie.value
                _session_cookies = cookies
                logger.info("3x-UI session established")
                return cookies


async def _invalidate_session():
    global _session_cookies
    _session_cookies = None


async def _request(method: str, path: str, data: dict | None = None, retries: int = 2) -> dict:
    base = settings.XUI_URL.rstrip('/')
    url = f"{base}{path}"
    import aiohttp
    for attempt in range(1 + retries):
        try:
            cookies = await _get_session()
            cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
            headers = {
                "Cookie": cookie_header,
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
            }
            async with aiohttp.ClientSession() as sess:
                async with sess.request(method, url, headers=headers, data=data) as resp:
                    text = await resp.text()
                    if resp.status == 403:
                        await _invalidate_session()
                        if attempt < retries:
                            logger.warning("3x-UI session expired, re-logging in...")
                            continue
                        raise RuntimeError(f"3x-UI access denied: {text[:200]}")
                    if resp.status >= 500:
                        raise RuntimeError(f"3x-UI server error ({resp.status}): {text[:300]}")
                    try:
                        result = json.loads(text)
                    except json.JSONDecodeError:
                        raise RuntimeError(f"3x-UI returned non-JSON ({resp.status}): {text[:300]}")
                    if not result.get("success"):
                        msg = result.get('msg', 'unknown')
                        raise RuntimeError(f"3x-UI error: {msg}")
                    return result.get("obj", {})
        except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as e:
            if attempt < retries and "login" not in str(e).lower():
                wait = 2 ** attempt
                logger.warning("3x-UI request failed (attempt %d/%d): %s. Retrying in %ds...", attempt + 1, retries, e, wait)
                await asyncio.sleep(wait)
            else:
                raise


async def add_client(email: str, days: int) -> dict[str, str]:
    uid = str(uuid_pkg.uuid4())
    expiry = int(time.time() * 1000) + days * 86400000
    inbound_id = settings.XUI_INBOUND_ID
    payload = {
        "email": email,
        "uuid": uid,
        "inboundIds": str(inbound_id),
        "totalGB": "0",
        "expiryTime": str(expiry),
        "enable": "true",
    }
    await _request("POST", "/panel/api/clients/add", data=payload)
    link = await _build_link(uid, email)
    return {"uuid": uid, "email": email, "link": link}


async def update_client_expiry(email: str, days: int):
    expiry = int(time.time() * 1000) + days * 86400000
    payload = {
        "enable": "true",
        "expiryTime": str(expiry),
    }
    await _request("POST", f"/panel/api/clients/update/{quote(email)}", data=payload)


async def remove_client(email: str):
    await _request("POST", f"/panel/api/clients/del/{quote(email)}")


async def get_inbound_info(inbound_id: int) -> dict:
    global _inbound_cache, _inbound_cache_ts
    now = time.time()
    if _inbound_cache is not None and (now - _inbound_cache_ts) < _INBOUND_CACHE_TTL:
        return _inbound_cache
    data = await _request("GET", f"/panel/api/inbounds/get/{inbound_id}")
    _inbound_cache = data
    _inbound_cache_ts = now
    return data


async def _build_link(uuid: str, email: str) -> str:
    inbound = await get_inbound_info(settings.XUI_INBOUND_ID)
    port = inbound.get("port")
    protocol = inbound.get("protocol", "vless")
    stream_settings = {}
    try:
        ss = inbound.get("streamSettings")
        if isinstance(ss, str):
            stream_settings = json.loads(ss)
        else:
            stream_settings = ss or {}
    except Exception:
        stream_settings = {}
    network = stream_settings.get("network", "tcp")
    security = stream_settings.get("security", "none")
    query = {}
    query["encryption"] = "none"
    query["type"] = network
    if security == "reality":
        rs = stream_settings.get("realitySettings", {})
        server_names = rs.get("serverNames", [settings.XUI_SERVER or ""])
        sni = server_names[0] if server_names else (settings.XUI_SERVER or "")
        query["flow"] = "xtls-rprx-vision"
        query["security"] = "reality"
        query["sni"] = sni
        query["fp"] = "chrome"
        if rs.get("publicKey"):
            query["pbk"] = rs["publicKey"]
        if rs.get("shortIds"):
            query["sid"] = rs["shortIds"][0]
    elif security == "tls":
        tls = stream_settings.get("tlsSettings", {})
        sni = tls.get("serverName", settings.XUI_SERVER or "")
        query["security"] = "tls"
        query["sni"] = sni
        query["fp"] = "chrome"
    query_parts = [f"{k}={v}" for k, v in query.items() if v]
    query_str = "&".join(query_parts)
    server = settings.XUI_SERVER or ""
    if not server:
        server = urlparse(settings.XUI_URL).hostname or ""
    return f"{protocol}://{uuid}@{server}:{port}?{query_str}#BlackVPN-{email}"
