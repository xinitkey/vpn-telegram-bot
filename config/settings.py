import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
_ = __import__('dotenv').load_dotenv(BASE_DIR / '.env')


def _get_bool(name: str, default: str = 'false') -> bool:
    return os.getenv(name, default).lower() in ('true', '1', 'yes')


def _get_int_list(name: str, *fallbacks: str) -> list[int]:
    raw = os.getenv(name) or ''
    for f in fallbacks:
        raw = raw or (os.getenv(f) or '')
    return [int(x.strip()) for x in raw.split(',') if x.strip()]


def _base_url() -> str:
    url = os.getenv('BASE_URL')
    if url:
        return url
    protocol = 'https' if _get_bool('USE_HTTPS') else 'http'
    host = os.getenv('HOST', '0.0.0.0')
    host = host if host != '0.0.0.0' else 'localhost'
    port = os.getenv('PORT', '8000')
    return f"{protocol}://{host}:{port}"


@dataclass
class Settings:
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    BOT_USERNAME: str = os.getenv('BOT_USERNAME', 'BlackVPN_OfficialBot')
    ADMIN_BOT_TOKEN: str = os.getenv('ADMIN_BOT_TOKEN', '')
    ADMIN_IDS: list[int] = field(default_factory=lambda: [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()])

    # 3x-UI
    XUI_URL: str = os.getenv('XUI_URL', '')
    XUI_API_TOKEN: str = os.getenv('XUI_API_TOKEN', '')
    XUI_USERNAME: str = os.getenv('XUI_USERNAME', 'admin')
    XUI_PASSWORD: str = os.getenv('XUI_PASSWORD', '')
    XUI_INBOUND_IDS: list[int] = field(default_factory=lambda: _get_int_list('XUI_INBOUND_IDS', 'XUI_INBOUNDS_ID', 'XUI_INBOUND_ID'))
    XUI_INBOUND_ID: int | None = None
    XUI_SERVER: str = os.getenv('XUI_SERVER', '')
    XUI_SUB_URL: str = field(default_factory=lambda: os.getenv('XUI_SUB_URL', '').rstrip('/'))

    # Database
    DB_URL: str = os.getenv('DB_URL', 'sqlite+aiosqlite:///./data/bot.db')

    # Platega
    PLATEGA_MERCHANT_ID: str = os.getenv('PLATEGA_MERCHANT_ID', '')
    PLATEGA_SECRET: str = os.getenv('PLATEGA_SECRET', '')
    PLATEGA_PAYMENT_METHOD: int = int(os.getenv('PLATEGA_PAYMENT_METHOD', '2'))
    PLATEGA_WEBHOOK_VERIFY: bool = field(default_factory=lambda: _get_bool('PLATEGA_WEBHOOK_VERIFY', 'true'))
    PLATEGA_WEBHOOK_SECRET: str = ''
    PLATEGA_WEBHOOK_TOKEN: str = os.getenv('PLATEGA_WEBHOOK_TOKEN', '')

    # Server
    HOST: str = os.getenv('HOST', '0.0.0.0')
    PORT: int = int(os.getenv('PORT', '8000'))
    USE_HTTPS: bool = field(default_factory=lambda: _get_bool('USE_HTTPS'))
    BASE_URL: str = ''

    # Tariff
    TARIFF_DAILY_PRICE: int = int(os.getenv('TARIFF_DAILY_PRICE', '5'))
    REFERRAL_REWARD: int = int(os.getenv('REFERRAL_REWARD', '50'))

    def __post_init__(self):
        self.BASE_URL = _base_url()
        self.XUI_INBOUND_ID = self.XUI_INBOUND_IDS[0] if self.XUI_INBOUND_IDS else None
        self.PLATEGA_WEBHOOK_SECRET = os.getenv('PLATEGA_WEBHOOK_SECRET') or os.getenv('PLATEGA_SECRET', '')


settings = Settings()
