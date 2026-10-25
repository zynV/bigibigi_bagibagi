"""Outer middleware blocks every message/callback outside configured IDs/chat."""
from __future__ import annotations

from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from app.config import Settings


class AccessMiddleware(BaseMiddleware):
    def __init__(self, cfg: Settings):
        self.cfg = cfg

    async def __call__(
        self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject, data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            chat_id = event.chat.id
            author_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            chat_id = event.message.chat.id if event.message else None
            author_id = event.from_user.id
        else:
            return None
        if chat_id != self.cfg.group_chat_id or author_id not in self.cfg.allowed_user_ids:
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ Доступ заборонено", show_alert=True)
            return None
        return await handler(event, data)
