from __future__ import annotations

import csv
import io
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile
from app.config import Settings
from app.services.reports import ReportService

router = Router(name="export")
WARSAW = ZoneInfo("Europe/Warsaw")


@router.message(Command("export"))
async def export_csv(message: Message, config: Settings, reports: ReportService):
    if message.from_user.id != config.admin_user_id:
        await message.answer("⛔ Експорт доступний лише адміністратору.")
        return
    items = await reports.export(message.chat.id)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=";")
    writer.writerow(["id", "дата_Варшава", "категорія", "сума_PLN", "автор", "telegram_id", "коментар"])
    for item in items:
        local = datetime.fromisoformat(item.occurred_at).astimezone(WARSAW)
        writer.writerow([item.id, local.strftime("%Y-%m-%d %H:%M:%S"), item.category,
                         f"{item.amount_grosz // 100},{item.amount_grosz % 100:02d}",
                         item.author, item.author_tg_id, item.note or ""])
    payload = ("\ufeff" + stream.getvalue()).encode("utf-8")
    filename = f"family-expenses-{datetime.now(WARSAW):%Y-%m-%d}.csv"
    await message.answer_document(BufferedInputFile(payload, filename=filename),
                                  caption=f"📤 Експортовано операцій: {len(items)}")
