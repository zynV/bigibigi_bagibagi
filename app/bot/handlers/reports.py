from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.bot.keyboards.main import history_keyboard
from app.services.money import money
from app.services.reports import ReportService

router = Router(name="reports")
WARSAW = ZoneInfo("Europe/Warsaw")
TITLES = {"today": "📅 Сьогодні", "week": "📆 Цей тиждень", "month": "📊 Цей місяць"}


async def send_report(bot, chat_id: int, period: str, service: ReportService) -> None:
    report = await service.summary(chat_id, period)
    lines = [f"<b>{TITLES[period]}</b>",
             f"💰 Всього: <b>{money(report.total_grosz)}</b>",
             f"🧾 Операцій: {report.count}"]
    if not report.count:
        lines.append("Витрат поки немає.")
    else:
        lines.extend(["", "<b>За категоріями:</b>"])
        lines.extend(f"{escape(cat)} — {money(amount)}" for cat, amount in report.categories)
        lines.extend(["", "<b>За учасниками:</b>"])
        lines.extend(f"👤 {escape(name)} — {money(amount)}" for name, amount in report.authors)
    await bot.send_message(chat_id, "\n".join(lines))


@router.message(Command("today", "week", "month"))
async def report_command(message: Message, reports: ReportService):
    period = message.text.split()[0].split("@")[0].removeprefix("/")
    await send_report(message.bot, message.chat.id, period, reports)


@router.callback_query(F.data.in_({"menu:today", "menu:week", "menu:month"}))
async def report_button(call: CallbackQuery, reports: ReportService):
    await call.answer()
    await send_report(call.bot, call.message.chat.id, call.data.split(":")[1], reports)


async def send_history(bot, chat_id: int, actor_id: int, cfg: Settings, reports: ReportService):
    items = await reports.history(chat_id)
    if not items:
        await bot.send_message(chat_id, "📜 Історія порожня.")
        return
    lines = ["<b>📜 Останні 10 витрат</b>"]
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
    await bot.send_message(chat_id, "\n".join(lines), reply_markup=history_keyboard(deletable_ids))


@router.message(Command("history"))
async def history_command(message: Message, config: Settings, reports: ReportService):
    await send_history(message.bot, message.chat.id, message.from_user.id, config, reports)


@router.callback_query(F.data == "menu:history")
async def history_button(call: CallbackQuery, config: Settings, reports: ReportService):
    await call.answer()
    await send_history(call.bot, call.message.chat.id, call.from_user.id, config, reports)
