from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.bot.keyboards.main import main_keyboard, categories_keyboard
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
async def menu(message: Message):
    await message.answer("<b>💰 Сімейний бюджет</b>\nОберіть дію:", reply_markup=main_keyboard())


@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(HELP)


@router.message(Command("settings"))
async def settings_cmd(message: Message):
    await message.answer(
        "⚙️ <b>Налаштування MVP</b>\n"
        "Валюта: PLN · Часовий пояс: Europe/Warsaw.\n"
        "Категорії фіксовані, редагування — у наступній версії.\n"
        "Експорт CSV: /export (тільки адміністратор)."
    )


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Введення скасовано.")


@router.message(Command("categories"))
async def categories_cmd(message: Message, budget: BudgetService):
    rows = await budget.categories(message.chat.id)
    await message.answer("🗂 <b>Категорії витрат</b>", reply_markup=categories_keyboard(rows))


@router.callback_query(F.data == "menu:categories")
async def categories_cb(call: CallbackQuery, budget: BudgetService):
    rows = await budget.categories(call.message.chat.id)
    await call.answer()
    await call.bot.send_message(call.message.chat.id, "🗂 <b>Категорії витрат</b>",
                                reply_markup=categories_keyboard(rows))
