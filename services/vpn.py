import asyncio
import hashlib
import logging
import time
import uuid as uuid_pkg

from abc import ABC, abstractmethod

from config.settings import settings

logger = logging.getLogger(__name__)

_provider: "VPNProvider | None" = None
_provider_lock = asyncio.Lock()


class VPNProvider(ABC):
    """Interface implemented by all VPN backend adapters.

    A template ships with a local MockVPNProvider so the project runs
    without any external infrastructure. To integrate a real panel, write
    a new subclass and select it via the VPN_PROVIDER setting.
    """

    name: str = "base"

    @property
    def enabled(self) -> bool:
        """Whether the adapter has enough configuration to operate."""
        return True

    @property
    def inbound_ids(self) -> list[int]:
        return settings.VPN_INBOUND_IDS

    @abstractmethod
    async def add_client(self, email: str, days: int, inbound_id: int | None = None) -> dict[str, str]:
        """Provision a new client. Returns {uuid, email, link, inbound_id}."""

    @abstractmethod
    async def update_client_expiry(self, email: str, days: int):
        """Extend/overflow a client's expiry."""

    @abstractmethod
    async def remove_client(self, email: str):
        """Remove a client and revoke its keys."""

    @abstractmethod
    async def build_link_for_email(self, email: str, inbound_id: int | None = None) -> str:
        """Return a shareable subscription/client link for an existing client."""

    @abstractmethod
    async def get_client_activity(self, email: str) -> dict:
        """Return minimal activity metadata: active, lastOnline, traffic, ips."""

    async def sync_or_create_client(self, email: str, days: int, inbound_id: int | None = None) -> dict[str, str]:
        """Update expiry when the client exists; recreate it otherwise."""
        try:
            await self.update_client_expiry(email, days)
            link = await self.build_link_for_email(email, inbound_id)
            return {"email": email, "link": link, "recreated": False}
        except Exception:
            try:
                await self.remove_client(email)
            except Exception:
                pass
            result = await self.add_client(email, days, inbound_id)
            result["recreated"] = True
            return result


class MockVPNProvider(VPNProvider):
    """Offline provider that returns deterministic placeholder links.

    Never contacts the network. Useful for local development, tests and
    as a reference implementation for custom adapters.
    """

    name = "mock"

    async def add_client(self, email: str, days: int, inbound_id: int | None = None) -> dict[str, str]:
        uid = str(uuid_pkg.uuid4())
        sub_id = str(uuid_pkg.uuid4())[:16]
        link = await self._build_link(uid, email, sub_id)
        logger.info("[mock] add client %s for %d days", email, days)
        return {"uuid": uid, "email": email, "link": link, "inbound_id": inbound_id or 0}

    async def update_client_expiry(self, email: str, days: int):
        logger.info("[mock] extend %s by %d days", email, days)

    async def remove_client(self, email: str):
        logger.info("[mock] remove client %s", email)

    async def build_link_for_email(self, email: str, inbound_id: int | None = None) -> str:
        digest = hashlib.sha256(email.encode()).hexdigest()
        uid = f"{digest[:8]}-{digest[8:12]}-4{digest[12:15]}-{digest[15:19]}-{digest[19:31]}"
        return await self._build_link(uid, email, digest[:16])

    async def get_client_activity(self, email: str) -> dict:
        return {"active": False, "lastOnline": 0, "trafficUp": 0, "trafficDown": 0, "ips": []}

    async def _build_link(self, uuid: str, email: str, sub_id: str) -> str:
        host = settings.MOCK_VPN_HOST.rstrip("/") or "example.invalid"
        return f"vless://{uuid}@{host}:443?encryption=none&security=tls&sni={host}&type=tcp&fp=chrome#{sub_id}"


class XuiProvider(VPNProvider):
    """Optional adapter for 3x-UI panel instances (used by many VPN panels).

    Enabled only when VPN_PROVIDER=xui and the required settings are present.
    All panel traffic goes through the 3x-UI web API.
    """

    name = "xui"

    @property
    def enabled(self) -> bool:
        return bool(settings.XUI_URL and settings.XUI_PASSWORD and self.inbound_ids)

    async def add_client(self, email: str, days: int, inbound_id: int | None = None) -> dict[str, str]:
        from services.xui_api import add_client
        return await add_client(email, days, inbound_id)

    async def update_client_expiry(self, email: str, days: int):
        from services.xui_api import update_client_expiry
        await update_client_expiry(email, days)

    async def remove_client(self, email: str):
        from services.xui_api import remove_client
        await remove_client(email)

    async def build_link_for_email(self, email: str, inbound_id: int | None = None) -> str:
        from services.xui_api import build_link_for_email
        return await build_link_for_email(email, inbound_id)

    async def get_client_activity(self, email: str) -> dict:
        from services.xui_api import get_client_activity
        try:
            import time as _time
            activity = await get_client_activity(email)
            activity["lastOnline"] = int(activity.get("lastOnline") or 0)
            activity.setdefault("trafficUp", 0)
            activity.setdefault("trafficDown", 0)
            activity.setdefault("ips", [])
            activity["active"] = bool(activity.get("ips")) or (
                activity["trafficUp"] + activity["trafficDown"] > 0
                and activity["lastOnline"] > _time.time() * 1000 - 86400000
            )
            return activity
        except Exception as e:
            logger.warning("Failed to get client activity for %s: %s", email, e)
            return {"active": False, "lastOnline": 0, "trafficUp": 0, "trafficDown": 0, "ips": []}


def get_provider() -> VPNProvider:
    """Return the configured VPN provider (cached singleton)."""
    global _provider
    if _provider is None:
        if settings.VPN_PROVIDER in ("xui", "3x-ui", "3xui"):
            _provider = XuiProvider()
        else:
            _provider = MockVPNProvider()
        logger.info("VPN provider: %s", _provider.name)
    return _provider