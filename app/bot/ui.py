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


DELETE_PERMISSION_NOTICE = (
    "⚠️ Витрату збережено, але Telegram не дозволив прибрати ваше повідомлення. "
    "Перевірте, що бот є адміністратором групи з правом «Видаляти повідомлення»."
)


async def delete_message(bot: Bot, chat_id: int, message_id: int | None) -> bool:
    if message_id is None:
        return True
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        if isinstance(exc, TelegramBadRequest) and "message to delete not found" in exc.message.lower():
            return True
        logger.warning("Could not delete message %s in chat %s: %s", message_id, chat_id, exc.message)
        return False


async def clear_expense(
    bot: Bot, chat_id: int, state: FSMContext, *, remove_input: bool = True,
) -> bool:
    """Clear this user's form and return whether their input was removed."""
    data = await state.get_data()
    await state.clear()
    bot_ids = {data.get(key) for key in ("prompt_id", "confirmation_id", "error_id")} - {None}
    input_ids = set(data.get("input_message_ids", [])) if remove_input else set()
    input_removed = True
    for message_id in sorted(bot_ids | input_ids):
        removed = await delete_message(bot, chat_id, message_id)
        if message_id in input_ids and not removed:
            input_removed = False
    return input_removed


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
