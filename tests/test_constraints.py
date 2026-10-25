"""Database-level invariants independent of Telegram and async transport."""
import uuid
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.models import Base, Family, User, FamilyMember, Category, Expense


def test_duplicate_request_and_soft_delete(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'budget.sqlite3'}")
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(conn)
    t = "2026-10-25T11:00:00.000000+00:00"
    with Session(engine) as db:
        db.add_all([
            Family(id=1, chat_id=-100123, name="Сім'я", timezone="Europe/Warsaw", currency="PLN", created_at=t),
            User(id=1, telegram_id=11, display_name="Перший", role="admin", is_active=True, created_at=t),
            User(id=2, telegram_id=22, display_name="Друга", role="member", is_active=True, created_at=t),
        ])
        db.flush()
        db.add_all([
            FamilyMember(family_id=1, user_id=1, joined_at=t),
            FamilyMember(family_id=1, user_id=2, joined_at=t),
            Category(id=1, family_id=1, name="Продукти", emoji="🛒", sort_order=0, is_active=True),
        ])
        db.commit()
        expense_id = uuid.uuid4().hex
        db.add(Expense(family_id=1, user_id=1, category_id=1, amount_grosz=12550,
                       occurred_at=t, created_at=t, request_id=expense_id))
        db.commit()
        db.add(Expense(family_id=1, user_id=1, category_id=1, amount_grosz=12550,
                       occurred_at=t, created_at=t, request_id=expense_id))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        active = select(func.coalesce(func.sum(Expense.amount_grosz), 0)).where(Expense.deleted_at.is_(None))
        assert db.scalar(active) == 12550
        first = db.scalar(select(Expense).where(Expense.request_id == expense_id))
        first.deleted_at = t
        db.commit()
        assert db.scalar(active) == 0
    engine.dispose()
