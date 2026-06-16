import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))


def read_env_value(key: str) -> str | None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return None
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def get_db_path() -> Path:
    url = os.environ.get("DATABASE_URL") or read_env_value("DATABASE_URL") or "sqlite+aiosqlite:///./prospel.db"
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            path = Path(url[len(prefix):])
            return path.resolve() if path.is_absolute() else (ROOT_DIR / path).resolve()
    return (ROOT_DIR / "prospel.db").resolve()


def table_columns(cursor: sqlite3.Cursor, table: str) -> set[str]:
    cursor.execute(f"PRAGMA table_info('{table}')")
    return {str(row[1]).lower() for row in cursor.fetchall()}


def run_migration(conn: sqlite3.Connection) -> bool:
    cursor = conn.cursor()
    columns = table_columns(cursor, "planned_expense_payments")
    if not columns:
        print("[v20] Table planned_expense_payments does not exist, nothing to do.")
        return False
    if "expense_id" not in columns:
        print("[v20] Column planned_expense_payments.expense_id is already absent.")
        return False

    required = {"id", "planned_expense_id", "due_date", "paid_date", "note", "created_at"}
    missing = sorted(required - columns)
    if missing:
        raise RuntimeError(f"planned_expense_payments is missing required columns: {missing}")

    cursor.execute("DROP TABLE IF EXISTS planned_expense_payments_v20_old")
    cursor.execute("ALTER TABLE planned_expense_payments RENAME TO planned_expense_payments_v20_old")
    cursor.execute(
        """
        CREATE TABLE planned_expense_payments (
            id INTEGER PRIMARY KEY,
            planned_expense_id INTEGER NOT NULL,
            due_date DATE NOT NULL,
            paid_date DATE NOT NULL,
            note VARCHAR(200),
            created_at DATETIME,
            FOREIGN KEY(planned_expense_id) REFERENCES planned_expenses(id)
        )
        """
    )
    cursor.execute(
        """
        INSERT INTO planned_expense_payments (
            id, planned_expense_id, due_date, paid_date, note, created_at
        )
        SELECT id, planned_expense_id, due_date, paid_date, note, created_at
        FROM planned_expense_payments_v20_old
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_planned_expense_payments_id ON planned_expense_payments(id)")
    cursor.execute("DROP TABLE planned_expense_payments_v20_old")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Migration v20: drop planned_expense_payments.expense_id.")
    parser.add_argument("--dry-run", action="store_true", help="Run migration in a transaction and roll it back.")
    args = parser.parse_args()

    db_path = get_db_path()
    print(f"[v20] Using DB: {db_path}")
    if args.dry_run:
        print("[v20] Dry-run mode: changes will be rolled back.")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        changed = run_migration(conn)
        if args.dry_run:
            conn.rollback()
            print("[v20] Dry-run completed, no changes committed.")
            return
        conn.commit()
        if changed:
            print("[v20] Migration completed successfully.")
        else:
            print("[v20] No database changes were needed.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
