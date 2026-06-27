import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl
from typing import Optional


def verify_telegram_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> Optional[dict]:
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    hash_value = parsed.pop('hash', None)
    if not hash_value:
        return None

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()

    items = sorted(parsed.items(), key=lambda x: x[0])
    data_check_string = "\n".join(f"{k}={v}" for k, v in items)

    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, hash_value):
        return None

    auth_date = parsed.get('auth_date')
    if auth_date:
        try:
            if int(time.time()) - int(auth_date) > max_age:
                return None
        except ValueError:
            return None

    if 'user' in parsed:
        try:
            parsed['user'] = json.loads(parsed['user'])
        except json.JSONDecodeError:
            return None

    return parsed

