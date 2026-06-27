import uuid
import logging
from aiohttp import ClientSession
from config.settings import settings

logger = logging.getLogger(__name__)
BASE_URL = "https://app.platega.io"

METHOD_MAP = {
    2: "SBP",
    10: "CARDS",
    11: "ACQUIRING",
    12: "INTERNATIONAL",
    13: "CRYPTO",
}

async def create_transaction(
    payment_id: str,
    amount: float,
    description: str = "",
    return_url: str = "",
    failed_url: str = "",
    payment_method: int = 0,
) -> dict:
    headers = {
        "X-MerchantId": settings.PLATEGA_MERCHANT_ID,
        "X-Secret": settings.PLATEGA_SECRET,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "paymentMethod": payment_method or settings.PLATEGA_PAYMENT_METHOD or 2,
        "id": str(uuid.uuid4()),
        "paymentDetails": {
            "amount": amount,
            "currency": "RUB",
        },
        "description": description,
        "payload": payment_id,
        "return": return_url or settings.BASE_URL.rstrip('/'),
        "failedUrl": failed_url or settings.BASE_URL.rstrip('/'),
    }

    async with ClientSession(headers=headers) as sess:
        async with sess.post(f"{BASE_URL}/transaction/process", json=body) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Platega API error ({resp.status}): {text[:300]}")
            data = await resp.json()
            return data
