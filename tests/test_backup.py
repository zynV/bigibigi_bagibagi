import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from app.services.backup import BackupManager


def test_online_backup_retention_and_restore(tmp_path):
    db = tmp_path / "data.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE sample (x INTEGER)")
        conn.execute("INSERT INTO sample VALUES (42)")
    manager = BackupManager(db, tmp_path / "backups", keep=14)
    local = ZoneInfo("Europe/Warsaw")
    first = manager.backup_if_due(datetime(2026, 10, 24, 12, tzinfo=local))
    assert first is not None and first.exists()
    assert manager.backup_if_due(datetime(2026, 10, 24, 18, tzinfo=local)) is None
    for day in range(25, 31):
        manager.backup_if_due(datetime(2026, 10, day, 12, tzinfo=local))
    for day in range(1, 11):
        manager.backup_if_due(datetime(2026, 11, day, 12, tzinfo=local))
    assert len(list((tmp_path / "backups").glob("budget-*.sqlite3"))) == 14
    latest = tmp_path / "backups/budget-2026-11-10.sqlite3"
    with sqlite3.connect(latest) as conn:
        assert conn.execute("SELECT x FROM sample").fetchone()[0] == 42
