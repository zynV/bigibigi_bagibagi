"""Navigation and expense lifecycles without making Telegram API requests."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import DeleteMessage, EditMessageText
from aiogram.types import ForceReply

from app.bot.handlers import expenses, general, reports
from app.bot.keyboards.main import main_keyboard
from app.bot.states.expense import ExpenseState
from app.bot.ui import ChatUI, MAIN_TEXT, clear_expense
from app.services.budget import Receipt
from app.services.reports import Report

CHAT_ID = -1001234567890


class BotDouble:
    def __init__(self):
        self.messages = {}
        self.next_id = 100
        self.next_input_id = 10000
        self.send_message = AsyncMock(side_effect=self._send)
        self.edit_message_text = AsyncMock(side_effect=self._edit)
        self.delete_message = AsyncMock(side_effect=self._delete)

    async def _send(self, chat_id, text, reply_markup=None):
        await asyncio.sleep(0)
        self.next_id += 1
        message = SimpleNamespace(
            chat=SimpleNamespace(id=chat_id), message_id=self.next_id,
            text=text, reply_markup=reply_markup, bot=self,
        )
        self.messages[message.message_id] = message
        return message

    async def _edit(self, chat_id, message_id, text, reply_markup=None):
        message = self.messages.get(message_id)
        method = EditMessageText(chat_id=chat_id, message_id=message_id, text=text)
        if message is None:
            raise TelegramBadRequest(method=method, message="message to edit not found")
        if message.text == text and message.reply_markup == reply_markup:
            raise TelegramBadRequest(method=method, message="message is not modified")
        message.text, message.reply_markup = text, reply_markup
        return message

    async def _delete(self, chat_id, message_id):
        self.messages.pop(message_id, None)


def make_state(storage=None, user_id=11):
    return FSMContext(
        storage=storage or MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=CHAT_ID, user_id=user_id),
    )


def input_message(bot, text="/menu", user_id=11, reply_to=None):
    async def answer(text, **kwargs):
        return await bot.send_message(CHAT_ID, text, **kwargs)

    bot.next_input_id += 1
    return SimpleNamespace(
        bot=bot, chat=SimpleNamespace(id=CHAT_ID), text=text,
        message_id=bot.next_input_id,
        from_user=SimpleNamespace(id=user_id, full_name=f"Учасник {user_id}"),
        reply_to_message=SimpleNamespace(message_id=reply_to) if reply_to else None,
        answer=AsyncMock(side_effect=answer),
    )


def callback(bot, message_id, data, user_id=11):
    return SimpleNamespace(
        bot=bot, data=data, answer=AsyncMock(),
        message=SimpleNamespace(chat=SimpleNamespace(id=CHAT_ID), message_id=message_id),
        from_user=SimpleNamespace(id=user_id, full_name=f"Учасник {user_id}"),
    )


def services():
    category = SimpleNamespace(id=1, name="Продукти", emoji="🛒")
    budget = SimpleNamespace(
        category=AsyncMock(return_value=category),
        categories=AsyncMock(return_value=[category]),
        add_expense=AsyncMock(return_value=(Receipt(1, "🛒 Продукти", 1250, None), True)),
        delete_expense=AsyncMock(return_value=True),
        undo_last=AsyncMock(return_value=1),
    )
    reporting = SimpleNamespace(
        summary=AsyncMock(return_value=Report(1250, 1, [("🛒 Продукти", 1250)], [("Учасник", 1250)])),
        history=AsyncMock(return_value=[]),
    )
    return budget, reporting


@pytest.mark.asyncio
async def test_navigation_and_commands_reuse_the_same_menu():
    bot, ui, state = BotDouble(), ChatUI(), make_state()
    budget, reporting = services()
    config = SimpleNamespace(admin_user_id=11)

    await general.menu(input_message(bot), state, ui)
    menu_id = next(iter(bot.messages))
    await expenses.add_button(callback(bot, menu_id, "menu:add"), budget, state, ui)
    assert "cat:1" in str(bot.messages[menu_id].reply_markup)
    assert "menu:main" in str(bot.messages[menu_id].reply_markup)

    await reports.report_button(callback(bot, menu_id, "menu:today"), reporting, state, ui)
    assert "12,50 zł" in bot.messages[menu_id].text
    await reports.history_button(
        callback(bot, menu_id, "menu:history"), config, reporting, state, ui,
    )
    assert "Історія порожня" in bot.messages[menu_id].text
    assert "menu:main" in str(bot.messages[menu_id].reply_markup)

    await expenses.delete_by_id(
        callback(bot, menu_id, "del:1"), budget, reporting, config, state, ui,
    )
    assert "видалено з підсумків" in bot.messages[menu_id].text
    await expenses.undo_button(callback(bot, menu_id, "menu:undo"), budget, state, ui)
    await general.menu_button(callback(bot, menu_id, "menu:main"), state, ui)
    await general.menu(input_message(bot), state, ui)

    assert bot.send_message.await_count == 1
    assert list(bot.messages) == [menu_id]
    assert bot.messages[menu_id].text == MAIN_TEXT


@pytest.mark.asyncio
async def test_concurrent_navigation_creates_only_one_menu():
    bot, ui = BotDouble(), ChatUI()
    ids = await asyncio.gather(
        ui.show(bot, CHAT_ID, "Перший екран", main_keyboard()),
        ui.show(bot, CHAT_ID, "Другий екран", main_keyboard()),
    )
    assert ids[0] == ids[1]
    assert bot.send_message.await_count == 1
    assert len(bot.messages) == 1


@pytest.mark.asyncio
async def test_missing_and_stale_menus_are_replaced_without_duplicates():
    bot, ui = BotDouble(), ChatUI()
    original_id = await ui.show(bot, CHAT_ID, "Меню", main_keyboard())
    bot.messages.pop(original_id)
    replacement_id = await ui.show(
        bot, CHAT_ID, "Відновлене меню", main_keyboard(), message_id=original_id,
    )
    assert replacement_id != original_id
    assert list(bot.messages) == [replacement_id]
    stale = await bot.send_message(CHAT_ID, "Старе меню", main_keyboard())
    await ui.show(bot, CHAT_ID, "Історія", main_keyboard(), message_id=stale.message_id)
    assert list(bot.messages) == [replacement_id]


@pytest.mark.asyncio
async def test_invalid_edits_do_not_create_another_menu():
    bot, ui = BotDouble(), ChatUI()
    await ui.show(bot, CHAT_ID, "Меню", main_keyboard())
    bot.edit_message_text.side_effect = TelegramBadRequest(
        method=EditMessageText(chat_id=CHAT_ID, message_id=101, text="bad"),
        message="can't parse entities",
    )
    with pytest.raises(TelegramBadRequest):
        await ui.show(bot, CHAT_ID, "bad", main_keyboard())
    assert bot.send_message.await_count == 1


@pytest.mark.asyncio
async def test_two_users_can_finish_expenses_without_deleting_each_others_prompts():
    bot, ui, storage = BotDouble(), ChatUI(), MemoryStorage()
    first, second = make_state(storage, 11), make_state(storage, 22)
    budget, reporting = services()
    menu_id = await ui.show(bot, CHAT_ID, MAIN_TEXT, main_keyboard())

    await asyncio.gather(
        expenses.choose_category(callback(bot, menu_id, "cat:1", 11), budget, first, ui),
        expenses.choose_category(callback(bot, menu_id, "cat:1", 22), budget, second, ui),
    )
    first_data, second_data = await first.get_data(), await second.get_data()
    assert first_data["prompt_id"] != second_data["prompt_id"]
    assert isinstance(bot.messages[first_data["prompt_id"]].reply_markup, ForceReply)

    # Another participant cannot confirm this user's form.
    await expenses.confirm(
        callback(bot, menu_id, f"ok:{first_data['request_id']}", 22),
        second, budget, reporting, ui,
    )
    budget.add_expense.assert_not_awaited()

    for user_id, state, original_data in ((11, first, first_data), (22, second, second_data)):
        await expenses.receive_amount(
            input_message(bot, "12,50", user_id, original_data["prompt_id"]), state,
        )
        data = await state.get_data()
        assert original_data["prompt_id"] not in bot.messages
        assert data["confirmation_id"] in bot.messages
        await expenses.confirm(
            callback(bot, data["confirmation_id"], f"ok:{data['request_id']}", user_id),
            state, budget, reporting, ui,
        )
        assert data["confirmation_id"] not in bot.messages
        assert await state.get_state() is None
        if user_id == 11:
            assert second_data["prompt_id"] in bot.messages
            assert await second.get_data() == second_data
            assert await second.get_state() == ExpenseState.waiting_for_amount.state

    assert budget.add_expense.await_count == 2
    assert list(bot.messages) == [menu_id]
    assert "Витрату додано" in bot.messages[menu_id].text


@pytest.mark.asyncio
async def test_invalid_amount_warnings_are_cleaned_up_and_unrelated_messages_ignored():
    bot, ui, state = BotDouble(), ChatUI(), make_state()
    budget, _ = services()
    menu_id = await ui.show(bot, CHAT_ID, MAIN_TEXT, main_keyboard())
    await expenses.choose_category(callback(bot, menu_id, "cat:1"), budget, state, ui)
    prompt_id = (await state.get_data())["prompt_id"]
    sent_before = bot.send_message.await_count
    await expenses.receive_amount(input_message(bot, "Звичайне повідомлення"), state)
    assert bot.send_message.await_count == sent_before

    await expenses.receive_amount(input_message(bot, "0", reply_to=prompt_id), state)
    first_error = (await state.get_data())["error_id"]
    await expenses.receive_amount(input_message(bot, "-5", reply_to=prompt_id), state)
    second_error = (await state.get_data())["error_id"]
    assert first_error not in bot.messages
    assert second_error in bot.messages
    await expenses.receive_amount(input_message(bot, "12,50", reply_to=prompt_id), state)
    assert prompt_id not in bot.messages
    assert second_error not in bot.messages

    data = await state.get_data()
    await expenses.discard(
        callback(bot, data["confirmation_id"], f"no:{data['request_id']}"), state, ui,
    )
    assert list(bot.messages) == [menu_id]
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_cancel_only_cleans_up_the_current_user():
    bot, ui, storage = BotDouble(), ChatUI(), MemoryStorage()
    first, second = make_state(storage, 11), make_state(storage, 22)
    budget, _ = services()
    menu_id = await ui.show(bot, CHAT_ID, MAIN_TEXT, main_keyboard())
    await expenses.choose_category(callback(bot, menu_id, "cat:1", 11), budget, first, ui)
    await expenses.choose_category(callback(bot, menu_id, "cat:1", 22), budget, second, ui)
    first_prompt = (await first.get_data())["prompt_id"]
    second_data = await second.get_data()

    await general.cancel(input_message(bot, "/cancel"), first, ui)

    assert first_prompt not in bot.messages
    assert second_data["prompt_id"] in bot.messages
    assert await first.get_state() is None
    assert await second.get_data() == second_data


@pytest.mark.asyncio
async def test_cleanup_tolerates_missing_delete_permissions():
    bot, state = BotDouble(), make_state()
    await state.set_state(ExpenseState.waiting_for_amount)
    await state.update_data(prompt_id=101)
    bot.delete_message.side_effect = TelegramForbiddenError(
        method=DeleteMessage(chat_id=CHAT_ID, message_id=101),
        message="Forbidden",
    )
    await clear_expense(bot, CHAT_ID, state)
    assert await state.get_state() is None
    assert await state.get_data() == {}
