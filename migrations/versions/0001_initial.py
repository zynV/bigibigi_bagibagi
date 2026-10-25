"""Initial schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("telegram_id"))
    op.create_table("families",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("chat_id"))
    op.create_table("family_members",
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("joined_at", sa.String(40), nullable=False))
    op.create_table("categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("emoji", sa.String(16), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("family_id", "name", name="uq_category_family_name"))
    op.create_table("expenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("amount_grosz", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.String(40), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("deleted_at", sa.String(40), nullable=True),
        sa.CheckConstraint("amount_grosz > 0 AND amount_grosz <= 100000000", name="ck_valid_amount"),
        sa.UniqueConstraint("request_id"))
    op.create_index("ix_expenses_family_occurred", "expenses", ["family_id", "occurred_at"])
    op.create_index("ix_expenses_family_category", "expenses", ["family_id", "category_id"])
    op.create_index("ix_expenses_user_occurred", "expenses", ["user_id", "occurred_at"])


def downgrade():
    op.drop_table("expenses")
    op.drop_table("categories")
    op.drop_table("family_members")
    op.drop_table("families")
    op.drop_table("users")
