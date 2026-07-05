"""Migration v9: add default_project_id to transaction_categories."""

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


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(str(row[1]).lower() == column.lower() for row in cursor.fetchall())


def main() -> None:
    print(f"[v9] Using DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()

        if not column_exists(cursor, "transaction_categories", "default_project_id"):
            cursor.execute("ALTER TABLE transaction_categories ADD COLUMN default_project_id INTEGER")
            print("[v9] Added transaction_categories.default_project_id")
        else:
            print("[v9] Column transaction_categories.default_project_id already exists.")

        cursor.execute("SELECT id FROM projects WHERE code = ?", ("INT-TAX",))
        tax_project = cursor.fetchone()
        if tax_project:
            cursor.execute(
                """
                UPDATE transaction_categories
                SET default_project_id = ?
                WHERE category_group = 'tax' AND default_project_id IS NULL
                """,
                (int(tax_project[0]),),
            )
            print("[v9] Backfilled tax categories with INT-TAX default project.")
        else:
            print("[v9] INT-TAX project not found, skipping tax-category backfill.")

        conn.commit()
        print("[v9] Migration completed successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
