"""Миграция v4: ERP — внутренние проекты, справочник категорий, обязательный project_id.

Идемпотентна: повторный запуск безопасен.
"""
import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "prospel.db")
DB_PATH = os.path.abspath(DB_PATH)

SEED_CATEGORIES = [
    # (name_ru, name_sr, category_type, category_group, sort_order)
    ("Материалы", "Materijal", "expense", "commercial", 1),
    ("Услуги", "Usluge", "expense", "commercial", 2),
    ("Транспорт", "Transport", "expense", "admin", 3),
    ("Топливо", "Gorivo", "expense", "admin", 4),
    ("Офис", "Kancelarija", "expense", "admin", 5),
    ("Налоги", "Porezi", "expense", "tax", 6),
    ("Прочее", "Ostalo", "expense", "admin", 99),
]

SEED_INTERNAL_PROJECTS = [
    # (code, name, is_internal)
    ("INT-UNASSIGNED", "Нераспределено", 1),
    ("INT-OFFICE", "Офис и АХО", 1),
    ("INT-TRANSPORT", "Транспорт", 1),
    ("INT-MARKETING", "Маркетинг", 1),
    ("INT-SALARY", "Зарплата / Подрядчики", 1),
    ("INT-TAX", "Налоги и взносы", 1),
]

# Маппинг строковых категорий (legacy) → name_ru в справочнике
LEGACY_CATEGORY_MAP = {
    "materials": "Материалы",
    "material": "Материалы",
    "materijal": "Материалы",
    "материалы": "Материалы",
    "services": "Услуги",
    "услуги": "Услуги",
    "usluge": "Услуги",
    "rent": "Офис",
    "аренда": "Офис",
    "zakup": "Офис",
    "transport": "Транспорт",
    "транспорт": "Транспорт",
    "fuel": "Топливо",
    "gorivo": "Топливо",
    "топливо": "Топливо",
    "бензин": "Топливо",
    "гсм": "Топливо",
    "tax": "Налоги",
    "taxes": "Налоги",
    "porezi": "Налоги",
    "налоги": "Налоги",
    "internet": "Офис",
    "phone": "Офис",
    "utilities": "Офис",
    "insurance": "Прочее",
    "office": "Офис",
    "other": "Прочее",
    "остальное": "Прочее",
    "ostalo": "Прочее",
    "прочее": "Прочее",
}


