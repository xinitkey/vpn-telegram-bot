import aiosqlite
import asyncio
from typing import Optional
from models.user import User, _base36_encode
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
        for col in ('trial_used', 'subscription_start', 'banned', 'xui_inbound_id', 'referral_code', 'referred_by', 'referral_earnings', 'telegram_username', 'first_name'):
            try:
                text_cols = ('referral_code', 'telegram_username', 'first_name')
                col_type = 'TEXT' if col in text_cols else 'REAL' if col == 'referral_earnings' else 'INTEGER'
                default = "''" if col in text_cols else '0'
                await db.execute(f'ALTER TABLE users ADD COLUMN {col} {col_type} DEFAULT {default}')
            except Exception:
                pass
        await db.execute('''
            CREATE TABLE IF NOT EXISTS referral_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE(referrer_id, referred_id)
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
        try:
            await db.execute('CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)')
        except Exception:
            pass
        await db.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                discount_percent INTEGER NOT NULL,
                tariff_ids TEXT,
                max_uses INTEGER,
                used_count INTEGER NOT NULL DEFAULT 0,
                expires_at INTEGER,
                created_at INTEGER NOT NULL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS promocode_uses (
                code TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                used_at INTEGER NOT NULL,
                PRIMARY KEY (code, user_id)
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
            return _user_from_row(row)

async def create_user(user_id: int, referred_by: int = None):
    async with _db_lock:
        db = await _get_db()
        ref_code = await _generate_referral_code(user_id)
        await db.execute(
            '''INSERT OR IGNORE INTO users
               (user_id, balance, subscription, xui_uuid, xui_email, link, referral_code, referred_by)
               VALUES (?, 0, 0, '', '', '', ?, ?)''',
            (user_id, ref_code, referred_by)
        )
        await db.commit()

async def _generate_referral_code(user_id: int) -> str:
    return _base36_encode(user_id)

async def update_user(user: User):
    async with _db_lock:
        db = await _get_db()
        await db.execute(
            '''UPDATE users SET balance = ?, subscription = ?, xui_uuid = ?, xui_email = ?, link = ?,
               trial_used = ?, subscription_start = ?, banned = ?, xui_inbound_id = ?,
               referral_code = ?, referred_by = ?, referral_earnings = ?, telegram_username = ?, first_name = ? WHERE user_id = ?''',
            (user.balance, user.subscription, user.xui_uuid, user.xui_email, user.link,
             int(user.trial_used), user.subscription_start, int(user.banned), user.xui_inbound_id,
             user.referral_code, user.referred_by, user.referral_earnings, user.telegram_username, user.first_name, user.user_id)
        )
        await db.commit()

async def add_balance(user_id: int, amount: float) -> User:
    user = await get_user(user_id)
    if user is None:
        await create_user(user_id)
        user = await get_user(user_id)
    user.balance += amount
    await update_user(user)
    # Referral reward: 50₽ to referrer on first top-up
    if amount > 0 and user.referred_by:
        await _reward_referrer(user.referred_by, user.user_id, amount)
    return user

async def _reward_referrer(referrer_id: int, referred_id: int, topup_amount: float):
    REWARD = settings.REFERRAL_REWARD
    async with _db_lock:
        db = await _get_db()
        async with db.execute(
            'SELECT id FROM referral_rewards WHERE referrer_id = ? AND referred_id = ?',
            (referrer_id, referred_id)
        ) as cur:
            if await cur.fetchone():
                return
        try:
            await db.execute(
                'INSERT INTO referral_rewards (referrer_id, referred_id, amount, created_at) VALUES (?, ?, ?, ?)',
                (referrer_id, referred_id, REWARD, int(time.time()))
            )
            await db.commit()
        except Exception:
            return
    referrer = await get_user(referrer_id)
    if referrer:
        referrer.balance += REWARD
        referrer.referral_earnings += REWARD
        await update_user(referrer)

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
            return [_user_from_row(row) for row in rows]

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
        pending = 0
        expired = 0
        async with db.execute('SELECT COUNT(*) as cnt FROM payments') as cur:
            row = await cur.fetchone()
            total = row['cnt'] if row else 0
        async with db.execute("SELECT COUNT(*) as cnt FROM payments WHERE status = 'completed'") as cur:
            row = await cur.fetchone()
            completed = row['cnt'] if row else 0
        async with db.execute("SELECT COUNT(*) as cnt FROM payments WHERE status = 'pending'") as cur:
            row = await cur.fetchone()
            pending = row['cnt'] if row else 0
        async with db.execute("SELECT COUNT(*) as cnt FROM payments WHERE status = 'expired'") as cur:
            row = await cur.fetchone()
            expired = row['cnt'] if row else 0
        return {'total': total, 'completed': completed, 'pending': pending, 'expired': expired}

async def expire_old_payments(minutes: int = 30):
    cutoff = int(time.time()) - minutes * 60
    async with _db_lock:
        db = await _get_db()
        await db.execute(
            "UPDATE payments SET status = 'expired', completed_at = ? WHERE status = 'pending' AND created_at < ?",
            (int(time.time()), cutoff)
        )
        await db.commit()


async def get_recent_payments(limit: int = 20) -> list[dict]:
    async with _db_lock:
        db = await _get_db()
        async with db.execute(
            'SELECT * FROM payments ORDER BY created_at DESC LIMIT ?', (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_all_completed_payments() -> list[dict]:
    async with _db_lock:
        db = await _get_db()
        async with db.execute(
            '''SELECT p.*, u.balance as user_balance
               FROM payments p
               LEFT JOIN users u ON p.user_id = u.user_id
               WHERE p.status = 'completed'
               ORDER BY p.completed_at DESC'''
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_user_payments(user_id: int) -> list[dict]:
    async with _db_lock:
        db = await _get_db()
        async with db.execute(
            'SELECT * FROM payments WHERE user_id = ? ORDER BY created_at DESC', (user_id,)
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
        clean = query.lstrip('@')
        async with db.execute(
            'SELECT * FROM users WHERE xui_email LIKE ? OR telegram_username LIKE ? OR first_name LIKE ?',
            (f'%{query}%', f'%{clean}%', f'%{query}%')
        ) as cur:
            rows = await cur.fetchall()
        return [_user_from_row(r) for r in rows]


async def update_user_profile(user_id: int, username: str | None, first_name: str | None = None):
    if not username and not first_name:
        return
    sets = []
    vals = []
    if username:
        sets.append('telegram_username = ?')
        vals.append(username)
    if first_name:
        sets.append('first_name = ?')
        vals.append(first_name)
    if not sets:
        return
    vals.append(user_id)
    async with _db_lock:
        db = await _get_db()
        await db.execute(
            f'UPDATE users SET {", ".join(sets)} WHERE user_id = ?', vals
        )
        await db.commit()


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


async def reset_trial(user_id: int = None):
    async with _db_lock:
        db = await _get_db()
        if user_id:
            await db.execute('UPDATE users SET trial_used = 0 WHERE user_id = ?', (user_id,))
        else:
            await db.execute('UPDATE users SET trial_used = 0')
        await db.commit()


async def wipe_user(user_id: int):
    async with _db_lock:
        db = await _get_db()
        await db.execute('DELETE FROM payments WHERE user_id = ?', (user_id,))
        await db.execute('DELETE FROM referral_rewards WHERE referrer_id = ? OR referred_id = ?', (user_id, user_id))
        await db.execute(
            '''UPDATE users SET balance = 0, subscription = 0, subscription_start = 0,
               xui_uuid = '', xui_email = '', link = '', trial_used = 0,
               banned = 0, xui_inbound_id = 0, referral_code = '', referred_by = NULL,
               referral_earnings = 0 WHERE user_id = ?''',
            (user_id,)
        )
        await db.commit()


def _user_from_row(row) -> User:
    return User(
        user_id=row['user_id'],
        balance=row['balance'],
        subscription=row['subscription'],
        xui_uuid=row['xui_uuid'] or '',
        xui_email=row['xui_email'] or '',
        link=row['link'] or '',
        trial_used=bool(row['trial_used']),
        subscription_start=row['subscription_start'],
        banned=bool(row['banned']),
        xui_inbound_id=row['xui_inbound_id'],
        referral_code=row['referral_code'] or '',
        referred_by=row['referred_by'] if row['referred_by'] else None,
        referral_earnings=float(row['referral_earnings']),
        telegram_username=row['telegram_username'] or '',
        first_name=row['first_name'] or '',
    )

async def get_referral_stats(user_id: int) -> dict:
    async with _db_lock:
        db = await _get_db()
        async with db.execute('SELECT COUNT(*) as cnt FROM referral_rewards WHERE referrer_id = ?', (user_id,)) as cur:
            row = await cur.fetchone()
            referrals = row['cnt'] if row else 0
        async with db.execute('SELECT COALESCE(SUM(amount), 0) as total FROM referral_rewards WHERE referrer_id = ?', (user_id,)) as cur:
            row = await cur.fetchone()
            earned = row['total'] if row else 0
        return {'referrals': referrals, 'earned': earned}


async def create_promocode(code: str, discount_percent: int, tariff_ids: str = None,
                           max_uses: int = None, expires_at: int = None):
    async with _db_lock:
        db = await _get_db()
        try:
            await db.execute(
                '''INSERT INTO promocodes (code, discount_percent, tariff_ids, max_uses, used_count, expires_at, created_at)
                   VALUES (?, ?, ?, ?, 0, ?, ?)''',
                (code.upper(), discount_percent, tariff_ids, max_uses, expires_at, int(time.time()))
            )
            await db.commit()
            return True
        except Exception:
            return False


async def get_promocode(code: str) -> dict | None:
    async with _db_lock:
        db = await _get_db()
        async with db.execute('SELECT * FROM promocodes WHERE code = ?', (code.upper(),)) as cur:
            row = await cur.fetchone()
            if row is None:
                return None
            return dict(row)


async def delete_promocode(code: str) -> bool:
    async with _db_lock:
        db = await _get_db()
        cur = await db.execute('DELETE FROM promocodes WHERE code = ?', (code.upper(),))
        await db.commit()
        return cur.rowcount > 0


async def get_all_promocodes() -> list[dict]:
    async with _db_lock:
        db = await _get_db()
        async with db.execute('SELECT * FROM promocodes ORDER BY created_at DESC') as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def increment_promocode_uses(code: str) -> bool:
    async with _db_lock:
        db = await _get_db()
        cur = await db.execute(
            'UPDATE promocodes SET used_count = used_count + 1 WHERE code = ?',
            (code.upper(),)
        )
        await db.commit()
        return cur.rowcount > 0


async def user_used_promocode(code: str, user_id: int) -> bool:
    async with _db_lock:
        db = await _get_db()
        async with db.execute(
            'SELECT 1 FROM promocode_uses WHERE code = ? AND user_id = ?',
            (code.upper(), user_id)
        ) as cur:
            return await cur.fetchone() is not None


async def record_promocode_use(code: str, user_id: int):
    async with _db_lock:
        db = await _get_db()
        await db.execute(
            'INSERT OR IGNORE INTO promocode_uses (code, user_id, used_at) VALUES (?, ?, ?)',
            (code.upper(), user_id, int(time.time()))
        )
        await db.commit()


TARIFF_INDEX_MAP = {1: 3, 2: 30, 3: 90, 4: 180, 5: 365}
TARIFF_PRICE_MAP = {3: 15, 30: 119, 90: 299, 180: 549, 365: 999}
_DAYS_TO_INDEX = {v: k for k, v in TARIFF_INDEX_MAP.items()}


async def validate_promocode(promo: dict, tariff_days: int, user_id: int = None) -> tuple[bool, str]:
    now = int(time.time() * 1000)
    if promo['expires_at'] and now > promo['expires_at']:
        return False, 'Срок действия промокода истёк'
    if promo['max_uses'] is not None and promo['used_count'] >= promo['max_uses']:
        return False, 'Промокод исчерпал лимит использований'
    if promo['tariff_ids']:
        allowed_idxes = [int(x.strip()) for x in promo['tariff_ids'].split(',') if x.strip()]
        idx = _DAYS_TO_INDEX.get(tariff_days)
        if idx is None or idx not in allowed_idxes:
            return False, 'Промокод не действует на выбранный тариф'
    if user_id is not None and await user_used_promocode(promo['code'], user_id):
        return False, 'Вы уже использовали этот промокод'
    return True, ''


def discounted_price(tariff_days: int, discount_percent: int) -> int:
    original = TARIFF_PRICE_MAP.get(tariff_days, 0)
    if original == 0:
        return 0
    return max(1, int(original * (100 - discount_percent) / 100))