import sqlite3
from sqlalchemy import create_engine, inspect
from app.db.models import Base


def test_schema_sqlite_and_foreign_keys(tmp_path):
    file = tmp_path / "db.sqlite3"
    engine = create_engine(f"sqlite:///{file}")
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"users", "families", "family_members", "categories", "expenses"} <= tables
    with sqlite3.connect(file) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("INSERT INTO expenses (family_id, user_id, category_id, amount_grosz, occurred_at, created_at, request_id) VALUES (5,5,5,12,'2026','2026','test')")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Foreign keys must be enforced")
    engine.dispose()