def has_column(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def table_exists(cursor, table):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cursor.fetchone() is not None


def run():
    if not os.path.exists(DB_PATH):
        print(f"[v4] DB not found at {DB_PATH}, skipping (will be created by app).")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ── 1. CREATE TABLE transaction_categories ──
    if not table_exists(cursor, "transaction_categories"):
        print("[v4] Creating table transaction_categories...")
        cursor.execute("""
            CREATE TABLE transaction_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_ru VARCHAR(100) NOT NULL,
                name_sr VARCHAR(100) NOT NULL,
                category_type VARCHAR(20) DEFAULT 'expense',
                category_group VARCHAR(20) DEFAULT 'admin',
                is_active BOOLEAN DEFAULT 1,
                sort_order INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        print("[v4] Table transaction_categories created.")
    else:
        print("[v4] Table transaction_categories already exists.")

    # ── 2. ADD COLUMNS ──
    alter_pairs = [
        ("projects", "is_internal", "BOOLEAN DEFAULT 0"),
        ("expenses", "category_id", "INTEGER REFERENCES transaction_categories(id)"),
        ("planned_expenses", "category_id", "INTEGER REFERENCES transaction_categories(id)"),
        ("planned_expenses", "project_id", "INTEGER REFERENCES projects(id)"),
    ]
    for tbl, col, typedef in alter_pairs:
        if not table_exists(cursor, tbl):
            print(f"[v4] Table {tbl} not found, skipping column {col}.")
            continue
        if has_column(cursor, tbl, col):
            print(f"[v4] Column {tbl}.{col} already exists.")
        else:
            try:
                cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {typedef}")
                conn.commit()
                print(f"[v4] Added column {tbl}.{col}.")
            except Exception as e:
                print(f"[v4][WARN] Could not add {tbl}.{col}: {e}")

    # ── 3. SEED CATEGORIES ──
    cursor.execute("SELECT COUNT(*) FROM transaction_categories")
    cat_count = cursor.fetchone()[0]
    if cat_count == 0:
        print("[v4] Seeding default categories...")
        for name_ru, name_sr, ctype, cgroup, sort in SEED_CATEGORIES:
            cursor.execute(
                "INSERT INTO transaction_categories (name_ru, name_sr, category_type, category_group, is_active, sort_order) VALUES (?,?,?,?,1,?)",
                (name_ru, name_sr, ctype, cgroup, sort),
            )
        conn.commit()
        print(f"[v4] Seeded {len(SEED_CATEGORIES)} categories.")
    else:
        print(f"[v4] Categories already seeded ({cat_count} rows).")

    # ── 4. SEED INTERNAL PROJECTS ──
    for code, name, is_int in SEED_INTERNAL_PROJECTS:
        cursor.execute("SELECT id FROM projects WHERE code = ?", (code,))
        row = cursor.fetchone()
        if row:
            print(f"[v4] Internal project '{code}' already exists (id={row[0]}).")
            # Обновим is_internal на всякий случай
            cursor.execute("UPDATE projects SET is_internal = 1 WHERE code = ?", (code,))
        else:
            cursor.execute(
                "INSERT INTO projects (code, name, is_internal, status, created_at, updated_at) VALUES (?,?,?,?,datetime('now'),datetime('now'))",
                (code, name, is_int, "active"),
            )
            print(f"[v4] Created internal project '{code}'.")
    conn.commit()

    # ── 5. MIGRATE LEGACY CATEGORIES → category_id ──
    # Build lookup: name_ru → id
    cursor.execute("SELECT id, name_ru FROM transaction_categories")
    cat_lookup = {}
    for row in cursor.fetchall():
        cat_lookup[row[1]] = row[0]
    # "Прочее" as fallback
    fallback_id = cat_lookup.get("Прочее")

    for tbl in ("expenses", "planned_expenses"):
        if not table_exists(cursor, tbl) or not has_column(cursor, tbl, "category_id"):
            continue
        cursor.execute(f"SELECT DISTINCT category FROM {tbl} WHERE category IS NOT NULL AND category != '' AND category_id IS NULL")
        legacy_cats = [r[0] for r in cursor.fetchall()]
        for lcat in legacy_cats:
            norm = lcat.strip().lower()
            target_ru = LEGACY_CATEGORY_MAP.get(norm)
            target_id = cat_lookup.get(target_ru, fallback_id) if target_ru else fallback_id
            if target_id:
                cursor.execute(f"UPDATE {tbl} SET category_id = ? WHERE category = ? AND category_id IS NULL", (target_id, lcat))
                print(f"[v4] {tbl}: mapped '{lcat}' → category_id={target_id}")
            else:
                print(f"[v4][WARN] {tbl}: no mapping for '{lcat}', skipping.")
    conn.commit()

    # ── 6. ASSIGN INT-UNASSIGNED project ──
    cursor.execute("SELECT id FROM projects WHERE code = 'INT-UNASSIGNED'")
    unassigned_row = cursor.fetchone()
    if unassigned_row:
        uid = unassigned_row[0]
        for tbl in ("income", "expenses", "planned_expenses"):
            if not table_exists(cursor, tbl) or not has_column(cursor, tbl, "project_id"):
                continue
            cursor.execute(f"UPDATE {tbl} SET project_id = ? WHERE project_id IS NULL", (uid,))
            cnt = cursor.rowcount
            if cnt > 0:
                print(f"[v4] {tbl}: assigned {cnt} rows to INT-UNASSIGNED (id={uid}).")
            else:
                print(f"[v4] {tbl}: no NULL project_id rows.")
        # bank_transactions
        if table_exists(cursor, "bank_transactions") and has_column(cursor, "bank_transactions", "project_id"):
            cursor.execute("UPDATE bank_transactions SET project_id = ? WHERE project_id IS NULL", (uid,))
            cnt = cursor.rowcount
            print(f"[v4] bank_transactions: assigned {cnt} rows to INT-UNASSIGNED.")
        conn.commit()
    else:
        print("[v4][ERROR] INT-UNASSIGNED project not found! Cannot auto-assign.")

    conn.close()
    print("[v4] Migration v4 complete.")


if __name__ == "__main__":
    run()
