import aiohttp
import uuid as uuid_pkg
import json
import time
from typing import Dict, Any
from .settings import settings
from urllib.parse import quote

async def _request(method: str, path: str, data: dict | None = None) -> dict:
    url = f"{settings.XUI_URL.rstrip('/')}{path}"
    headers = {
        "Authorization": f"Bearer {settings.XUI_API_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
    }
    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, headers=headers, data=data) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                raise RuntimeError(f"Invalid JSON from 3x-UI: {text}")
            if not data.get("success"):
                raise RuntimeError(f"3x-UI error: {data.get('msg')}")
            return data.get("obj", {})

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
    data = await _request("POST", "/panel/api/clients/add", data=payload)
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
    return await _request("GET", f"/panel/api/inbounds/get/{inbound_id}")

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
    # Build query string
    query_parts = [f"{k}={v}" for k, v in query.items() if v]
    query_str = "&".join(query_parts)
    server = settings.XUI_SERVER or ""
    if not server:
        from urllib.parse import urlparse
        server = urlparse(settings.XUI_URL).hostname or ""
    return f"{protocol}://{uuid}@{server}:{port}?{query_str}#BlackVPN-{email}"