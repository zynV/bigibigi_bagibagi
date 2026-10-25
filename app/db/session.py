from __future__ import annotations

from pathlib import Path
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def create_session_factory(database_path: Path):
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        connect_args={"timeout": 30},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def pragmas(dbapi_connection, connection_record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
