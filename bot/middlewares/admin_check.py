import os
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from typing import Callable, Dict, Any, Awaitable

# Admin ID lar — vergul bilan ajratilgan, env dan o'qiladi
# Misol: ADMIN_IDS=8156792282,552003748
_raw = os.getenv("ADMIN_IDS", "8156792282,552003748")
ADMIN_IDS = [int(x.strip()) for x in _raw.split(",") if x.strip()]

# Guruh chat ID — buyurtmalar shu guruhga keladi
# Misol: GROUP_CHAT_ID=-5194049252
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "-5194049252"))


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


class AdminMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        data["is_admin"] = False
        if isinstance(event, Message) and event.from_user:
            data["is_admin"] = is_admin(event.from_user.id)
        return await handler(event, data)
