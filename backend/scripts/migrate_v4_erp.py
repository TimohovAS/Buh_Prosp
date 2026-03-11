"""Миграция v4: ERP — внутренние проекты, справочник категорий, обязательный project_id.

Идемпотентна: повторный запуск безопасен.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from backend.config import get_settings

SEED_CATEGORIES = [
    ("Материалы", "Materijal", "expense", "commercial", 1),
    ("Услуги", "Usluge", "expense", "commercial", 2),
    ("Транспорт", "Transport", "expense", "admin", 3),
    ("Топливо", "Gorivo", "expense", "admin", 4),
    ("Офис", "Kancelarija", "expense", "admin", 5),
    ("Налоги", "Porezi", "expense", "tax", 6),
    ("Прочее", "Ostalo", "expense", "admin", 99),
]

SEED_INTERNAL_PROJECTS = [
    ("INT-UNASSIGNED", "Нераспределено"),
    ("INT-CASH", "Наличка / Касса"),
    ("INT-OFFICE", "Офис и АХО"),
    ("INT-TRANSPORT", "Транспорт"),
    ("INT-MARKETING", "Маркетинг"),
    ("INT-SALARY", "Зарплата / Подрядчики"),
    ("INT-TAX", "Налоги и взносы"),
]

LEGACY_CATEGORY_MAP = {
    "materials": "Материалы",
    "material": "Материалы",
    "materijal": "Материалы",
    "материалы": "Материалы",
    "services": "Услуги",
    "service": "Услуги",
    "usluge": "Услуги",
    "услуги": "Услуги",
    "transport": "Транспорт",
    "транспорт": "Транспорт",
    "fuel": "Топливо",
    "gorivo": "Топливо",
    "топливо": "Топливо",
    "бензин": "Топливо",
    "гсм": "Топливо",
    "office": "Офис",
    "rent": "Офис",
    "internet": "Офис",
    "phone": "Офис",
    "utilities": "Офис",
    "аренда": "Офис",
    "офис": "Офис",
    "tax": "Налоги",
    "taxes": "Налоги",
    "porezi": "Налоги",
    "налоги": "Налоги",
    "insurance": "Прочее",
    "other": "Прочее",
    "ostalo": "Прочее",
    "прочее": "Прочее",
    "остальное": "Прочее",
}


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


def normalize_label(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def title_case(value: str) -> str:
    value = " ".join(value.strip().split())
    if not value:
        return value
    return value[0].upper() + value[1:]


def table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cursor.fetchone() is not None


def has_column(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(str(row[1]).lower() == column.lower() for row in cursor.fetchall())


def ensure_column(cursor: sqlite3.Cursor, table: str, column: str, definition: str) -> None:
    if not table_exists(cursor, table):
        print(f"[v4] Table {table} not found, skipping column {column}.")
        return
    if has_column(cursor, table, column):
        print(f"[v4] Column {table}.{column} already exists.")
        return
    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    print(f"[v4] Added column {table}.{column}.")


def ensure_transaction_categories_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS transaction_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_ru VARCHAR(100) NOT NULL,
            name_sr VARCHAR(100) NOT NULL,
            category_type VARCHAR(20) NOT NULL DEFAULT 'expense',
            category_group VARCHAR(20) NOT NULL DEFAULT 'admin',
            is_active BOOLEAN NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    print("[v4] Ensured table transaction_categories exists.")


def fetch_categories(cursor: sqlite3.Cursor) -> list[tuple[int, str, str]]:
    cursor.execute("SELECT id, name_ru, name_sr FROM transaction_categories")
    return [(int(row[0]), str(row[1]), str(row[2])) for row in cursor.fetchall()]


def ensure_category(
    cursor: sqlite3.Cursor,
    name_ru: str,
    name_sr: str | None = None,
    category_type: str = "expense",
    category_group: str = "admin",
    sort_order: int = 0,
) -> int:
    normalized = normalize_label(name_ru)
    for category_id, existing_ru, existing_sr in fetch_categories(cursor):
        if normalize_label(existing_ru) == normalized or normalize_label(existing_sr) == normalized:
            return category_id

    safe_ru = title_case(name_ru)
    safe_sr = title_case(name_sr or name_ru)
    cursor.execute(
        """
        INSERT INTO transaction_categories
            (name_ru, name_sr, category_type, category_group, is_active, sort_order)
        VALUES (?, ?, ?, ?, 1, ?)
        """,
        (safe_ru, safe_sr, category_type, category_group, sort_order),
    )
    category_id = int(cursor.lastrowid)
    print(f"[v4] Created category '{safe_ru}' (id={category_id}).")
    return category_id


def seed_categories(cursor: sqlite3.Cursor) -> None:
    cursor.execute("SELECT COUNT(*) FROM transaction_categories")
    if int(cursor.fetchone()[0]) != 0:
        print("[v4] Categories already seeded.")
        return

    for name_ru, name_sr, category_type, category_group, sort_order in SEED_CATEGORIES:
        cursor.execute(
            """
            INSERT INTO transaction_categories
                (name_ru, name_sr, category_type, category_group, is_active, sort_order)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (name_ru, name_sr, category_type, category_group, sort_order),
        )
    print(f"[v4] Seeded {len(SEED_CATEGORIES)} default categories.")


