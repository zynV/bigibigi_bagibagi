"""SQLite online backup via Backup API, retained for at least 14 days."""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
WARSAW = ZoneInfo("Europe/Warsaw")


class BackupManager:
    def __init__(self, db_path: Path, directory: Path, keep: int = 14):
        self.db_path = db_path
        self.directory = directory
        self.keep = max(14, keep)

    def backup_if_due(self, now: datetime | None = None) -> Path | None:
        local = (now or datetime.now(timezone.utc)).astimezone(WARSAW)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        dest = self.directory / f"budget-{local:%Y-%m-%d}.sqlite3"
        if dest.exists():
            return None
        if not self.db_path.is_file():
            raise FileNotFoundError(self.db_path)
        tmp = dest.with_suffix(".sqlite3.tmp")
        try:
            with closing(sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=30)) as source:
                with closing(sqlite3.connect(tmp, timeout=30)) as target:
                    source.backup(target)
            os.chmod(tmp, 0o600)
            os.replace(tmp, dest)
            # Keep the latest N complete snapshots (may span more than N days).
            older = sorted(self.directory.glob("budget-????-??-??.sqlite3"), reverse=True)
            for obsolete in older[self.keep:]:
                obsolete.unlink()
            logger.info("SQLite backup completed: %s", dest.name)
            return dest
        finally:
            tmp.unlink(missing_ok=True)


async def backup_loop(manager: BackupManager) -> None:
    """Back up at startup if needed, then hourly; restart fills missed days."""
    while True:
        try:
            await asyncio.to_thread(manager.backup_if_due)
        except Exception:
            logger.exception("SQLite backup failed; retrying on next check")
        await asyncio.sleep(3600)
