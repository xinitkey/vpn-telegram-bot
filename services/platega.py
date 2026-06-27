import uuid
import logging
from urllib.parse import urljoin
from aiohttp import ClientSession, ClientError
from config.settings import settings

logger = logging.getLogger(__name__)
BASE_URL = "https://app.platega.io"


async def create_transaction(
    payment_id: str,
    amount: float,
    description: str = "",
    return_url: str = "",
    failed_url: str = "",
) -> dict:
    headers = {
        "X-MerchantId": settings.PLATEGA_MERCHANT_ID,
        "X-Secret": settings.PLATEGA_SECRET,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "paymentMethod": settings.PLATEGA_PAYMENT_METHOD,
        "id": str(uuid.uuid4()),
        "paymentDetails": {
            "amount": amount,
            "currency": "RUB",
        },
        "description": description,
        "payload": payment_id,
    }
    if return_url:
        body["returnUrl"] = return_url
    if failed_url:
        body["failedUrl"] = failed_url

    async with ClientSession(headers=headers) as sess:
        async with sess.post(urljoin(BASE_URL, "/transaction/process"), json=body) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Platega API error ({resp.status}): {text[:300]}")
            data = await resp.json()
            return data
