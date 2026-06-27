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
        try:
            await db.execute('ALTER TABLE users ADD COLUMN trial_used INTEGER DEFAULT 0')
        except Exception:
            pass
        try:
            await db.execute('ALTER TABLE users ADD COLUMN subscription_start INTEGER DEFAULT 0')
        except Exception:
            pass
        try:
            await db.execute('ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0')
        except Exception:
            pass
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
                link=row['link'] or '',
                trial_used=bool(row['trial_used']) if 'trial_used' in row else False,
                subscription_start=row['subscription_start'] if 'subscription_start' in row else None,
                banned=bool(row['banned']) if 'banned' in row.keys() else False
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
            '''UPDATE users SET balance = ?, subscription = ?, xui_uuid = ?, xui_email = ?, link = ?,
               trial_used = ?, subscription_start = ?, banned = ? WHERE user_id = ?''',
            (user.balance, user.subscription, user.xui_uuid, user.xui_email, user.link,
             int(user.trial_used), user.subscription_start, int(user.banned), user.user_id)
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
        start = user.subscription_start
    else:
        new_sub = now_ms + add_ms
        start = now_ms
    async with _db_lock:
        db = await _get_db()
        await db.execute(
            'UPDATE users SET subscription = ?, subscription_start = ? WHERE user_id = ?',
            (new_sub, start, user_id)
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

async def get_all_users() -> list[User]:
    async with _db_lock:
        db = await _get_db()
        async with db.execute('SELECT * FROM users ORDER BY user_id') as cur:
            rows = await cur.fetchall()
            return [User(
                user_id=row['user_id'],
                balance=row['balance'],
                subscription=row['subscription'],
                xui_uuid=row['xui_uuid'] or '',
                xui_email=row['xui_email'] or '',
                link=row['link'] or '',
                trial_used=bool(row['trial_used']) if 'trial_used' in row else False,
                subscription_start=row['subscription_start'] if 'subscription_start' in row else None,
                banned=bool(row['banned']) if 'banned' in row.keys() else False
            ) for row in rows]

async def get_user_count() -> int:
    async with _db_lock:
        db = await _get_db()
        async with db.execute('SELECT COUNT(*) as cnt FROM users') as cur:
            row = await cur.fetchone()
            return row['cnt'] if row else 0

async def get_active_sub_count() -> int:
    now_ms = int(time.time() * 1000)
    async with _db_lock:
        db = await _get_db()
        async with db.execute('SELECT COUNT(*) as cnt FROM users WHERE subscription > ?', (now_ms,)) as cur:
            row = await cur.fetchone()
            return row['cnt'] if row else 0

async def get_total_balance() -> float:
    async with _db_lock:
        db = await _get_db()
        async with db.execute('SELECT SUM(balance) as total FROM users') as cur:
            row = await cur.fetchone()
            return row['total'] if row and row['total'] else 0.0

async def get_payments_count() -> dict:
    async with _db_lock:
        db = await _get_db()
        total = 0
        completed = 0
        async with db.execute('SELECT COUNT(*) as cnt FROM payments') as cur:
            row = await cur.fetchone()
            total = row['cnt'] if row else 0
        async with db.execute("SELECT COUNT(*) as cnt FROM payments WHERE status = 'completed'") as cur:
            row = await cur.fetchone()
            completed = row['cnt'] if row else 0
        return {'total': total, 'completed': completed}


async def get_recent_payments(limit: int = 20) -> list[dict]:
    async with _db_lock:
        db = await _get_db()
        async with db.execute(
            'SELECT * FROM payments ORDER BY created_at DESC LIMIT ?', (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_revenue() -> dict:
    async with _db_lock:
        db = await _get_db()
        async with db.execute("SELECT SUM(amount) as total FROM payments WHERE status = 'completed'") as cur:
            row = await cur.fetchone()
            total = row['total'] or 0
        async with db.execute("SELECT method, SUM(amount) as total FROM payments WHERE status = 'completed' GROUP BY method") as cur:
            by_method = {r['method']: r['total'] for r in await cur.fetchall()}
        return {'total': total, 'by_method': by_method}


async def get_users_by_id_or_email(query: str) -> list[User]:
    async with _db_lock:
        db = await _get_db()
        if query.isdigit():
            rows = []
            async with db.execute('SELECT * FROM users WHERE user_id = ?', (int(query),)) as cur:
                r = await cur.fetchone()
                if r:
                    rows.append(r)
            return [_user_from_row(r) for r in rows]
        async with db.execute('SELECT * FROM users WHERE xui_email LIKE ?', (f'%{query}%',)) as cur:
            rows = await cur.fetchall()
        return [_user_from_row(r) for r in rows]


async def get_banned_count() -> int:
    async with _db_lock:
        db = await _get_db()
        async with db.execute('SELECT COUNT(*) as cnt FROM users WHERE banned = 1') as cur:
            row = await cur.fetchone()
            return row['cnt'] if row else 0


async def get_trial_used_count() -> int:
    async with _db_lock:
        db = await _get_db()
        async with db.execute('SELECT COUNT(*) as cnt FROM users WHERE trial_used = 1') as cur:
            row = await cur.fetchone()
            return row['cnt'] if row else 0


def _user_from_row(row) -> User:
    return User(
        user_id=row['user_id'],
        balance=row['balance'],
        subscription=row['subscription'],
        xui_uuid=row['xui_uuid'] or '',
        xui_email=row['xui_email'] or '',
        link=row['link'] or '',
        trial_used=bool(row['trial_used']) if 'trial_used' in row else False,
        subscription_start=row['subscription_start'] if 'subscription_start' in row else None,
        banned=bool(row['banned']) if 'banned' in row.keys() else False
    )