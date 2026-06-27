import aiohttp
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

async def _request(method: str, path: str, data: dict | None = None, retries: int = 2) -> dict:
    url = f"{settings.XUI_URL.rstrip('/')}{path}"
    headers = {
        "Authorization": f"Bearer {settings.XUI_API_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
    }
    last_error = None
    for attempt in range(1 + retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, headers=headers, data=data) as resp:
                    if resp.status >= 500:
                        text = await resp.text()
                        raise RuntimeError(f"3x-UI server error ({resp.status}): {text[:200]}")
                    text = await resp.text()
                    try:
                        result = json.loads(text)
                    except json.JSONDecodeError:
                        raise RuntimeError(f"Invalid JSON from 3x-UI: {text[:200]}")
                    if not result.get("success"):
                        raise RuntimeError(f"3x-UI error: {result.get('msg', 'unknown')}")
                    return result.get("obj", {})
        except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as e:
            last_error = e
            if attempt < retries:
                wait = 2 ** attempt
                logger.warning("3x-UI request failed (attempt %d/%d): %s. Retrying in %ds...", attempt + 1, retries, e, wait)
                await asyncio.sleep(wait)
            else:
                logger.error("3x-UI request failed after %d attempts: %s", retries, e)
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