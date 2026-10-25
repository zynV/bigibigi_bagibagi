"""Browse expenses by category without entering the expense creation flow."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.keyboards.main import category_periods_keyboard
from app.bot.ui import ChatUI, clear_expense
from app.services.budget import BudgetService
from app.services.dates import WARSAW
from app.services.money import money
from app.services.reports import CategoryReport, ReportService

router = Router(name="category_reports")
PERIOD_TITLES = {"today": "День", "week": "Тиждень", "month": "Місяць"}


def category_report_text(report: CategoryReport, period: str) -> str:
    first = datetime.fromisoformat(report.start).astimezone(WARSAW).date()
    last = datetime.fromisoformat(report.end).astimezone(WARSAW).date() - timedelta(days=1)
    dates = f"{first:%d.%m.%Y}" if first == last else f"{first:%d.%m} – {last:%d.%m.%Y}"
    lines = [
        f"<b>🗂 {escape(report.category)}</b>",
        f"{PERIOD_TITLES[period]} · {dates}",
        f"💰 Всього: <b>{money(report.total_grosz)}</b>",
        f"🧾 Операцій: {report.count}",
    ]
    if not report.items:
        lines.extend(["", "Витрат у цій категорії за обраний період немає."])
    for item in report.items:
        local = datetime.fromisoformat(item.occurred_at).astimezone(WARSAW)
        lines.append(
            f"\n<b>#{item.id}</b> · {local:%d.%m %H:%M}\n"
            f"<b>{money(item.amount_grosz)}</b> · {escape(item.author)}"
        )
        if item.note:
            lines.append(f"📝 {escape(item.note)}")
    if report.pages > 1:
        lines.append(f"\nСторінка {report.page + 1} з {report.pages}")
    return "\n".join(lines)


def category_id(value: str) -> int:
    parsed = int(value)
    if not 0 < parsed < 2**63:
        raise ValueError("Invalid category ID")
    return parsed


@router.callback_query(F.data.startswith("viewcat:"))
async def choose_category(
    call: CallbackQuery, budget: BudgetService, state: FSMContext, ui: ChatUI,
):
    try:
        selected_id = category_id(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await call.answer("Некоректна категорія.", show_alert=True)
        return
    category = await budget.category(call.message.chat.id, selected_id)
    if category is None:
        await call.answer("Ця категорія більше недоступна.", show_alert=True)
        return
    await call.answer()
    await clear_expense(call.bot, call.message.chat.id, state)
    await ui.show(
        call.bot, call.message.chat.id,
        f"<b>🗂 {escape(category.emoji + ' ' + category.name)}</b>\nОберіть період:",
        category_periods_keyboard(selected_id), message_id=call.message.message_id,
    )


@router.callback_query(F.data.startswith("catreport:"))
async def show_category_report(
    call: CallbackQuery, reports: ReportService, state: FSMContext, ui: ChatUI,
):
    try:
        match = re.fullmatch(r"catreport:([1-9]\d*):(today|week|month):(\d+)", call.data)
        if match is None:
            raise ValueError("Invalid report selection")
        selected_id = category_id(match[1])
        period, page = match[2], int(match[3])
        report = await reports.category_report(
            call.message.chat.id, selected_id, period, page=page,
        )
    except ValueError:
        await call.answer("Категорія або період недоступні.", show_alert=True)
        return
    await call.answer()
    await clear_expense(call.bot, call.message.chat.id, state)
    await ui.show(
        call.bot, call.message.chat.id, category_report_text(report, period),
        category_periods_keyboard(
            selected_id, period=period, page=report.page, pages=report.pages,
        ),
        message_id=call.message.message_id,
    )
