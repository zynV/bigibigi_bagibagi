from __future__ import annotations

from datetime import datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.db.models import Category
from app.services.dates import current_month, shift_month


def main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for text, code in (
        ("➕ Додати витрату", "menu:add"),
        ("📅 Сьогодні", "menu:today"), ("📆 Тиждень", "menu:week"),
        ("📊 Місяць", "menu:month"), ("📜 Історія", "menu:history"),
        ("🗓 Попередні місяці", "menu:months"),
        ("🗂 Категорії", "menu:categories"), ("↩️ Скасувати останню", "menu:undo"),
    ):
        builder.button(text=text, callback_data=code)
    builder.adjust(1, 2, 2, 1, 2)
    return builder.as_markup()


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Головне меню", callback_data="menu:main"),
    ]])


def month_keyboard(
    year: int, month: int, *, now: datetime | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    selected, current = (year, month), current_month(now)
    navigation = []
    if selected > (1, 1):
        previous_year, previous_month = shift_month(year, month, -1)
        navigation.append(InlineKeyboardButton(
            text="⬅️ Раніше", callback_data=f"month:{previous_year:04d}-{previous_month:02d}",
        ))
    if selected < current:
        next_year, next_month = shift_month(year, month, 1)
        navigation.append(InlineKeyboardButton(
            text="Пізніше ➡️", callback_data=f"month:{next_year:04d}-{next_month:02d}",
        ))
    if navigation:
        builder.row(*navigation)
    if selected != current:
        builder.row(InlineKeyboardButton(text="📊 Поточний місяць", callback_data="menu:month"))
    builder.row(InlineKeyboardButton(text="⬅️ Головне меню", callback_data="menu:main"))
    return builder.as_markup()


def categories_keyboard(
    categories: list[Category], *, browsing: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    prefix = "viewcat" if browsing else "cat"
    for cat in categories:
        builder.button(text=f"{cat.emoji} {cat.name}", callback_data=f"{prefix}:{cat.id}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⬅️ Головне меню", callback_data="menu:main"))
    return builder.as_markup()


def category_periods_keyboard(
    category_id: int, *, period: str | None = None, page: int = 0, pages: int = 1,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    navigation = []
    if period is not None and page > 0:
        navigation.append(InlineKeyboardButton(
            text="⬅️ Попередні", callback_data=f"catreport:{category_id}:{period}:{page - 1}",
        ))
    if period is not None and page + 1 < pages:
        navigation.append(InlineKeyboardButton(
            text="Наступні ➡️", callback_data=f"catreport:{category_id}:{period}:{page + 1}",
        ))
    if navigation:
        builder.row(*navigation)
    builder.row(*[
        InlineKeyboardButton(text=label, callback_data=f"catreport:{category_id}:{value}:0")
        for label, value in (("📅 День", "today"), ("📆 Тиждень", "week"), ("📊 Місяць", "month"))
    ])
    builder.row(InlineKeyboardButton(text="⬅️ Категорії", callback_data="menu:categories"))
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
