"""SQLite migration runner: uses DATABASE_PATH for both local and Docker runs."""
from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path
from alembic import context
from sqlalchemy import create_engine, pool
from app.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
path = Path(os.environ.get("DATABASE_PATH", "data/budget.sqlite3")).expanduser().resolve()
path.parent.mkdir(parents=True, exist_ok=True)
config.set_main_option("sqlalchemy.url", f"sqlite:///{path}")


def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"),
                      target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(config.get_main_option("sqlalchemy.url"),
                           poolclass=pool.NullPool)
    # Explicit outer transaction ensures Alembic version row is committed on SQLite.
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
