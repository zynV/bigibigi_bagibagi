"""One navigation message per chat, with separate expense prompts per user."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup

logger = logging.getLogger(__name__)
MAIN_TEXT = "<b>💰 Сімейний бюджет</b>\nОберіть дію:"


async def delete_message(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if message_id is None:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        # Deleted/expired messages or missing permissions must not break the flow.
        logger.debug("Could not remove interface message %s in chat %s", message_id, chat_id)


async def clear_expense(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """Remove only this user's temporary bot messages, then reset their form."""
    data = await state.get_data()
    await state.clear()
    message_ids = {data.get(key) for key in ("prompt_id", "confirmation_id", "error_id")}
    for message_id in message_ids - {None}:
        await delete_message(bot, chat_id, message_id)


class ChatUI:
    def __init__(self) -> None:
        self._messages: dict[int, int] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    async def show(
        self,
        bot: Bot,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup,
        *,
        message_id: int | None = None,
    ) -> int:
        async with self._locks.setdefault(chat_id, asyncio.Lock()):
            target = self._messages.get(chat_id, message_id)
            obsolete: set[int] = set()
            if target is not None:
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id, message_id=target,
                        text=text, reply_markup=reply_markup,
                    )
                except TelegramBadRequest as exc:
                    error = exc.message.lower()
                    if "message is not modified" in error:
                        pass
                    elif any(reason in error for reason in (
                        "message to edit not found", "message can't be edited",
                        "message can not be edited", "message_id_invalid",
                    )):
                        replacement = await bot.send_message(
                            chat_id=chat_id, text=text, reply_markup=reply_markup,
                        )
                        obsolete.add(target)
                        target = replacement.message_id
                    else:
                        raise
            else:
                message = await bot.send_message(
                    chat_id=chat_id, text=text, reply_markup=reply_markup,
                )
                target = message.message_id
            self._messages[chat_id] = target
            # Retire a stale menu clicked after another menu became current.
            if message_id is not None and message_id != target:
                obsolete.add(message_id)
            for old_id in obsolete:
                await delete_message(bot, chat_id, old_id)
            return target
