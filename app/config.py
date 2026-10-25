"""Validate process configuration before contacting Telegram or the database."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    group_chat_id: int
    allowed_user_ids: frozenset[int]
    admin_user_id: int
    family_name: str
    database_path: Path
    backup_dir: Path
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        token = os.environ.get("BOT_TOKEN", "").strip()
        if not token or token.endswith("REPLACE_WITH_REAL_TOKEN") or ":" not in token:
            raise ValueError("Set a real BOT_TOKEN in .env")
        try:
            group_id = int(os.environ["GROUP_CHAT_ID"])
            members = [int(x.strip()) for x in os.environ["ALLOWED_USER_IDS"].split(",")]
            admin_id = int(os.environ["ADMIN_USER_ID"])
        except (KeyError, ValueError) as exc:
            raise ValueError("Set GROUP_CHAT_ID, ALLOWED_USER_IDS and ADMIN_USER_ID") from exc
        if group_id >= 0:
            raise ValueError("GROUP_CHAT_ID must be a negative Telegram group ID")
        if len(members) != 2 or len(set(members)) != 2 or any(x <= 0 for x in members):
            raise ValueError("ALLOWED_USER_IDS must contain exactly two distinct positive IDs")
        if admin_id not in members:
            raise ValueError("ADMIN_USER_ID must be listed in ALLOWED_USER_IDS")
        database_path = Path(os.environ.get("DATABASE_PATH", "data/budget.sqlite3")).expanduser().resolve()
        backup_dir = Path(os.environ.get("BACKUP_DIR", "backups")).expanduser().resolve()
        return cls(
            bot_token=token, group_chat_id=group_id,
            allowed_user_ids=frozenset(members), admin_user_id=admin_id,
            family_name=os.getenv("FAMILY_NAME", "Сімейний бюджет").strip() or "Сімейний бюджет",
            database_path=database_path, backup_dir=backup_dir,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
