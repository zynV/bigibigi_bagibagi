from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.db.models import Expense, Category, Family, User
from app.services.dates import period_bounds, month_bounds


@dataclass(frozen=True)
class Report:
    total_grosz: int
    count: int
    categories: list[tuple[str, int]]
    authors: list[tuple[str, int]]


@dataclass(frozen=True)
class HistoryItem:
    id: int
    occurred_at: str
    category: str
    amount_grosz: int
    author: str
    author_tg_id: int
    note: str | None


CATEGORY_PAGE_SIZE = 5


@dataclass(frozen=True)
class CategoryReport:
    category: str
    total_grosz: int
    count: int
    items: list[HistoryItem]
    page: int
    pages: int
    start: str
    end: str


class ReportService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def _family_id(self, session: AsyncSession, chat_id: int) -> int:
        id_ = await session.scalar(select(Family.id).where(Family.chat_id == chat_id))
        if id_ is None:
            raise PermissionError("Unknown family")
        return id_

    async def summary(self, chat_id: int, period: str, now: datetime | None = None) -> Report:
        start, end = period_bounds(period, now)
        return await self._summary(chat_id, start, end)

    async def monthly_summary(self, chat_id: int, year: int, month: int) -> Report:
        start, end = month_bounds(year, month)
        return await self._summary(chat_id, start, end)

    async def _summary(self, chat_id: int, start: str, end: str) -> Report:
        async with self.sessions() as session:
            family_id = await self._family_id(session, chat_id)
            filt = (Expense.family_id == family_id, Expense.deleted_at.is_(None),
                    Expense.occurred_at >= start, Expense.occurred_at < end)
            total, count = (await session.execute(select(
                func.coalesce(func.sum(Expense.amount_grosz), 0), func.count(Expense.id)
            ).where(*filt))).one()
            by_cat = (await session.execute(select(
                Category.emoji, Category.name, func.sum(Expense.amount_grosz).label("sum_grosz")
            ).join(Expense, Expense.category_id == Category.id)
                .where(*filt).group_by(Category.id)
                .order_by(func.sum(Expense.amount_grosz).desc(), Category.sort_order))).all()
            by_user = (await session.execute(select(
                User.display_name, func.sum(Expense.amount_grosz).label("sum_grosz")
            ).join(Expense, Expense.user_id == User.id)
                .where(*filt).group_by(User.id)
                .order_by(func.sum(Expense.amount_grosz).desc()))).all()
            return Report(int(total), int(count),
                          [(f"{emoji} {name}", int(amount)) for emoji, name, amount in by_cat],
                          [(name, int(amount)) for name, amount in by_user])

    async def category_report(
        self, chat_id: int, category_id: int, period: str, *, page: int = 0,
        now: datetime | None = None,
    ) -> CategoryReport:
        if page < 0:
            raise ValueError("Page must be non-negative")
        start, end = period_bounds(period, now)
        async with self.sessions() as session:
            family_id = await self._family_id(session, chat_id)
            category = await session.scalar(select(Category).where(
                Category.id == category_id, Category.family_id == family_id,
                Category.is_active.is_(True),
            ))
            if category is None:
                raise ValueError("Category not found or inactive")
            title = f"{category.emoji} {category.name}"
            filt = (
                Expense.family_id == family_id, Expense.category_id == category_id,
                Expense.deleted_at.is_(None), Expense.occurred_at >= start,
                Expense.occurred_at < end,
            )
            total, count = (await session.execute(select(
                func.coalesce(func.sum(Expense.amount_grosz), 0), func.count(Expense.id),
            ).where(*filt))).one()
            pages = max(1, (int(count) + CATEGORY_PAGE_SIZE - 1) // CATEGORY_PAGE_SIZE)
            page = min(page, pages - 1)
            rows = (await session.execute(
                select(Expense, User.display_name, User.telegram_id)
                .join(User, User.id == Expense.user_id).where(*filt)
                .order_by(Expense.occurred_at.desc(), Expense.id.desc())
                .offset(page * CATEGORY_PAGE_SIZE).limit(CATEGORY_PAGE_SIZE)
            )).all()
            items = [
                HistoryItem(e.id, e.occurred_at, title, e.amount_grosz, author, tg_id, e.note)
                for e, author, tg_id in rows
            ]
            return CategoryReport(title, int(total), int(count), items, page, pages, start, end)

    async def history(self, chat_id: int, limit: int = 10) -> list[HistoryItem]:
        async with self.sessions() as session:
            family_id = await self._family_id(session, chat_id)
            rows = (await session.execute(
                select(Expense, Category.emoji, Category.name, User.display_name, User.telegram_id)
                .join(Category, Category.id == Expense.category_id)
                .join(User, User.id == Expense.user_id)
                .where(Expense.family_id == family_id, Expense.deleted_at.is_(None))
                .order_by(Expense.occurred_at.desc(), Expense.id.desc()).limit(min(limit, 100))
            )).all()
            return [HistoryItem(e.id, e.occurred_at, f"{emoji} {name}", e.amount_grosz,
                                author, tg_id, e.note)
                    for e, emoji, name, author, tg_id in rows]

    async def export(self, chat_id: int) -> list[HistoryItem]:
        # No upper bound here: exports are an explicit admin-only operation.
        async with self.sessions() as session:
            family_id = await self._family_id(session, chat_id)
            rows = (await session.execute(
                select(Expense, Category.emoji, Category.name, User.display_name, User.telegram_id)
                .join(Category, Category.id == Expense.category_id)
                .join(User, User.id == Expense.user_id)
                .where(Expense.family_id == family_id, Expense.deleted_at.is_(None))
                .order_by(Expense.occurred_at, Expense.id)
            )).all()
            return [HistoryItem(e.id, e.occurred_at, f"{emoji} {name}", e.amount_grosz,
                                author, tg_id, e.note)
                    for e, emoji, name, author, tg_id in rows]
