from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.config import Settings
from app.db.models import Family, FamilyMember, User, Category

DEFAULT_CATEGORIES = (
    ("Продукти", "🛒"), ("Транспорт", "🚗"), ("Житло", "🏠"),
    ("Здоров’я", "💊"), ("Beauty", "💄"), ("Кафе та ресторани", "☕"), ("Одяг", "👕"),
    ("Розваги", "🎮"), ("Подорожі", "✈️"), ("Подарунки", "🎁"),
    ("Покупки", "🛍️"), ("Підписки", "📱"), ("Інше", "📦"),
)
RETIRED_CATEGORIES = frozenset({"Діти"})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


async def seed_database(factory: async_sessionmaker[AsyncSession], cfg: Settings) -> None:
    async with factory.begin() as session:
        family = await session.scalar(select(Family).where(Family.chat_id == cfg.group_chat_id))
        if family is None:
            family = Family(chat_id=cfg.group_chat_id, name=cfg.family_name,
                            timezone="Europe/Warsaw", currency="PLN", created_at=utc_now())
            session.add(family)
            await session.flush()
        for telegram_id in sorted(cfg.allowed_user_ids):
            user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
            if user is None:
                user = User(telegram_id=telegram_id, display_name=f"Учасник {telegram_id}",
                            role="admin" if telegram_id == cfg.admin_user_id else "member",
                            is_active=True, created_at=utc_now())
                session.add(user)
                await session.flush()
            else:
                user.role = "admin" if telegram_id == cfg.admin_user_id else "member"
                user.is_active = True
            membership = await session.get(FamilyMember, (family.id, user.id))
            if membership is None:
                session.add(FamilyMember(family_id=family.id, user_id=user.id, joined_at=utc_now()))
        existing = {c.name: c for c in (await session.scalars(
            select(Category).where(Category.family_id == family.id))).all()}
        # Preserve category IDs and all expenses already referencing retired categories.
        for name in RETIRED_CATEGORIES:
            if name in existing:
                existing[name].is_active = False
        for order, (name, emoji) in enumerate(DEFAULT_CATEGORIES):
            category = existing.get(name)
            if category is None:
                session.add(Category(family_id=family.id, name=name, emoji=emoji,
                                     sort_order=order, is_active=True))
            else:
                category.emoji = emoji
                category.sort_order = order
                category.is_active = True
