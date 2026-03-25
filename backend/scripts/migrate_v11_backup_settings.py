import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from backend.config import get_settings


def get_db_path() -> Path:
    url = get_settings().database_url
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            raw = url[len(prefix):]
            path = Path(raw)
            if not path.is_absolute():
                return (ROOT_DIR / path).resolve()
            return path.resolve()
    return (ROOT_DIR / "prospel.db").resolve()


DB_PATH = get_db_path()


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(str(row[1]).lower() == column.lower() for row in cursor.fetchall())


def ensure_column(cursor: sqlite3.Cursor, table: str, column: str, ddl: str) -> None:
    if not column_exists(cursor, table, column):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        print(f"[v11] Added {table}.{column}")
    else:
        print(f"[v11] Column {table}.{column} already exists.")


def main() -> None:
    print(f"[v11] Using DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        ensure_column(cursor, "enterprise", "backup_dir", "VARCHAR(500)")
        ensure_column(cursor, "enterprise", "backup_auto_enabled", "BOOLEAN")
        ensure_column(cursor, "enterprise", "backup_auto_interval_hours", "INTEGER")
        ensure_column(cursor, "enterprise", "backup_auto_retention_count", "INTEGER")
        ensure_column(cursor, "enterprise", "backup_manual_retention_count", "INTEGER")
        ensure_column(cursor, "enterprise", "backup_pre_restore_retention_count", "INTEGER")
        ensure_column(cursor, "enterprise", "backup_scheduler_check_minutes", "INTEGER")
        conn.commit()
        print("[v11] Backup settings migration complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
