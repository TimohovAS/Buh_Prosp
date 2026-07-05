"""Migration v6: add maticni_broj to clients."""

from __future__ import annotations

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
            raw = url[len(prefix) :]
            path = Path(raw)
            if not path.is_absolute():
                return (ROOT_DIR / path).resolve()
            return path.resolve()
    return (ROOT_DIR / "prospel.db").resolve()


DB_PATH = get_db_path()


def table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cursor.fetchone() is not None


def has_column(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(str(row[1]).lower() == column.lower() for row in cursor.fetchall())


def ensure_column(cursor: sqlite3.Cursor, table: str, column: str, definition: str) -> None:
    if not table_exists(cursor, table):
        print(f"[v6] Table {table} not found, skipping {column}.")
        return
    if has_column(cursor, table, column):
        print(f"[v6] Column {table}.{column} already exists.")
        return
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    print(f"[v6] Added column {table}.{column}.")


def main() -> None:
    print(f"[v6] Using DB: {DB_PATH}")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        ensure_column(cursor, "clients", "maticni_broj", "VARCHAR(20)")
        conn.commit()
        print("[v6] Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
