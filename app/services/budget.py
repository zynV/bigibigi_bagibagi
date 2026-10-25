"""Authenticated expense operations. Family boundaries are checked in SQL."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.db.models import Category, Expense, Family, FamilyMember, User
from app.db.seed import utc_now
from app.services.money import MAX_GROSZY
from app.services.dates import iso_utc


@dataclass(frozen=True)
class Receipt:
    expense_id: int
    category: str
    amount_grosz: int
    note: str | None


class BudgetService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def family(self, session: AsyncSession, chat_id: int) -> Family:
        family = await session.scalar(select(Family).where(Family.chat_id == chat_id))
        if not family:
            raise PermissionError("Unknown family")
        return family

    async def member(self, session: AsyncSession, family_id: int, tg_id: int) -> User:
        user = await session.scalar(
            select(User).join(FamilyMember, FamilyMember.user_id == User.id)
            .where(FamilyMember.family_id == family_id, User.telegram_id == tg_id, User.is_active.is_(True))
        )
        if not user:
            raise PermissionError("Not a member")
        return user

    async def categories(self, chat_id: int) -> list[Category]:
        async with self.sessions() as session:
            family = await self.family(session, chat_id)
            return list((await session.scalars(
                select(Category).where(Category.family_id == family.id, Category.is_active.is_(True))
                .order_by(Category.sort_order, Category.id)
            )).all())

    async def category(self, chat_id: int, category_id: int) -> Category | None:
        async with self.sessions() as session:
            family = await self.family(session, chat_id)
            return await session.scalar(select(Category).where(
                Category.id == category_id, Category.family_id == family.id,
                Category.is_active.is_(True)))

    async def add_expense(
        self, chat_id: int, telegram_id: int, category_id: int,
        amount_grosz: int, note: str | None, request_id: str,
        display_name: str | None = None, when: datetime | None = None,
    ) -> tuple[Receipt, bool]:
        if not isinstance(amount_grosz, int) or not 0 < amount_grosz <= MAX_GROSZY:
            raise ValueError("Invalid amount")
        if note is not None and (len(note) > 140 or not note.strip()):
            raise ValueError("Invalid note")
        if len(request_id) != 32 or not all(c in "0123456789abcdef" for c in request_id):
            raise ValueError("Invalid request ID")
        try:
            async with self.sessions.begin() as session:
                family = await self.family(session, chat_id)
                user = await self.member(session, family.id, telegram_id)
                category = await session.scalar(select(Category).where(
                    Category.id == category_id,
                    Category.family_id == family.id,
                    Category.is_active.is_(True)))
                if category is None:
                    raise ValueError("Category not found or inactive")
                if display_name:
                    user.display_name = display_name[:120]
                stamp = iso_utc(when or datetime.now(timezone.utc))
                expense = Expense(family_id=family.id, user_id=user.id, category_id=category_id,
                                  amount_grosz=amount_grosz, note=note,
                                  occurred_at=stamp, created_at=utc_now(), request_id=request_id)
                session.add(expense)
                await session.flush()
                result = Receipt(expense.id, f"{category.emoji} {category.name}", amount_grosz, note)
                return result, True
        except IntegrityError:
            # Unique request ID makes concurrent double-confirmations idempotent.
            async with self.sessions() as session:
                family = await self.family(session, chat_id)
                user = await self.member(session, family.id, telegram_id)
                old = (await session.execute(
                    select(Expense, Category).join(Category, Expense.category_id == Category.id)
                    .where(Expense.request_id == request_id, Expense.family_id == family.id,
                           Expense.user_id == user.id)
                )).one_or_none()
                if old is None:
                    raise  # unrelated constraint failure, do not hide it
                item, category = old
                return Receipt(item.id, f"{category.emoji} {category.name}", item.amount_grosz, item.note), False

    async def delete_expense(self, chat_id: int, telegram_id: int, expense_id: int) -> bool:
        async with self.sessions.begin() as session:
            family = await self.family(session, chat_id)
            user = await self.member(session, family.id, telegram_id)
            conditions = [Expense.id == expense_id, Expense.family_id == family.id,
                          Expense.deleted_at.is_(None)]
            if user.role != "admin":
                conditions.append(Expense.user_id == user.id)
            result = await session.execute(update(Expense).where(*conditions).values(deleted_at=utc_now()))
            return result.rowcount == 1

    async def undo_last(self, chat_id: int, telegram_id: int) -> int | None:
        async with self.sessions.begin() as session:
            family = await self.family(session, chat_id)
            user = await self.member(session, family.id, telegram_id)
            # Search and update in one transaction; conditional UPDATE handles races.
            recent_id = await session.scalar(select(Expense.id).where(
                Expense.family_id == family.id, Expense.user_id == user.id,
                Expense.deleted_at.is_(None)).order_by(Expense.created_at.desc(), Expense.id.desc()).limit(1))
            if recent_id is None:
                return None
            result = await session.execute(update(Expense).where(
                Expense.id == recent_id, Expense.deleted_at.is_(None)
            ).values(deleted_at=utc_now()))
            return recent_id if result.rowcount == 1 else None
