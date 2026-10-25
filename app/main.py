"""Entry point: python -m app.main, after `alembic upgrade head`."""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.fsm.strategy import FSMStrategy

from app.config import Settings
from app.db.session import create_session_factory
from app.db.seed import seed_database
from app.services.budget import BudgetService
from app.services.reports import ReportService
from app.services.backup import BackupManager, backup_loop
from app.bot.ui import ChatUI
from app.bot.middlewares.access import AccessMiddleware
from app.bot.middlewares.cleanup import CommandCleanupMiddleware
from app.bot.handlers import general, expenses, reports, categories, export


async def main() -> None:
    cfg = Settings.from_env()
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    engine, sessions = create_session_factory(cfg.database_path)
    try:
        # The container CMD applies schema migrations before the bot starts.
        await seed_database(sessions, cfg)
        dp = Dispatcher(storage=MemoryStorage(), events_isolation=SimpleEventIsolation(),
                        fsm_strategy=FSMStrategy.USER_IN_CHAT)
        dp["config"] = cfg
        dp["ui"] = ChatUI()
        dp["budget"] = BudgetService(sessions)
        dp["reports"] = ReportService(sessions)
        access = AccessMiddleware(cfg)
        dp.message.outer_middleware(access)
        dp.message.middleware(CommandCleanupMiddleware())
        dp.callback_query.outer_middleware(access)
        dp.include_routers(general.router, expenses.router, reports.router, categories.router, export.router)
        bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        backup_task = asyncio.create_task(backup_loop(BackupManager(cfg.database_path, cfg.backup_dir)))
        try:
            await bot.delete_webhook(drop_pending_updates=False)
            logging.info("Bot started with long polling (authorized chat %s)", cfg.group_chat_id)
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        finally:
            backup_task.cancel()
            with suppress(asyncio.CancelledError):
                await backup_task
            await bot.session.close()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
