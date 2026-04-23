import os
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from typing import Callable, Dict, Any, Awaitable

# ADMIN_IDS=6399335791,552003748
_raw = os.getenv("ADMIN_IDS", "6399335791,552003748,8156792282")
ADMIN_IDS = [int(x.strip()) for x in _raw.split(",") if x.strip()]

# Guruh chat ID lari
GROUP_CHAT_ID   = int(os.getenv("GROUP_CHAT_ID",   "-5194049252"))  # Buyurtmalar
GROUP_CHECKS_ID = int(os.getenv("GROUP_CHECKS_ID", "-5284654949"))  # Cheklar
GLAVNIY_ADMIN_ID = int(os.getenv("GLAVNIY_ADMIN_ID", "8156792282")) # Bosh admin


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
