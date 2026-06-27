import aiosqlite
import asyncio
from typing import Optional
from models.user import User
from config.settings import settings
import time
import os

DB_PATH = None
_db: Optional[aiosqlite.Connection] = None
_db_lock = asyncio.Lock()

_FIELD_MAP = {
    'uuid': 'xui_uuid',
    'email': 'xui_email',
    'link': 'link',
}

async def _get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
    return _db

async def init_db():
    global DB_PATH
    DB_PATH = settings.DB_URL.replace('sqlite+aiosqlite:///', '')
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else '.', exist_ok=True)
    async with _db_lock:
        db = await _get_db()
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance REAL NOT NULL DEFAULT 0,
                subscription INTEGER NOT NULL DEFAULT 0,
                xui_uuid TEXT DEFAULT '',
                xui_email TEXT DEFAULT '',
                link TEXT DEFAULT ''
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                method TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at INTEGER NOT NULL,
                completed_at INTEGER
            )
        ''')
        await db.commit()

async def close_db():
    global _db
    async with _db_lock:
        if _db:
            await _db.close()
            _db = None

async def get_user(user_id: int) -> Optional[User]:
    async with _db_lock:
        db = await _get_db()
        async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cur:
            row = await cur.fetchone()
            if row is None:
                return None
            return User(
                user_id=row['user_id'],
                balance=row['balance'],
                subscription=row['subscription'],
                xui_uuid=row['xui_uuid'] or '',
                xui_email=row['xui_email'] or '',
                link=row['link'] or ''
            )

async def create_user(user_id: int):
    async with _db_lock:
        db = await _get_db()
        await db.execute(
            '''INSERT OR IGNORE INTO users (user_id, balance, subscription, xui_uuid, xui_email, link)
               VALUES (?, 0, 0, '', '', '')''',
            (user_id,)
        )
        await db.commit()

async def update_user(user: User):
    async with _db_lock:
        db = await _get_db()
        await db.execute(
            '''UPDATE users SET balance = ?, subscription = ?, xui_uuid = ?, xui_email = ?, link = ?
               WHERE user_id = ?''',
            (user.balance, user.subscription, user.xui_uuid, user.xui_email, user.link, user.user_id)
        )
        await db.commit()

async def add_balance(user_id: int, amount: float) -> User:
    user = await get_user(user_id)
    if user is None:
        await create_user(user_id)
        user = await get_user(user_id)
    user.balance += amount
    await update_user(user)
    return user

async def set_subscription(user_id: int, days: int):
    now_ms = int(time.time() * 1000)
    add_ms = days * 86400000
    user = await get_user(user_id)
    if user is None:
        await create_user(user_id)
        user = await get_user(user_id)
    if user.subscription and user.subscription > now_ms:
        new_sub = user.subscription + add_ms
    else:
        new_sub = now_ms + add_ms
    async with _db_lock:
        db = await _get_db()
        await db.execute(
            'UPDATE users SET subscription = ? WHERE user_id = ?',
            (new_sub, user_id)
        )
        await db.commit()

async def update_vpn_info(user_id: int, **kwargs):
    fields = []
    values = []
    for key, value in kwargs.items():
        col = _FIELD_MAP.get(key)
        if col and value is not None:
            fields.append(f'{col} = ?')
            values.append(value)
    if not fields:
        return
    values.append(user_id)
    query = 'UPDATE users SET ' + ', '.join(fields) + ' WHERE user_id = ?'
    async with _db_lock:
        db = await _get_db()
        await db.execute(query, values)
        await db.commit()

async def create_payment(payment_id: str, user_id: int, amount: float, method: str):
    async with _db_lock:
        db = await _get_db()
        await db.execute(
            '''INSERT INTO payments (payment_id, user_id, amount, method, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (payment_id, user_id, amount, method, 'pending', int(time.time()))
        )
        await db.commit()

async def get_payment(payment_id: str):
    async with _db_lock:
        db = await _get_db()
        async with db.execute('SELECT * FROM payments WHERE payment_id = ?', (payment_id,)) as cur:
            row = await cur.fetchone()
            if row is None:
                return None
            return dict(row)

async def update_payment_status(payment_id: str, status: str):
    async with _db_lock:
        db = await _get_db()
        await db.execute(
            'UPDATE payments SET status = ?, completed_at = ? WHERE payment_id = ?',
            (status, int(time.time()), payment_id)
        )
        await db.commit()