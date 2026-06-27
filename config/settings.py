import os
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_BOT_TOKEN = os.getenv('ADMIN_BOT_TOKEN')
ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]

# 3x-UI
XUI_URL = os.getenv('XUI_URL')
XUI_API_TOKEN = os.getenv('XUI_API_TOKEN')
XUI_USERNAME = os.getenv('XUI_USERNAME', 'admin')
XUI_PASSWORD = os.getenv('XUI_PASSWORD')
_inbound_str = os.getenv('XUI_INBOUND_IDS') or os.getenv('XUI_INBOUND_ID', '')
XUI_INBOUND_IDS = [int(x.strip()) for x in _inbound_str.split(',') if x.strip()]
XUI_INBOUND_ID = XUI_INBOUND_IDS[0] if XUI_INBOUND_IDS else None  # backward compat
XUI_SERVER = os.getenv('XUI_SERVER')  # optional
XUI_SUB_URL = os.getenv('XUI_SUB_URL', '').rstrip('/')

# Database
DB_URL = os.getenv('DB_URL', 'sqlite+aiosqlite:///./data/bot.db')

# Cryptomus
CRYPTOMUS_LINK = os.getenv('CRYPTOMUS_LINK')
CRYPTOMUS_MERCHANT_ID = os.getenv('CRYPTOMUS_MERCHANT_ID')
CRYPTOMUS_SECRET_KEY = os.getenv('CRYPTOMUS_SECRET_KEY')

# Server
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', '8000'))
USE_HTTPS = os.getenv('USE_HTTPS', 'false').lower() in ('true', '1', 'yes')
BASE_URL = os.getenv('BASE_URL')
if not BASE_URL:
    protocol = 'https' if USE_HTTPS else 'http'
    host = HOST if HOST != '0.0.0.0' else 'localhost'
    BASE_URL = f"{protocol}://{host}:{PORT}"

# Tariff
TARIFF_DAILY_PRICE = int(os.getenv('TARIFF_DAILY_PRICE', '5'))

# Exported settings object (optional)
class Settings:
    TELEGRAM_BOT_TOKEN = TELEGRAM_BOT_TOKEN
    ADMIN_BOT_TOKEN = ADMIN_BOT_TOKEN
    ADMIN_IDS = ADMIN_IDS
    XUI_URL = XUI_URL
    XUI_API_TOKEN = XUI_API_TOKEN
    XUI_USERNAME = XUI_USERNAME
    XUI_PASSWORD = XUI_PASSWORD
    XUI_INBOUND_IDS = XUI_INBOUND_IDS
    XUI_INBOUND_ID = XUI_INBOUND_ID
    XUI_SERVER = XUI_SERVER
    XUI_SUB_URL = XUI_SUB_URL
    DB_URL = DB_URL
    CRYPTOMUS_LINK = CRYPTOMUS_LINK
    CRYPTOMUS_MERCHANT_ID = CRYPTOMUS_MERCHANT_ID
    CRYPTOMUS_SECRET_KEY = CRYPTOMUS_SECRET_KEY
    HOST = HOST
    PORT = PORT
    USE_HTTPS = USE_HTTPS
    BASE_URL = BASE_URL
    TARIFF_DAILY_PRICE = TARIFF_DAILY_PRICE

settings = Settings()