"""Read-only category browsing, period filtering, and complete paginated lists."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from html import unescape
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.bot.handlers import categories, expenses, general
from app.bot.keyboards.main import categories_keyboard, category_periods_keyboard, main_keyboard
from app.bot.states.expense import ExpenseState
from app.bot.ui import ChatUI, MAIN_TEXT
from app.db.models import Expense, Family
from app.db.seed import seed_database
from app.services.budget import BudgetService
from app.services.dates import WARSAW, period_bounds
from app.services.reports import CATEGORY_PAGE_SIZE, CategoryReport, HistoryItem, ReportService
from tests.test_bot_ui import CHAT_ID, BotDouble, callback, input_message, make_state, services
from tests.test_month_archive import database

NOW = datetime(2026, 10, 25, 12, tzinfo=WARSAW)


def callbacks(keyboard):
    return {button.callback_data for row in keyboard.inline_keyboard for button in row}


def sample_report(period="month", *, page=0, pages=1):
    start, end = period_bounds(period, NOW)
    return CategoryReport(
        category="☕ Кафе та ресторани", total_grosz=13000, count=1,
        items=[HistoryItem(
            1, NOW.astimezone(timezone.utc).isoformat(), "☕ Кафе та ресторани",
            13000, "Bohdan <B>", 11, "Кава & десерт <3",
        )],
        page=page, pages=pages, start=start, end=end,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("period,expected_amounts", [
    ("today", {1000, 2000}),
    ("week", {1000, 2000, 3000}),
    ("month", {1000, 2000, 3000, 4000, 5000, 7000}),
])
async def test_category_report_filters_period_category_deletion_and_family(database, period, expected_amounts):
    cfg, _, sessions = database
    budget = BudgetService(sessions)
    active = {item.name: item.id for item in await budget.categories(CHAT_ID)}
    cafe_id = active["Кафе та ресторани"]
    assert "Beauty" in active
    rows = [
        (1000, datetime(2026, 10, 25, 0, tzinfo=WARSAW)),
        (2000, datetime(2026, 10, 25, 3, 30, tzinfo=WARSAW)),
        (3000, datetime(2026, 10, 19, 0, tzinfo=WARSAW)),
        (4000, datetime(2026, 10, 18, 23, 59, 59, 999999, tzinfo=WARSAW)),
        (5000, datetime(2026, 10, 1, 0, tzinfo=WARSAW)),
        (6000, datetime(2026, 9, 30, 23, 59, 59, 999999, tzinfo=WARSAW)),
        (7000, datetime(2026, 10, 26, 0, tzinfo=WARSAW)),
        (8000, datetime(2026, 11, 1, 0, tzinfo=WARSAW)),
    ]
    for index, (amount, stamp) in enumerate(rows):
        await budget.add_expense(
            CHAT_ID, 11 if index % 2 else 22, cafe_id, amount, f"Коментар {amount}",
            uuid4().hex, display_name="Перший" if index % 2 else "Друга", when=stamp,
        )
    deleted, _ = await budget.add_expense(
        CHAT_ID, 11, cafe_id, 9000, "Видалена", uuid4().hex, when=NOW,
    )
    await budget.delete_expense(CHAT_ID, 11, deleted.expense_id)
    await budget.add_expense(CHAT_ID, 11, active["Beauty"], 9900, "Інша категорія", uuid4().hex, when=NOW)

    other = replace(cfg, group_chat_id=-1009999999999)
    await seed_database(sessions, other)
    other_cafe = next(item for item in await budget.categories(other.group_chat_id) if item.name == "Кафе та ресторани")
    await budget.add_expense(other.group_chat_id, 11, other_cafe.id, 99900, "Інша сім’я", uuid4().hex, when=NOW)

    reporting = ReportService(sessions)
    first = await reporting.category_report(CHAT_ID, cafe_id, period, now=NOW)
    items = []
    for page in range(first.pages):
        result = await reporting.category_report(CHAT_ID, cafe_id, period, page=page, now=NOW)
        assert result.total_grosz == sum(expected_amounts)
        assert result.count == len(expected_amounts)
        items.extend(result.items)
    assert {item.amount_grosz for item in items} == expected_amounts
    assert {item.note for item in items} == {f"Коментар {amount}" for amount in expected_amounts}
    assert all(item.author in {"Перший", "Друга"} for item in items)


@pytest.mark.asyncio
async def test_all_expenses_are_available_across_pages_without_a_ten_row_cutoff(database):
    _, _, sessions = database
    budget = BudgetService(sessions)
    beauty = next(item for item in await budget.categories(CHAT_ID) if item.name == "Beauty")
    saved_ids = []
    for index in range(12):
        receipt, _ = await budget.add_expense(
            CHAT_ID, 11, beauty.id, 100 + index, f"Beauty {index}", uuid4().hex,
            when=NOW + timedelta(seconds=index),
        )
        saved_ids.append(receipt.expense_id)
    reporting = ReportService(sessions)
    seen = []
    for page in range(3):
        result = await reporting.category_report(CHAT_ID, beauty.id, "month", page=page, now=NOW)
        assert result.pages == 3 and result.page == page
        assert result.total_grosz == 1266 and result.count == 12
        assert len(result.items) <= CATEGORY_PAGE_SIZE
        seen.extend(item.id for item in result.items)
    assert seen == list(reversed(saved_ids))
    clamped = await reporting.category_report(CHAT_ID, beauty.id, "month", page=10**100, now=NOW)
    assert clamped.page == 2 and len(clamped.items) == 2
    async with sessions() as session:
        assert await session.scalar(select(func.count(Expense.id))) == 12


@pytest.mark.asyncio
async def test_unavailable_categories_and_invalid_periods_are_rejected(database):
    cfg, _, sessions = database
    reporting = ReportService(sessions)
    budget = BudgetService(sessions)
    category = (await budget.categories(CHAT_ID))[0]
    other = replace(cfg, group_chat_id=-1009999999999)
    await seed_database(sessions, other)
    foreign = (await budget.categories(other.group_chat_id))[0]
    with pytest.raises(ValueError, match="Category not found"):
        await reporting.category_report(CHAT_ID, foreign.id, "month", now=NOW)
    with pytest.raises(ValueError, match="Unknown period"):
        await reporting.category_report(CHAT_ID, category.id, "year", now=NOW)
    with pytest.raises(ValueError, match="non-negative"):
        await reporting.category_report(CHAT_ID, category.id, "month", page=-1, now=NOW)


@pytest.mark.asyncio
async def test_category_browsing_does_not_start_expense_entry_and_reuses_menu():
    bot, ui, state = BotDouble(), ChatUI(), make_state()
    budget, reporting = services()
    category = SimpleNamespace(id=1, name="Кафе та ресторани", emoji="☕")
    budget.categories.return_value = [category]
    budget.category.return_value = category
    reporting.category_report = AsyncMock(return_value=sample_report())
    menu_id = await ui.show(bot, CHAT_ID, MAIN_TEXT, main_keyboard())

    await general.categories_cb(callback(bot, menu_id, "menu:categories"), budget, state, ui)
    assert "viewcat:1" in callbacks(bot.messages[menu_id].reply_markup)
    assert "cat:1" not in callbacks(bot.messages[menu_id].reply_markup)
    await categories.choose_category(callback(bot, menu_id, "viewcat:1"), budget, state, ui)
    assert {"catreport:1:today:0", "catreport:1:week:0", "catreport:1:month:0"} <= callbacks(
        bot.messages[menu_id].reply_markup,
    )
    for period in ("today", "week", "month"):
        reporting.category_report.return_value = sample_report(period)
        await categories.show_category_report(
            callback(bot, menu_id, f"catreport:1:{period}:0"), reporting, state, ui,
        )
        reporting.category_report.assert_awaited_with(CHAT_ID, 1, period, page=0)
        assert "Кава &amp; десерт &lt;3" in bot.messages[menu_id].text
        assert "Bohdan &lt;B&gt;" in bot.messages[menu_id].text
        assert "130,00 zł" in bot.messages[menu_id].text
        assert await state.get_state() is None
    budget.add_expense.assert_not_awaited()
    assert bot.send_message.await_count == 1

    await general.categories_cmd(input_message(bot, "/categories"), budget, state, ui)
    assert "viewcat:1" in callbacks(bot.messages[menu_id].reply_markup)
    await expenses.add_button(callback(bot, menu_id, "menu:add"), budget, state, ui)
    assert "cat:1" in callbacks(bot.messages[menu_id].reply_markup)
    assert "viewcat:1" not in callbacks(bot.messages[menu_id].reply_markup)
    await expenses.choose_category(callback(bot, menu_id, "cat:1"), budget, state, ui)
    assert await state.get_state() == ExpenseState.waiting_for_amount.state
    assert bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_category_pages_and_empty_reports_keep_navigation():
    bot, ui, state = BotDouble(), ChatUI(), make_state()
    reporting = SimpleNamespace(category_report=AsyncMock(return_value=sample_report(page=1, pages=3)))
    menu_id = await ui.show(bot, CHAT_ID, MAIN_TEXT, main_keyboard())
    await categories.show_category_report(
        callback(bot, menu_id, "catreport:1:month:1"), reporting, state, ui,
    )
    assert "Сторінка 2 з 3" in bot.messages[menu_id].text
    keys = callbacks(bot.messages[menu_id].reply_markup)
    assert {"catreport:1:month:0", "catreport:1:month:2", "menu:categories", "menu:main"} <= keys
    empty = replace(sample_report(), total_grosz=0, count=0, items=[])
    reporting.category_report.return_value = empty
    await categories.show_category_report(
        callback(bot, menu_id, "catreport:1:month:0"), reporting, state, ui,
    )
    assert "Витрат у цій категорії" in bot.messages[menu_id].text
    assert "catreport:1:today:0" in callbacks(bot.messages[menu_id].reply_markup)
    assert bot.send_message.await_count == 1


def test_category_pages_fit_with_maximum_length_unicode_comments_and_names():
    report = sample_report()
    item = replace(report.items[0], id=2**63 - 1, author="👩" * 120, note="💄" * 140)
    report = replace(report, items=[item] * CATEGORY_PAGE_SIZE)
    text = categories.category_report_text(report, "month")
    visible = unescape(re.sub(r"<[^>]+>", "", text))
    assert len(visible.encode("utf-16-le")) // 2 < 4096


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [
    "viewcat:0", "viewcat:-1", "viewcat:abc", "viewcat:999999999999999999999",
    "catreport:1:year:0", "catreport:1:month:-1", "catreport:0:today:0",
    "catreport:999999999999999999999:today:0",
])
async def test_invalid_category_callbacks_leave_an_existing_form_intact(data):
    bot, ui, state = BotDouble(), ChatUI(), make_state()
    budget, reporting = services()
    reporting.category_report = AsyncMock()
    await state.set_state(ExpenseState.waiting_for_amount)
    await state.update_data(prompt_id=1234)
    call = callback(bot, 101, data)
    if data.startswith("viewcat:"):
        await categories.choose_category(call, budget, state, ui)
    else:
        await categories.show_category_report(call, reporting, state, ui)
    assert call.answer.await_args.kwargs["show_alert"] is True
    budget.add_expense.assert_not_awaited()
    reporting.category_report.assert_not_awaited()
    assert await state.get_state() == ExpenseState.waiting_for_amount.state


def test_category_keyboard_separates_creation_and_browsing():
    category = SimpleNamespace(id=7, name="Beauty", emoji="💄")
    assert "cat:7" in callbacks(categories_keyboard([category]))
    assert "viewcat:7" in callbacks(categories_keyboard([category], browsing=True))
    assert {"catreport:7:today:0", "catreport:7:week:0", "catreport:7:month:0"} <= callbacks(
        category_periods_keyboard(7),
    )
