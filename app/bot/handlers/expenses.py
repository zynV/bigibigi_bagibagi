from __future__ import annotations

from html import escape
from uuid import uuid4

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, ForceReply

from app.config import Settings
from app.bot.states.expense import ExpenseState
from app.bot.keyboards.main import categories_keyboard, confirmation_keyboard, main_keyboard
from app.bot.ui import ChatUI, MAIN_TEXT, clear_expense, delete_message
from app.bot.handlers.reports import send_history
from app.services.money import money, parse_expense
from app.services.budget import BudgetService
from app.services.reports import ReportService

router = Router(name="expenses")


@router.message(Command("add"))
async def add_command(message: Message, budget: BudgetService, state: FSMContext, ui: ChatUI):
    rows = await budget.categories(message.chat.id)
    await clear_expense(message.bot, message.chat.id, state)
    await ui.show(message.bot, message.chat.id, "➕ <b>Оберіть категорію:</b>",
                  categories_keyboard(rows))


@router.callback_query(F.data == "menu:add")
async def add_button(call: CallbackQuery, budget: BudgetService, state: FSMContext, ui: ChatUI):
    rows = await budget.categories(call.message.chat.id)
    await call.answer()
    await clear_expense(call.bot, call.message.chat.id, state)
    await ui.show(call.bot, call.message.chat.id, "➕ <b>Оберіть категорію:</b>",
                  categories_keyboard(rows), message_id=call.message.message_id)


@router.callback_query(F.data.startswith("cat:"))
async def choose_category(call: CallbackQuery, budget: BudgetService, state: FSMContext, ui: ChatUI):
    try:
        category_id = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await call.answer("Некоректна категорія", show_alert=True)
        return
    category = await budget.category(call.message.chat.id, category_id)
    if not category:
        await call.answer("Ця категорія більше недоступна.", show_alert=True)
        return
    await call.answer()
    await clear_expense(call.bot, call.message.chat.id, state)
    await ui.show(call.bot, call.message.chat.id, MAIN_TEXT, main_keyboard(),
                  message_id=call.message.message_id)
    # ForceReply needs a separate message for Telegram Privacy Mode.
    prompt = await call.bot.send_message(
        call.message.chat.id,
        f"👤 <a href=\"tg://user?id={call.from_user.id}\">{escape(call.from_user.full_name)}</a>, "
        f"введіть суму для <b>{escape(category.emoji + ' ' + category.name)}</b>.\n"
        "Приклад: <code>125,50</code> або <code>125,50 Biedronka</code>.\n"
        "Скасувати: /cancel",
        reply_markup=ForceReply(selective=False, input_field_placeholder="125,50"),
    )
    await state.set_state(ExpenseState.waiting_for_amount)
    await state.update_data(
        category_id=category.id, category_title=f"{category.emoji} {category.name}",
        request_id=uuid4().hex, prompt_id=prompt.message_id,
    )


@router.message(ExpenseState.waiting_for_amount, F.text)
async def receive_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    # Leave unrelated group conversation alone.
    if not message.reply_to_message or message.reply_to_message.message_id != data.get("prompt_id"):
        return
    try:
        amount, note = parse_expense(message.text)
    except ValueError as exc:
        warning = await message.answer(
            f"⚠️ {escape(str(exc))}\nВідповідайте на попередній запит ще раз.",
        )
        await delete_message(message.bot, message.chat.id, data.get("error_id"))
        await state.update_data(error_id=warning.message_id)
        await delete_message(message.bot, message.chat.id, message.message_id)
        return
    note_line = f"\n📝 {escape(note)}" if note else ""
    confirmation = await message.answer(
        f"<b>Підтвердити витрату?</b>\n{escape(data['category_title'])}\n"
        f"💵 <b>{money(amount)}</b>{note_line}",
        reply_markup=confirmation_keyboard(data["request_id"]),
    )
    await state.update_data(
        amount_grosz=amount, note=note, confirmation_id=confirmation.message_id,
        prompt_id=None, error_id=None,
    )
    await state.set_state(ExpenseState.waiting_for_confirmation)
    await delete_message(message.bot, message.chat.id, data.get("prompt_id"))
    await delete_message(message.bot, message.chat.id, data.get("error_id"))
    await delete_message(message.bot, message.chat.id, message.message_id)


