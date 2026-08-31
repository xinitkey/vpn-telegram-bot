import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
_ = __import__('dotenv').load_dotenv(BASE_DIR / '.env')


def _get_bool(name: str, default: str = 'false') -> bool:
    return os.getenv(name, default).lower() in ('true', '1', 'yes')


def _get_int(name: str, default: int = 0) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _get_int_list(name: str, *fallbacks: str) -> list[int]:
    raw = os.getenv(name) or ''
    for f in fallbacks:
        raw = raw or (os.getenv(f) or '')
    return [int(x.strip()) for x in raw.split(',') if x.strip()]


def _parse_tariffs(raw: str) -> dict[int, int]:
    """Parse 'DAYS:PRICE,DAYS:PRICE' into {days: price}. Sample values are
    placeholders — replace them with your own pricing."""
    result: dict[int, int] = {}
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        try:
            days, price = part.split(':')
            result[int(days.strip())] = int(price.strip())
        except ValueError:
            continue
    return result


def _base_url() -> str:
    url = os.getenv('BASE_URL')
    if url:
        return url.rstrip('/')
    protocol = 'https' if _get_bool('USE_HTTPS') else 'http'
    host = os.getenv('HOST', '127.0.0.1')
    host = host if host not in ('0.0.0.0', '::') else 'localhost'
    port = os.getenv('PORT', '8000')
    return f"{protocol}://{host}:{port}"


