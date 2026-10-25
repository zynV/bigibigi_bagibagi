"""Remove recognized user commands only after their handler completes."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.bot.ui import delete_message


class CommandCleanupMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        result = await handler(event, data)
        # Command filters populate this key only for commands addressed to this bot.
        if data.get("command") is not None:
            await delete_message(event.bot, event.chat.id, event.message_id)
        return result
