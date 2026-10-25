"""Calendar archives and category upgrades preserve persisted expenses."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from app.bot.handlers import reports as report_handlers
from app.bot.keyboards.main import main_keyboard, month_keyboard
from app.bot.states.expense import ExpenseState
from app.bot.ui import ChatUI, MAIN_TEXT
from app.config import Settings
from app.db.models import Base, Category, Expense, Family
from app.db.seed import DEFAULT_CATEGORIES, seed_database
from app.db.session import create_session_factory
from app.services.budget import BudgetService
from app.services.dates import WARSAW, current_month, month_bounds, month_label, shift_month
from app.services.reports import Report, ReportService
from tests.test_bot_ui import CHAT_ID, BotDouble, callback, input_message, make_state


@pytest.mark.parametrize("year,month,start,end,hours", [
    (2026, 10, "2026-10-01", "2026-11-01", 31 * 24 + 1),
    (2026, 3, "2026-03-01", "2026-04-01", 31 * 24 - 1),
    (2024, 2, "2024-02-01", "2024-03-01", 29 * 24),
    (2025, 12, "2025-12-01", "2026-01-01", 31 * 24),
])
def test_month_bounds_follow_the_warsaw_calendar(year, month, start, end, hours):
    lower, upper = map(datetime.fromisoformat, month_bounds(year, month))
    assert lower.astimezone(WARSAW).date().isoformat() == start
    assert upper.astimezone(WARSAW).date().isoformat() == end
    assert (upper - lower).total_seconds() == hours * 3600


@pytest.mark.parametrize("year,month,offset,expected", [
    (2026, 1, -1, (2025, 12)),
    (2025, 12, 1, (2026, 1)),
    (2026, 1, -13, (2024, 12)),
])
def test_month_navigation_crosses_years(year, month, offset, expected):
    assert shift_month(year, month, offset) == expected


@pytest.mark.parametrize("year,month", [(0, 1), (2026, 0), (2026, 13), (10000, 1)])
def test_invalid_calendar_months_are_rejected(year, month):
    with pytest.raises(ValueError):
        month_bounds(year, month)


def test_current_month_uses_warsaw_midnight():
    assert current_month(datetime(2025, 12, 31, 23, 30, tzinfo=timezone.utc)) == (2026, 1)
    assert month_label(2025, 12) == "Грудень 2025"


def keyboard_callbacks(keyboard):
    return {button.callback_data for row in keyboard.inline_keyboard for button in row}


def test_month_keyboard_stops_at_current_month_and_links_back():
    now = datetime(2026, 1, 15, tzinfo=WARSAW)
    assert "menu:months" in keyboard_callbacks(main_keyboard())
    current = keyboard_callbacks(month_keyboard(2026, 1, now=now))
    assert "month:2025-12" in current
    assert "month:2026-02" not in current
    assert "menu:main" in current
    previous = keyboard_callbacks(month_keyboard(2025, 12, now=now))
    assert {"month:2025-11", "month:2026-01", "menu:month", "menu:main"} <= previous
    earliest = keyboard_callbacks(month_keyboard(1, 1, now=now))
    assert "month:0001-02" in earliest
    assert not any(value.startswith("month:0000") for value in earliest)


@pytest_asyncio.fixture
async def database(tmp_path):
    cfg = Settings(
        bot_token="123456789:TEST_TOKEN", group_chat_id=CHAT_ID,
        allowed_user_ids=frozenset({11, 22}), admin_user_id=11, family_name="Тестова сім’я",
        database_path=tmp_path / "budget.sqlite3", backup_dir=tmp_path / "backups",
    )
    engine, sessions = create_session_factory(cfg.database_path)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await seed_database(sessions, cfg)
    try:
        yield cfg, engine, sessions
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_monthly_reports_survive_restart_and_filter_boundaries_and_families(database):
    cfg, engine, sessions = database
    budget = BudgetService(sessions)
    food_id = (await budget.categories(CHAT_ID))[0].id
    rows = [
        (100, 11, datetime(2026, 9, 30, 21, 59, 59, 999999, tzinfo=timezone.utc)),
        (200, 11, datetime(2026, 9, 30, 22, tzinfo=timezone.utc)),
        (300, 22, datetime(2026, 10, 31, 22, 59, 59, 999999, tzinfo=timezone.utc)),
        (400, 11, datetime(2026, 10, 31, 23, tzinfo=timezone.utc)),
        (500, 11, datetime(2026, 10, 15, tzinfo=timezone.utc)),
    ]
    for amount, user_id, stamp in rows:
        receipt, _ = await budget.add_expense(
            CHAT_ID, user_id, food_id, amount, None, uuid4().hex,
            display_name="Перший" if user_id == 11 else "Друга", when=stamp,
        )
    assert await budget.delete_expense(CHAT_ID, 11, receipt.expense_id)

    other_cfg = replace(cfg, group_chat_id=-1009999999999)
    await seed_database(sessions, other_cfg)
    other_food = (await budget.categories(other_cfg.group_chat_id))[0]
    await budget.add_expense(
        other_cfg.group_chat_id, 11, other_food.id, 999990, None, uuid4().hex,
        when=datetime(2026, 10, 15, tzinfo=WARSAW),
    )

    # Reopen the physical SQLite file, as happens after a bot/container restart.
    await engine.dispose()
    reopened_engine, reopened_sessions = create_session_factory(cfg.database_path)
    try:
        await seed_database(reopened_sessions, cfg)
        reporting = ReportService(reopened_sessions)
        october = await reporting.monthly_summary(CHAT_ID, 2026, 10)
        assert october.total_grosz == 500
        assert october.count == 2
        assert october.categories == [("🛒 Продукти", 500)]
        assert october.authors == [("Друга", 300), ("Перший", 200)]
        assert await reporting.summary(
            CHAT_ID, "month", datetime(2026, 10, 25, tzinfo=WARSAW),
        ) == october
        assert (await reporting.monthly_summary(CHAT_ID, 2026, 9)).total_grosz == 100
        assert (await reporting.monthly_summary(CHAT_ID, 2026, 11)).total_grosz == 400
        empty = await reporting.monthly_summary(CHAT_ID, 2026, 8)
        assert empty.total_grosz == 0 and empty.count == 0

        async with reopened_sessions() as session:
            family_id = await session.scalar(select(Family.id).where(Family.chat_id == CHAT_ID))
            assert await session.scalar(select(func.count(Expense.id)).where(
                Expense.family_id == family_id,
            )) == 5  # Soft-deleted expenses also remain stored.
    finally:
        await reopened_engine.dispose()


@pytest.mark.asyncio
async def test_category_upgrade_keeps_ids_and_historical_child_expenses(database):
    cfg, _, sessions = database
    async with sessions.begin() as session:
        family_id = await session.scalar(select(Family.id).where(Family.chat_id == CHAT_ID))
        # Model an existing database with the original ten categories.
        await session.execute(delete(Category).where(
            Category.family_id == family_id,
            Category.name.in_(("Подорожі", "Подарунки", "Покупки", "Beauty")),
        ))
        old = Category(
            family_id=family_id, name="Діти", emoji="👶", sort_order=7, is_active=True,
        )
        session.add(old)
        await session.flush()
        old_id = old.id
        food_id = await session.scalar(select(Category.id).where(
            Category.family_id == family_id, Category.name == "Продукти",
        ))

    budget = BudgetService(sessions)
    receipt, _ = await budget.add_expense(
        CHAT_ID, 11, old_id, 12550, "Історична витрата", uuid4().hex,
        when=datetime(2026, 9, 10, tzinfo=WARSAW),
    )
    await seed_database(sessions, cfg)
    await seed_database(sessions, cfg)

    active = await budget.categories(CHAT_ID)
    assert [item.name for item in active] == [name for name, _ in DEFAULT_CATEGORIES]
    assert len(active) == 13
    assert active[0].id == food_id
    assert await budget.category(CHAT_ID, old_id) is None
    async with sessions() as session:
        retired = await session.get(Category, old_id)
        assert retired.name == "Діти" and retired.is_active is False
        saved = await session.get(Expense, receipt.expense_id)
        assert saved.amount_grosz == 12550 and saved.category_id == old_id
        assert await session.scalar(select(func.count(Category.id)).where(
            Category.family_id == family_id,
        )) == 14

    historical = await ReportService(sessions).monthly_summary(CHAT_ID, 2026, 9)
    assert historical.total_grosz == 12550
    assert historical.categories == [("👶 Діти", 12550)]
    with pytest.raises(ValueError, match="Category not found"):
        await budget.add_expense(CHAT_ID, 11, old_id, 100, None, uuid4().hex)


@pytest.mark.asyncio
async def test_month_archive_navigates_in_one_message_including_empty_months(monkeypatch):
    monkeypatch.setattr(report_handlers, "current_month", lambda: (2026, 1))
    bot, ui, state = BotDouble(), ChatUI(), make_state()
    reporting = type("Reports", (), {})()
    reporting.monthly_summary = AsyncMock(return_value=Report(13000, 1, [("🎁 Подарунки", 13000)], [("Учасник", 13000)]))
    menu_id = await ui.show(bot, CHAT_ID, MAIN_TEXT, main_keyboard())

    await report_handlers.months_button(
        callback(bot, menu_id, "menu:months"), reporting, state, ui,
    )
    reporting.monthly_summary.assert_awaited_with(CHAT_ID, 2025, 12)
    assert "Грудень 2025" in bot.messages[menu_id].text
    assert "130,00 zł" in bot.messages[menu_id].text

    reporting.monthly_summary.return_value = Report(0, 0, [], [])
    await report_handlers.month_button(
        callback(bot, menu_id, "month:2025-11"), reporting, state, ui,
    )
    assert "Листопад 2025" in bot.messages[menu_id].text
    assert "Витрат за цей період немає" in bot.messages[menu_id].text
    assert "month:2025-10" in keyboard_callbacks(bot.messages[menu_id].reply_markup)
    await report_handlers.months_command(input_message(bot, "/months"), reporting, state, ui)
    assert "Грудень 2025" in bot.messages[menu_id].text
    await report_handlers.report_button(
        callback(bot, menu_id, "menu:month"), reporting, state, ui,
    )
    reporting.monthly_summary.assert_awaited_with(CHAT_ID, 2026, 1)
    assert "Січень 2026" in bot.messages[menu_id].text
    assert bot.send_message.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [
    "month:bad", "month:0000-01", "month:2025-00",
    "month:2025-13", "month:2025-1", "month:9999-12",
])
async def test_invalid_or_future_month_does_not_cancel_input(monkeypatch, data):
    monkeypatch.setattr(report_handlers, "current_month", lambda: (2026, 1))
    bot, ui, state = BotDouble(), ChatUI(), make_state()
    reporting = type("Reports", (), {})()
    reporting.monthly_summary = AsyncMock()
    await state.set_state(ExpenseState.waiting_for_amount)
    await state.update_data(prompt_id=1234)
    call = callback(bot, 101, data)
    await report_handlers.month_button(call, reporting, state, ui)
    reporting.monthly_summary.assert_not_awaited()
    assert call.answer.await_args.kwargs["show_alert"] is True
    assert await state.get_state() == ExpenseState.waiting_for_amount.state
