import time
import uuid
from urllib.parse import quote_plus
from config.settings import settings

def generate_payment_id() -> str:
    return f"pay_{int(time.time())}_{uuid.uuid4().hex[:8]}"

async def get_payment_url(bot, user_id: int, amount: float, method: str) -> str:
    """
    Returns a URL the user should follow to pay.
    For Stars: returns invoice link via bot.create_invoice_link (but we need to call it)
    For CryptoBot: deeplink to @CryptoBot
    For Cryptomus: external payment page
    """
    payment_id = generate_payment_id()
    # Save pending payment to DB (caller should do)
    if method == "stars":
        # Use bot's method to create invoice link
        from aiogram.types import LabeledPrice
        prices = [LabeledPrice(label="Пополнение BlackVPN", amount=int(amount * 100))]  # amount in XTR * 100? Stars are integer.
        # In aiogram 3, use await bot.create_invoice_link(...)
        # We'll return placeholder; actual generation done in handler.
        return f"https://t.me/{(await bot.get_me()).username}?start=pay_{payment_id}"
    elif method == "crypto":
        return f"https://t.me/CryptoBot?start={payment_id}"
    elif method == "cryptomus":
        base = settings.CRYPTOMUS_LINK.rstrip('/')
        return f"{base}?amount={amount}&order_id={payment_id}"
    else:
        raise ValueError(f"Unsupported payment method: {method}")