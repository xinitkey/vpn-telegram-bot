import logging
import time

logger = logging.getLogger(__name__)

HOUR_MS = 3600000


def _hours_word(h: int) -> str:
    if h % 10 == 1 and h % 100 != 11:
        return 'час'
    if 2 <= h % 10 <= 4 and not (12 <= h % 100 <= 14):
        return 'часа'
    return 'часов'


NOTIFY_24H = (
    "⚠️ Внимание! Ваш тариф закончится через {hours} {word}.\n\n"
    "Продлите подписку или оформите новый тариф, чтобы не терять доступ к сервису!"
)

NOTIFY_12H = (
    "⚠️ Внимание! Ваш тариф закончится через {hours} {word}.\n\n"
    "Продлите подписку или оформите новый тариф, чтобы не терять доступ к сервису!"
)

NOTIFY_EXPIRED = (
    "⚠️ Внимание! Ваша подписка истекла. ⚠️\n\n"
    "Оформите новый тариф, чтобы не терять доступ к сервису!"
)


async def check_sub_expiry_notifications(bot):
    from services.db import (
        get_all_users,
        has_sub_notification,
        record_sub_notification,
    )
    now_ms = int(time.time() * 1000)
    for user in await get_all_users():
        if user.banned:
            continue
        end = user.subscription or 0
        if end <= 0:
            continue
        remaining = end - now_ms
        try:
            if remaining <= 0:
                kind, text = 'expired', NOTIFY_EXPIRED
            elif remaining <= 12 * HOUR_MS:
                hours = max(1, round(remaining / HOUR_MS))
                kind, text = 'h12', NOTIFY_12H.format(hours=hours, word=_hours_word(hours))
            elif remaining <= 24 * HOUR_MS:
                hours = max(1, round(remaining / HOUR_MS))
                kind, text = 'h24', NOTIFY_24H.format(hours=hours, word=_hours_word(hours))
            else:
                continue
            if await has_sub_notification(user.user_id, kind):
                continue
            await bot.send_message(user.user_id, text)
            await record_sub_notification(user.user_id, kind)
        except Exception as e:
            logger.warning("Expiry notification failed for user %s: %s", user.user_id, e)
