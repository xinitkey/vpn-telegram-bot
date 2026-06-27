from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

def _fmt_ts(ts: int | None) -> str:
    if not ts or ts <= 0:
        return "—"
    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).astimezone()
    return dt.strftime("%d.%m.%Y %H:%M")

@dataclass
class User:
    user_id: int
    balance: float = 0.0
    subscription: Optional[int] = None
    subscription_start: Optional[int] = None
    xui_uuid: str = ''
    xui_email: str = ''
    link: str = ''
    xui_inbound_id: int = 0
    trial_used: bool = False
    banned: bool = False

    @property
    def is_subscription_active(self) -> bool:
        if self.subscription is None:
            return False
        return self.subscription > int(datetime.now().timestamp() * 1000)

    @property
    def remaining_ms(self) -> int:
        if not self.is_subscription_active:
            return 0
        return max(0, self.subscription - int(datetime.now().timestamp() * 1000))

    @property
    def days_left(self) -> int:
        return max(0, int(self.remaining_ms // (1000 * 60 * 60 * 24)))

    @property
    def hours_left(self) -> int:
        return max(0, int(self.remaining_ms // (1000 * 60 * 60)))

    @property
    def remaining_str(self) -> str:
        if not self.is_subscription_active:
            return "не активна"
        days = self.days_left
        if days >= 1:
            return f"{days} дн."
        hours = self.hours_left
        if hours >= 1:
            return f"{hours} ч."
        minutes = max(1, int(self.remaining_ms // (1000 * 60)))
        return f"{minutes} мин."

    @property
    def subscription_end_str(self) -> str:
        return _fmt_ts(self.subscription)

    @property
    def subscription_start_str(self) -> str:
        return _fmt_ts(self.subscription_start)