@router.callback_query(F.data.startswith("ok:"))
async def confirm(
    call: CallbackQuery, state: FSMContext, budget: BudgetService,
    reports: ReportService, ui: ChatUI,
):
    data = await state.get_data()
    request_id = call.data.removeprefix("ok:")
    if await state.get_state() != ExpenseState.waiting_for_confirmation.state or data.get("request_id") != request_id:
        await call.answer("Це підтвердження застаріло або належить іншому користувачу.", show_alert=True)
        return
    try:
        receipt, created = await budget.add_expense(
            call.message.chat.id, call.from_user.id, data["category_id"],
            data["amount_grosz"], data["note"], request_id,
            display_name=call.from_user.full_name,
        )
    except ValueError:
        await clear_expense(call.bot, call.message.chat.id, state)
        await ui.show(call.bot, call.message.chat.id,
                      "⚠️ Категорія або сума вже неактуальні. Створіть нову витрату.",
                      main_keyboard())
        await call.answer()
        return
    await call.answer()
    today = await reports.summary(call.message.chat.id, "today")
    text = (
        f"{'✅ Витрату додано!' if created else '✅ Витрата вже була збережена.'}\n"
        f"{escape(receipt.category)} — <b>{money(receipt.amount_grosz)}</b>\n"
        f"👤 {escape(call.from_user.full_name)}\n"
        f"📅 Сьогодні витрачено: <b>{money(today.total_grosz)}</b>"
    )
    await ui.show(call.bot, call.message.chat.id, text, main_keyboard())
    await clear_expense(call.bot, call.message.chat.id, state)


@router.callback_query(F.data.startswith("no:"))
async def discard(call: CallbackQuery, state: FSMContext, ui: ChatUI):
    data = await state.get_data()
    if data.get("request_id") != call.data.removeprefix("no:"):
        await call.answer("Неактуальне підтвердження.", show_alert=True)
        return
    await call.answer()
    await ui.show(call.bot, call.message.chat.id, "❌ Введення витрати скасовано.", main_keyboard())
    await clear_expense(call.bot, call.message.chat.id, state)


@router.message(Command("undo"))
async def undo_command(message: Message, budget: BudgetService, state: FSMContext, ui: ChatUI):
    id_ = await budget.undo_last(message.chat.id, message.from_user.id)
    await clear_expense(message.bot, message.chat.id, state)
    text = f"↩️ Останню вашу витрату #{id_} скасовано." if id_ else "Немає витрат для скасування."
    await ui.show(message.bot, message.chat.id, text, main_keyboard())


@router.callback_query(F.data == "menu:undo")
async def undo_button(call: CallbackQuery, budget: BudgetService, state: FSMContext, ui: ChatUI):
    id_ = await budget.undo_last(call.message.chat.id, call.from_user.id)
    await call.answer()
    await clear_expense(call.bot, call.message.chat.id, state)
    text = (
        f"↩️ {escape(call.from_user.full_name)} скасувала/скасував свою витрату #{id_}."
        if id_ else "Немає ваших витрат для скасування."
    )
    await ui.show(call.bot, call.message.chat.id, text, main_keyboard(),
                  message_id=call.message.message_id)


@router.callback_query(F.data.startswith("del:"))
async def delete_by_id(
    call: CallbackQuery, budget: BudgetService, reports: ReportService,
    config: Settings, state: FSMContext, ui: ChatUI,
):
    try:
        expense_id = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await call.answer("Некоректний ID", show_alert=True)
        return
    success = await budget.delete_expense(call.message.chat.id, call.from_user.id, expense_id)
    if not success:
        await call.answer("⛔ Немає прав або витрата вже видалена", show_alert=True)
        return
    await call.answer()
    await clear_expense(call.bot, call.message.chat.id, state)
    await send_history(
        call.bot, call.message.chat.id, call.from_user.id, config, reports, ui,
        message_id=call.message.message_id,
        notice=f"🗑 Витрату #{expense_id} видалено з підсумків.",
    )
