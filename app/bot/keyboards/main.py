from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.db.models import Category


def main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for text, code in (
        ("➕ Додати витрату", "menu:add"),
        ("📅 Сьогодні", "menu:today"), ("📆 Тиждень", "menu:week"),
        ("📊 Місяць", "menu:month"), ("📜 Історія", "menu:history"),
        ("🗂 Категорії", "menu:categories"), ("↩️ Скасувати останню", "menu:undo"),
    ):
        builder.button(text=text, callback_data=code)
    builder.adjust(1, 2, 2, 2)
    return builder.as_markup()


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Головне меню", callback_data="menu:main"),
    ]])


def categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=f"{cat.emoji} {cat.name}", callback_data=f"cat:{cat.id}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⬅️ Головне меню", callback_data="menu:main"))
    return builder.as_markup()


def confirmation_keyboard(request_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"ok:{request_id}"),
        InlineKeyboardButton(text="❌ Скасувати", callback_data=f"no:{request_id}"),
    ]])


def history_keyboard(ids: list[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for id_ in ids:
        builder.button(text=f"🗑 Видалити #{id_}", callback_data=f"del:{id_}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⬅️ Головне меню", callback_data="menu:main"))
    return builder.as_markup()