def seed_internal_projects(cursor: sqlite3.Cursor) -> None:
    if not table_exists(cursor, "projects"):
        print("[v4] Projects table not found, skipping internal projects seed.")
        return

    for code, name in SEED_INTERNAL_PROJECTS:
        cursor.execute("SELECT id FROM projects WHERE code = ?", (code,))
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE projects SET name = ?, is_internal = 1 WHERE code = ?",
                (name, code),
            )
            print(f"[v4] Internal project '{code}' already exists (id={row[0]}).")
            continue

        cursor.execute(
            """
            INSERT INTO projects (code, name, is_internal, status, created_at, updated_at)
            VALUES (?, ?, 1, 'active', datetime('now'), datetime('now'))
            """,
            (code, name),
        )
        print(f"[v4] Created internal project '{code}'.")


def migrate_legacy_categories(cursor: sqlite3.Cursor) -> None:
    fallback_id = ensure_category(cursor, "Прочее", "Ostalo", "expense", "admin", 99)

    for table in ("expenses", "planned_expenses"):
        if not table_exists(cursor, table) or not has_column(cursor, table, "category_id"):
            continue

        cursor.execute(
            f"SELECT id, category FROM {table} WHERE category_id IS NULL AND category IS NOT NULL AND TRIM(category) <> ''"
        )
        rows = cursor.fetchall()
        for row_id, legacy_value in rows:
            normalized = normalize_label(legacy_value)
            mapped_name = LEGACY_CATEGORY_MAP.get(normalized)
            if mapped_name:
                category_id = ensure_category(cursor, mapped_name, mapped_name, "expense", "admin", 100)
            else:
                cleaned_name = title_case(str(legacy_value))
                category_id = ensure_category(cursor, cleaned_name, cleaned_name, "expense", "admin", 1000)

            cursor.execute(
                f"UPDATE {table} SET category_id = ? WHERE id = ?",
                (category_id or fallback_id, row_id),
            )

        cursor.execute(
            f"UPDATE {table} SET category_id = ? WHERE category_id IS NULL",
            (fallback_id,),
        )
        print(f"[v4] Legacy categories migrated for {table}.")


def assign_default_project(cursor: sqlite3.Cursor) -> None:
    cursor.execute("SELECT id FROM projects WHERE code = 'INT-UNASSIGNED'")
    row = cursor.fetchone()
    if not row:
        print("[v4][WARN] Project INT-UNASSIGNED not found, skipping default assignment.")
        return

    unassigned_id = int(row[0])
    for table in ("income", "expenses", "bank_transactions", "planned_expenses"):
        if not table_exists(cursor, table) or not has_column(cursor, table, "project_id"):
            continue
        cursor.execute(
            f"UPDATE {table} SET project_id = ? WHERE project_id IS NULL",
            (unassigned_id,),
        )
        print(f"[v4] {table}: assigned {cursor.rowcount} rows to INT-UNASSIGNED.")


def run() -> None:
    if not DB_PATH.exists():
        print(f"[v4] DB not found at {DB_PATH}, skipping.")
        return

    print(f"[v4] Using DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()

        ensure_transaction_categories_table(cursor)
        ensure_column(cursor, "projects", "is_internal", "BOOLEAN NOT NULL DEFAULT 0")
        ensure_column(cursor, "expenses", "category_id", "INTEGER REFERENCES transaction_categories(id)")
        ensure_column(cursor, "planned_expenses", "category_id", "INTEGER REFERENCES transaction_categories(id)")
        ensure_column(cursor, "planned_expenses", "project_id", "INTEGER REFERENCES projects(id)")
        conn.commit()

        seed_categories(cursor)
        seed_internal_projects(cursor)
        migrate_legacy_categories(cursor)
        assign_default_project(cursor)
        conn.commit()
        print("[v4] Migration v4 complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
