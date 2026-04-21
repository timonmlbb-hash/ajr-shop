import os
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from typing import Callable, Dict, Any, Awaitable

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "8156792282").split(",")]


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
