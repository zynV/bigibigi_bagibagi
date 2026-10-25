"""User input cleanup respects command routing and group access."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandObject
from aiogram.methods import DeleteMessage
from aiogram.types import Chat, Message, Update, User

from app.bot.handlers import expenses
from app.bot.keyboards.main import main_keyboard
from app.bot.middlewares.access import AccessMiddleware
from app.bot.middlewares.cleanup import CommandCleanupMiddleware
from app.bot.states.expense import ExpenseState
from app.bot.ui import ChatUI, MAIN_TEXT
from tests.test_bot_ui import CHAT_ID, BotDouble, callback, input_message, make_state, services


@pytest.mark.asyncio
@pytest.mark.parametrize("text,user_id,chat_id,should_delete", [
    ("/menu", 11, CHAT_ID, True),
    ("/cancel", 22, CHAT_ID, True),
    ("/menu@family_bot", 11, CHAT_ID, True),
    ("/menu@other_bot", 11, CHAT_ID, False),
    ("/unknown", 11, CHAT_ID, False),
    ("Привіт!", 11, CHAT_ID, False),
    ("/menu", 33, CHAT_ID, False),
    ("/menu", 11, -1009999999999, False),
])
async def test_only_recognized_authorized_commands_are_deleted(text, user_id, chat_id, should_delete):
    bot = Bot("123456789:TEST_TOKEN")
    bot.get_me = AsyncMock(return_value=User(
        id=123456789, is_bot=True, first_name="Family", username="family_bot",
    ))
    bot.delete_message = AsyncMock(return_value=True)
    config = SimpleNamespace(group_chat_id=CHAT_ID, allowed_user_ids=frozenset({11, 22}))
    dp = Dispatcher()
    dp.message.outer_middleware(AccessMiddleware(config))
    dp.message.middleware(CommandCleanupMiddleware())
    handled_ids = []

    async def handle(message: Message):
        # Cleanup runs after the command has produced its result.
        bot.delete_message.assert_not_awaited()
        handled_ids.append(message.message_id)

    dp.message.register(handle, Command("menu", "cancel"))
    message = Message(
        message_id=501, date=datetime.now(timezone.utc),
        chat=Chat(id=chat_id, type="supergroup"),
        from_user=User(id=user_id, is_bot=False, first_name="Учасник"), text=text,
    )
    try:
        await dp.feed_update(bot, Update(update_id=1, message=message))
        if should_delete:
            assert handled_ids == [501]
            bot.delete_message.assert_awaited_once_with(chat_id=chat_id, message_id=501)
        else:
            assert handled_ids == []
            bot.delete_message.assert_not_awaited()
    finally:
        await dp.storage.close()
        await bot.session.close()


@pytest.mark.asyncio
async def test_failed_command_keeps_the_original_message():
    bot = BotDouble()
    message = input_message(bot)
    handler = AsyncMock(side_effect=RuntimeError("Could not show the result"))
    with pytest.raises(RuntimeError, match="Could not show"):
        await CommandCleanupMiddleware()(handler, message, {"command": CommandObject(command="menu")})
    bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("error_class", [TelegramBadRequest, TelegramForbiddenError])
async def test_command_still_succeeds_when_telegram_refuses_deletion(error_class):
    bot = BotDouble()
    message = input_message(bot)
    bot.delete_message.side_effect = error_class(
        method=DeleteMessage(chat_id=CHAT_ID, message_id=message.message_id),
        message="Not enough rights to delete messages",
    )
    handler = AsyncMock(return_value="done")
    result = await CommandCleanupMiddleware()(
        handler, message, {"command": CommandObject(command="menu")},
    )
    assert result == "done"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_amount_with_note_is_deleted_after_confirmation_is_created():
    bot, ui, state = BotDouble(), ChatUI(), make_state()
    budget, _ = services()
    menu_id = await ui.show(bot, CHAT_ID, MAIN_TEXT, main_keyboard())
    await expenses.choose_category(callback(bot, menu_id, "cat:1"), budget, state, ui)
    prompt_id = (await state.get_data())["prompt_id"]
    message = input_message(bot, "130 Kaufland", reply_to=prompt_id)

    await expenses.receive_amount(message, state)

    data = await state.get_data()
    assert data["amount_grosz"] == 13000
    assert data["note"] == "Kaufland"
    assert "Kaufland" in bot.messages[data["confirmation_id"]].text
    assert await state.get_state() == ExpenseState.waiting_for_confirmation.state
    bot.delete_message.assert_any_await(chat_id=CHAT_ID, message_id=message.message_id)


@pytest.mark.asyncio
async def test_invalid_amount_is_deleted_but_retry_prompt_remains():
    bot, ui, state = BotDouble(), ChatUI(), make_state()
    budget, _ = services()
    menu_id = await ui.show(bot, CHAT_ID, MAIN_TEXT, main_keyboard())
    await expenses.choose_category(callback(bot, menu_id, "cat:1"), budget, state, ui)
    prompt_id = (await state.get_data())["prompt_id"]
    message = input_message(bot, "0", reply_to=prompt_id)

    await expenses.receive_amount(message, state)

    data = await state.get_data()
    assert prompt_id in bot.messages
    assert data["error_id"] in bot.messages
    assert await state.get_state() == ExpenseState.waiting_for_amount.state
    bot.delete_message.assert_awaited_once_with(chat_id=CHAT_ID, message_id=message.message_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("reply_to", [None, 9999])
async def test_unrelated_conversation_is_not_deleted_during_amount_entry(reply_to):
    bot, state = BotDouble(), make_state()
    await state.set_state(ExpenseState.waiting_for_amount)
    await state.update_data(prompt_id=1234)
    await expenses.receive_amount(input_message(bot, "4250", reply_to=reply_to), state)
    bot.delete_message.assert_not_awaited()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_amount_is_preserved_if_confirmation_cannot_be_sent():
    bot, ui, state = BotDouble(), ChatUI(), make_state()
    budget, _ = services()
    menu_id = await ui.show(bot, CHAT_ID, MAIN_TEXT, main_keyboard())
    await expenses.choose_category(callback(bot, menu_id, "cat:1"), budget, state, ui)
    prompt_id = (await state.get_data())["prompt_id"]
    message = input_message(bot, "12,50", reply_to=prompt_id)
    bot.delete_message.reset_mock()
    bot.send_message.side_effect = RuntimeError("Could not send confirmation")

    with pytest.raises(RuntimeError, match="Could not send"):
        await expenses.receive_amount(message, state)

    bot.delete_message.assert_not_awaited()
    assert prompt_id in bot.messages
    assert await state.get_state() == ExpenseState.waiting_for_amount.state


@pytest.mark.asyncio
async def test_amount_entry_still_works_without_delete_permission():
    bot, ui, state = BotDouble(), ChatUI(), make_state()
    budget, _ = services()
    menu_id = await ui.show(bot, CHAT_ID, MAIN_TEXT, main_keyboard())
    await expenses.choose_category(callback(bot, menu_id, "cat:1"), budget, state, ui)
    prompt_id = (await state.get_data())["prompt_id"]
    bot.delete_message.side_effect = TelegramBadRequest(
        method=DeleteMessage(chat_id=CHAT_ID, message_id=prompt_id),
        message="message can't be deleted",
    )

    await expenses.receive_amount(input_message(bot, "12,50", reply_to=prompt_id), state)

    data = await state.get_data()
    assert data["confirmation_id"] in bot.messages
    assert data["amount_grosz"] == 1250
    assert await state.get_state() == ExpenseState.waiting_for_confirmation.state
