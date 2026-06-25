from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class User:
    user_id: int
    balance: float = 0.0
    subscription: Optional[int] = None  # timestamp in milliseconds
    vpn_key: str = ''
    xui_uuid: str = ''
    xui_email: str = ''
    link: str = ''

    @property
    def is_subscription_active(self) -> bool:
        if self.subscription is None:
            return False
        return self.subscription > int(datetime.now().timestamp() * 1000)

    @property
    def days_left(self) -> int:
        if not self.is_subscription_active:
            return 0
        remaining = self.subscription - int(datetime.now().timestamp() * 1000)
        return max(0, int(remaining // (1000 * 60 * 60 * 24)))