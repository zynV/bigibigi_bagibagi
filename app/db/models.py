"""Schema aligned with the family-budget specification, with UTC ISO8601 strings."""
from __future__ import annotations

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # admin or member
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class Family(Base):
    __tablename__ = "families"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Europe/Warsaw")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PLN")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class FamilyMember(Base):
    __tablename__ = "family_members"
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    joined_at: Mapped[str] = mapped_column(String(40), nullable=False)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("family_id", "name", name="uq_category_family_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    emoji: Mapped[str] = mapped_column(String(16), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount_grosz > 0 AND amount_grosz <= 100000000", name="ck_valid_amount"),
        Index("ix_expenses_family_occurred", "family_id", "occurred_at"),
        Index("ix_expenses_family_category", "family_id", "category_id"),
        Index("ix_expenses_user_occurred", "user_id", "occurred_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    amount_grosz: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    deleted_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