@dataclass
class Settings:
    # Application
    APP_NAME: str = os.getenv('APP_NAME', 'NoName')
    APP_ENV: str = os.getenv('APP_ENV', 'development')
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO').upper()
    HOST: str = os.getenv('HOST', '127.0.0.1')
    PORT: int = _get_int('PORT', 8000)
    USE_HTTPS: bool = field(default_factory=lambda: _get_bool('USE_HTTPS'))
    BASE_URL: str = ''
    # Allows plain ?userId= auth for local frontend development (NEVER enable in prod)
    DEV_MODE: bool = field(default_factory=lambda: _get_bool('DEV_MODE'))

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    BOT_USERNAME: str = os.getenv('BOT_USERNAME', 'YourBot')
    ADMIN_BOT_TOKEN: str = os.getenv('ADMIN_BOT_TOKEN', '')
    # Admin IDs come from TELEGRAM_ADMIN_IDS (ADMIN_IDS kept as a fallback name)
    TELEGRAM_ADMIN_IDS: list[int] = field(default_factory=lambda: _get_int_list('TELEGRAM_ADMIN_IDS', 'ADMIN_IDS'))
    ADMIN_IDS: list[int] = field(default_factory=lambda: [])

    # Webhook (off by default; register the webhook only when enabled)
    WEBHOOK_ENABLED: bool = field(default_factory=lambda: _get_bool('WEBHOOK_ENABLED'))
    WEBHOOK_SECRET: str = os.getenv('WEBHOOK_SECRET', '')

    # Database
    DB_URL: str = os.getenv('DB_URL', 'sqlite+aiosqlite:///./data/noname.db')

    # VPN provider. Defaults to a safe local mock that never contacts the network.
    # Set VPN_PROVIDER=xui to enable the optional 3x-UI panel adapter.
    VPN_PROVIDER: str = os.getenv('VPN_PROVIDER', 'mock').lower()
    VPN_API_URL: str = os.getenv('VPN_API_URL', '')
    VPN_API_TOKEN: str = os.getenv('VPN_API_TOKEN', '')
    VPN_INBOUND_IDS: list[int] = field(default_factory=lambda: _get_int_list('VPN_INBOUND_IDS', 'XUI_INBOUND_IDS', 'XUI_INBOUNDS_ID', 'XUI_INBOUND_ID'))
    VPN_USERNAME: str = os.getenv('VPN_USERNAME', 'admin')
    VPN_PASSWORD: str = os.getenv('VPN_PASSWORD', '')
    VPN_SUB_URL: str = field(default_factory=lambda: os.getenv('VPN_SUB_URL', '').rstrip('/'))
    MOCK_VPN_HOST: str = os.getenv('MOCK_VPN_HOST', 'example.invalid')

    # Compatibility aliases for the optional 3x-UI adapter (legacy names still accepted)
    XUI_URL: str = ''
    XUI_API_TOKEN: str = ''
    XUI_USERNAME: str = ''
    XUI_PASSWORD: str = ''
    XUI_INBOUND_IDS: list[int] = field(default_factory=lambda: [])
    XUI_INBOUND_ID: int | None = None
    XUI_SERVER: str = ''
    XUI_SUB_URL: str = ''

    # Payment provider adapter (optional; disabled by default)
    PAYMENT_PROVIDER: str = os.getenv('PAYMENT_PROVIDER', 'none').lower()
    PLATEGA_MERCHANT_ID: str = os.getenv('PLATEGA_MERCHANT_ID', '')
    PLATEGA_SECRET: str = os.getenv('PLATEGA_SECRET', '')
    PLATEGA_PAYMENT_METHOD: int = _get_int('PLATEGA_PAYMENT_METHOD', 2)
    PLATEGA_WEBHOOK_VERIFY: bool = field(default_factory=lambda: _get_bool('PLATEGA_WEBHOOK_VERIFY', 'true'))
    PLATEGA_WEBHOOK_TOKEN: str = os.getenv('PLATEGA_WEBHOOK_TOKEN', '')

    # Tariffs and pricing (sample placeholders — configure your own)
    TARIFFS: dict[int, int] = field(default_factory=lambda: _parse_tariffs(
        os.getenv('TARIFFS', '3:10,30:99,90:249,180:449,365:849')))
    TARIFF_DAILY_PRICE: int = _get_int('TARIFF_DAILY_PRICE', 10)
    REFERRAL_REWARD: int = _get_int('REFERRAL_REWARD', 10)
    TRIAL_DAYS: int = _get_int('TRIAL_DAYS', 3)
    MIN_TOPUP: int = _get_int('MIN_TOPUP', 10)
    TOPUP_PRESETS: list[int] = field(default_factory=lambda: _get_int_list('TOPUP_PRESETS') or [10, 50, 100, 200, 500])
    SUPPORT_URL: str = os.getenv('SUPPORT_URL', 'https://example.invalid/support')

    def __post_init__(self):
        self.BASE_URL = _base_url()
        self.ADMIN_IDS = self.TELEGRAM_ADMIN_IDS
        self.TARIFF_PRICE_MAP = dict(sorted(self.TARIFFS.items()))
        self.TARIFF_INDEX_MAP = {idx + 1: days for idx, days in enumerate(self.TARIFF_PRICE_MAP)}
        self._DAYS_TO_INDEX = {v: k for k, v in self.TARIFF_INDEX_MAP.items()}

        # Legacy 3x-UI env names still work when VPN_PROVIDER=xui is set
        self.XUI_URL = os.getenv('XUI_URL', '')
        self.XUI_API_TOKEN = os.getenv('XUI_API_TOKEN', '')
        self.XUI_USERNAME = os.getenv('XUI_USERNAME', self.VPN_USERNAME)
        self.XUI_PASSWORD = os.getenv('XUI_PASSWORD', self.VPN_PASSWORD)
        self.XUI_INBOUND_IDS = self.VPN_INBOUND_IDS
        self.XUI_INBOUND_ID = self.XUI_INBOUND_IDS[0] if self.XUI_INBOUND_IDS else None
        self.XUI_SERVER = os.getenv('XUI_SERVER', '')
        self.XUI_SUB_URL = os.getenv('XUI_SUB_URL', self.VPN_SUB_URL).rstrip('/')

        self.PLATEGA_WEBHOOK_SECRET = os.getenv('PLATEGA_WEBHOOK_SECRET') or self.PLATEGA_SECRET

    @property
    def payment_enabled(self) -> bool:
        return bool(self.PAYMENT_PROVIDER and self.PAYMENT_PROVIDER != 'none')

    @property
    def tariffs_config(self) -> list[dict]:
        return [
            {'days': days, 'price': self.TARIFF_PRICE_MAP[days]}
            for days in sorted(self.TARIFF_PRICE_MAP)
        ]


settings = Settings()