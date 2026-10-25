"""User input is removed only after the expense has been saved and acknowledged."""
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import DeleteMessage

from app.bot.handlers import expenses
from app.bot.keyboards.main import main_keyboard
from app.bot.states.expense import ExpenseState
from app.bot.ui import ChatUI, DELETE_PERMISSION_NOTICE, MAIN_TEXT, delete_message
from tests.test_bot_ui import CHAT_ID, BotDouble, callback, input_message, make_state, services


def deleted_ids(bot):
    return {call.kwargs["message_id"] for call in bot.delete_message.await_args_list}


async def pending_form(with_invalid=False):
    bot, ui, state = BotDouble(), ChatUI(), make_state()
    budget, reports = services()
    menu_id = await ui.show(bot, CHAT_ID, MAIN_TEXT, main_keyboard())
    await expenses.choose_category(callback(bot, menu_id, "cat:1"), budget, state, ui)
    prompt_id = (await state.get_data())["prompt_id"]
    if with_invalid:
        await expenses.receive_amount(input_message(bot, "0", reply_to=prompt_id), state)
    await expenses.receive_amount(input_message(bot, "12,50", reply_to=prompt_id), state)
    return SimpleNamespace(
        bot=bot, ui=ui, state=state, budget=budget, reports=reports,
        menu_id=menu_id, data=await state.get_data(),
    )


async def confirm(form):
    await expenses.confirm(
        callback(form.bot, form.data["confirmation_id"], f"ok:{form.data['request_id']}"),
        form.state, form.budget, form.reports, form.ui,
    )


@pytest.mark.asyncio
async def test_all_attempts_are_removed_only_after_save_and_success_message():
    form = await pending_form(with_invalid=True)
    inputs = set(form.data["input_message_ids"])
    assert len(inputs) == 2
    assert inputs.isdisjoint(deleted_ids(form.bot))
    saved = False
    result = form.budget.add_expense.return_value

    async def save(*args, **kwargs):
        nonlocal saved
        assert inputs.isdisjoint(deleted_ids(form.bot))
        saved = True
        return result

    async def delete(chat_id, message_id):
        if message_id in inputs:
            assert saved
            assert "Витрату додано" in form.bot.messages[form.menu_id].text
        return await form.bot._delete(chat_id, message_id)

    form.budget.add_expense.side_effect = save
    form.bot.delete_message.side_effect = delete
    await confirm(form)

    assert inputs <= deleted_ids(form.bot)
    form.budget.add_expense.assert_awaited_once()
    assert await form.state.get_state() is None
    assert await form.state.get_data() == {}
    assert list(form.bot.messages) == [form.menu_id]


@pytest.mark.asyncio
async def test_failed_save_preserves_input_and_confirmation_for_retry():
    form = await pending_form()
    inputs = set(form.data["input_message_ids"])
    form.bot.delete_message.reset_mock()
    form.budget.add_expense.side_effect = RuntimeError("Database is unavailable")

    with pytest.raises(RuntimeError, match="Database is unavailable"):
        await confirm(form)

    form.bot.delete_message.assert_not_awaited()
    assert inputs.isdisjoint(deleted_ids(form.bot))
    assert await form.state.get_state() == ExpenseState.waiting_for_confirmation.state
    assert form.data["confirmation_id"] in form.bot.messages


@pytest.mark.asyncio
async def test_rejected_expense_does_not_delete_the_users_unsaved_amount():
    form = await pending_form()
    form.budget.add_expense.side_effect = ValueError("Category is inactive")
    await confirm(form)
    assert set(form.data["input_message_ids"]).isdisjoint(deleted_ids(form.bot))
    assert "Створіть нову витрату" in form.bot.messages[form.menu_id].text
    assert await form.state.get_state() is None


@pytest.mark.asyncio
async def test_failed_success_message_keeps_input_available():
    form = await pending_form()
    form.bot.delete_message.reset_mock()

    async def unavailable(*args, **kwargs):
        raise RuntimeError("Telegram is unavailable")

    form.ui.show = unavailable
    with pytest.raises(RuntimeError, match="Telegram is unavailable"):
        await confirm(form)

    form.budget.add_expense.assert_awaited_once()
    form.bot.delete_message.assert_not_awaited()
    assert await form.state.get_state() == ExpenseState.waiting_for_confirmation.state


@pytest.mark.asyncio
async def test_refused_input_deletion_shows_help_in_the_existing_menu(caplog):
    form = await pending_form()
    inputs = set(form.data["input_message_ids"])

    async def refused(chat_id, message_id):
        if message_id in inputs:
            raise TelegramBadRequest(
                method=DeleteMessage(chat_id=chat_id, message_id=message_id),
                message="not enough rights to delete messages",
            )
        return await form.bot._delete(chat_id, message_id)

    form.bot.delete_message.side_effect = refused
    await confirm(form)

    assert DELETE_PERMISSION_NOTICE in form.bot.messages[form.menu_id].text
    assert "not enough rights to delete messages" in caplog.text
    assert await form.state.get_state() is None
    form.budget.add_expense.assert_awaited_once()
    assert form.bot.send_message.await_count == 3
    assert list(form.bot.messages) == [form.menu_id]


@pytest.mark.asyncio
async def test_an_already_deleted_message_is_successful_cleanup(caplog):
    bot = BotDouble()
    bot.delete_message.side_effect = TelegramBadRequest(
        method=DeleteMessage(chat_id=CHAT_ID, message_id=501),
        message="Bad Request: message to delete not found",
    )
    assert await delete_message(bot, CHAT_ID, 501)
    assert "Could not delete" not in caplog.text


@pytest.mark.asyncio
async def test_completing_one_expense_keeps_the_other_users_input():
    bot, ui, storage = BotDouble(), ChatUI(), MemoryStorage()
    budget, reports = services()
    first, second = make_state(storage, 11), make_state(storage, 22)
    menu_id = await ui.show(bot, CHAT_ID, MAIN_TEXT, main_keyboard())
    for user_id, state in ((11, first), (22, second)):
        await expenses.choose_category(callback(bot, menu_id, "cat:1", user_id), budget, state, ui)
        prompt_id = (await state.get_data())["prompt_id"]
        await expenses.receive_amount(input_message(bot, "12,50", user_id, prompt_id), state)
    first_data, second_data = await first.get_data(), await second.get_data()

    await expenses.confirm(
        callback(bot, first_data["confirmation_id"], f"ok:{first_data['request_id']}"),
        first, budget, reports, ui,
    )

    assert set(first_data["input_message_ids"]) <= deleted_ids(bot)
    assert set(second_data["input_message_ids"]).isdisjoint(deleted_ids(bot))
    assert await second.get_data() == second_data
    assert second_data["confirmation_id"] in bot.messages
