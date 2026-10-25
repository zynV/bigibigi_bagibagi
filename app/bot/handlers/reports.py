from __future__ import annotations

import re
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.bot.keyboards.main import history_keyboard, back_keyboard, month_keyboard
from app.bot.ui import ChatUI, clear_expense
from app.services.dates import current_month, month_label, shift_month
from app.services.money import money
from app.services.reports import Report, ReportService

router = Router(name="reports")
WARSAW = ZoneInfo("Europe/Warsaw")
TITLES = {"today": "📅 Сьогодні", "week": "📆 Цей тиждень"}


def report_text(report: Report, title: str) -> str:
    lines = [f"<b>{title}</b>",
             f"💰 Всього: <b>{money(report.total_grosz)}</b>",
             f"🧾 Операцій: {report.count}"]
    if not report.count:
        lines.append("Витрат за цей період немає.")
    else:
        lines.extend(["", "<b>За категоріями:</b>"])
        lines.extend(f"{escape(cat)} — {money(amount)}" for cat, amount in report.categories)
        lines.extend(["", "<b>За учасниками:</b>"])
        lines.extend(f"👤 {escape(name)} — {money(amount)}" for name, amount in report.authors)
    return "\n".join(lines)


async def send_month_report(
    bot, chat_id: int, year: int, month: int, service: ReportService, ui: ChatUI,
    *, message_id: int | None = None,
) -> None:
    report = await service.monthly_summary(chat_id, year, month)
    await ui.show(
        bot, chat_id, report_text(report, f"📊 {month_label(year, month)}"),
        month_keyboard(year, month), message_id=message_id,
    )


async def send_report(
    bot, chat_id: int, period: str, service: ReportService, ui: ChatUI,
    *, message_id: int | None = None,
) -> None:
    if period == "month":
        year, month = current_month()
        await send_month_report(bot, chat_id, year, month, service, ui, message_id=message_id)
        return
    report = await service.summary(chat_id, period)
    await ui.show(bot, chat_id, report_text(report, TITLES[period]),
                  back_keyboard(), message_id=message_id)


@router.message(Command("today", "week", "month"))
async def report_command(message: Message, reports: ReportService, state: FSMContext, ui: ChatUI):
    period = message.text.split()[0].split("@")[0].removeprefix("/")
    await clear_expense(message.bot, message.chat.id, state)
    await send_report(message.bot, message.chat.id, period, reports, ui)


@router.callback_query(F.data.in_({"menu:today", "menu:week", "menu:month"}))
async def report_button(call: CallbackQuery, reports: ReportService, state: FSMContext, ui: ChatUI):
    await call.answer()
    await clear_expense(call.bot, call.message.chat.id, state)
    await send_report(call.bot, call.message.chat.id, call.data.split(":")[1], reports, ui,
                      message_id=call.message.message_id)


@router.message(Command("months"))
async def months_command(message: Message, reports: ReportService, state: FSMContext, ui: ChatUI):
    year, month = shift_month(*current_month(), -1)
    await clear_expense(message.bot, message.chat.id, state)
    await send_month_report(message.bot, message.chat.id, year, month, reports, ui)


@router.callback_query(F.data == "menu:months")
async def months_button(call: CallbackQuery, reports: ReportService, state: FSMContext, ui: ChatUI):
    year, month = shift_month(*current_month(), -1)
    await call.answer()
    await clear_expense(call.bot, call.message.chat.id, state)
    await send_month_report(call.bot, call.message.chat.id, year, month, reports, ui,
                            message_id=call.message.message_id)


@router.callback_query(F.data.startswith("month:"))
async def month_button(call: CallbackQuery, reports: ReportService, state: FSMContext, ui: ChatUI):
    try:
        selected = re.fullmatch(r"month:(\d{4})-(\d{2})", call.data)
        if selected is None:
            raise ValueError("Invalid month")
        year, month = int(selected[1]), int(selected[2])
        datetime(year, month, 1)
        if (year, month) > current_month():
            raise ValueError("Future month")
    except ValueError:
        await call.answer("Оберіть поточний або попередній місяць.", show_alert=True)
        return
    await call.answer()
    await clear_expense(call.bot, call.message.chat.id, state)
    await send_month_report(call.bot, call.message.chat.id, year, month, reports, ui,
                            message_id=call.message.message_id)


async def send_history(
    bot, chat_id: int, actor_id: int, cfg: Settings, reports: ReportService, ui: ChatUI,
    *, message_id: int | None = None, notice: str | None = None,
):
    items = await reports.history(chat_id)
    lines = [notice, ""] if notice else []
    lines.append("<b>📜 Останні 10 витрат</b>" if items else "📜 Історія порожня.")
    deletable_ids = []
    for item in items:
        local = datetime.fromisoformat(item.occurred_at).astimezone(WARSAW)
        line = (f"\n<b>#{item.id}</b> · {local:%d.%m %H:%M} · {escape(item.category)}\n"
                f"{money(item.amount_grosz)} · {escape(item.author)}")
        if item.note:
            line += f" · {escape(item.note)}"
        lines.append(line)
        if actor_id == cfg.admin_user_id or actor_id == item.author_tg_id:
            deletable_ids.append(item.id)
    await ui.show(bot, chat_id, "\n".join(lines), history_keyboard(deletable_ids),
                  message_id=message_id)


@router.message(Command("history"))
async def history_command(
    message: Message, config: Settings, reports: ReportService, state: FSMContext, ui: ChatUI,
):
    await clear_expense(message.bot, message.chat.id, state)
    await send_history(message.bot, message.chat.id, message.from_user.id, config, reports, ui)


@router.callback_query(F.data == "menu:history")
async def history_button(
    call: CallbackQuery, config: Settings, reports: ReportService, state: FSMContext, ui: ChatUI,
):
    await call.answer()
    await clear_expense(call.bot, call.message.chat.id, state)
    await send_history(call.bot, call.message.chat.id, call.from_user.id, config, reports, ui,
                       message_id=call.message.message_id)
