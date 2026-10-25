from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.bot.keyboards.main import main_keyboard, categories_keyboard, back_keyboard
from app.bot.ui import ChatUI, MAIN_TEXT, clear_expense
from app.services.budget import BudgetService

router = Router(name="general")

HELP = (
    "<b>💰 Сімейний бюджет</b>\n"
    "Тут ви разом записуєте витрати у PLN.\n\n"
    "➕ Додати витрату → обрати категорію → ввести суму → підтвердити.\n"
    "Можна вказати коментар одразу після суми: <code>125,50 Biedronka</code>.\n\n"
    "Команди: /menu, /add, /today, /week, /month, /history, "
    "/categories, /undo, /cancel, /export (адмін), /settings, /help."
)


@router.message(CommandStart())
@router.message(Command("menu"))
async def menu(message: Message, state: FSMContext, ui: ChatUI):
    await clear_expense(message.bot, message.chat.id, state)
    await ui.show(message.bot, message.chat.id, MAIN_TEXT, main_keyboard())


@router.callback_query(F.data == "menu:main")
async def menu_button(call: CallbackQuery, state: FSMContext, ui: ChatUI):
    await call.answer()
    await clear_expense(call.bot, call.message.chat.id, state)
    await ui.show(call.bot, call.message.chat.id, MAIN_TEXT, main_keyboard(),
                  message_id=call.message.message_id)


@router.message(Command("help"))
async def help_cmd(message: Message, state: FSMContext, ui: ChatUI):
    await clear_expense(message.bot, message.chat.id, state)
    await ui.show(message.bot, message.chat.id, HELP, back_keyboard())


@router.message(Command("settings"))
async def settings_cmd(message: Message, state: FSMContext, ui: ChatUI):
    await clear_expense(message.bot, message.chat.id, state)
    await ui.show(
        message.bot, message.chat.id,
        "⚙️ <b>Налаштування MVP</b>\n"
        "Валюта: PLN · Часовий пояс: Europe/Warsaw.\n"
        "Категорії фіксовані, редагування — у наступній версії.\n"
        "Експорт CSV: /export (тільки адміністратор).",
        back_keyboard(),
    )


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext, ui: ChatUI):
    await clear_expense(message.bot, message.chat.id, state)
    await ui.show(message.bot, message.chat.id, "✅ Введення скасовано.", main_keyboard())


@router.message(Command("categories"))
async def categories_cmd(message: Message, budget: BudgetService, state: FSMContext, ui: ChatUI):
    rows = await budget.categories(message.chat.id)
    await clear_expense(message.bot, message.chat.id, state)
    await ui.show(message.bot, message.chat.id, "🗂 <b>Категорії витрат</b>",
                  categories_keyboard(rows))


@router.callback_query(F.data == "menu:categories")
async def categories_cb(call: CallbackQuery, budget: BudgetService, state: FSMContext, ui: ChatUI):
    rows = await budget.categories(call.message.chat.id)
    await call.answer()
    await clear_expense(call.bot, call.message.chat.id, state)
    await ui.show(call.bot, call.message.chat.id, "🗂 <b>Категорії витрат</b>",
                  categories_keyboard(rows), message_id=call.message.message_id)
