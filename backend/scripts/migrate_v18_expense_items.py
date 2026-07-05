import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))


def get_db_path() -> Path:
    url = os.environ.get("DATABASE_URL") or read_env_value("DATABASE_URL") or "sqlite+aiosqlite:///./prospel.db"
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            raw = url[len(prefix) :]
            path = Path(raw)
            if not path.is_absolute():
                return (ROOT_DIR / path).resolve()
            return path.resolve()
    return (ROOT_DIR / "prospel.db").resolve()


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


def count_pending_receipt_items(cursor: sqlite3.Cursor) -> int:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM purchase_receipts pr
        JOIN purchase_receipt_items pri ON pri.receipt_id = pr.id
        WHERE pr.expense_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM expense_items ei
              WHERE ei.expense_id = pr.expense_id
          )
        """
    )
    return int(cursor.fetchone()[0] or 0)


def run_migration(conn: sqlite3.Connection) -> int:
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS expense_items (
            id INTEGER PRIMARY KEY,
            expense_id INTEGER NOT NULL,
            line_no INTEGER NOT NULL DEFAULT 1,
            name VARCHAR(500) NOT NULL,
            quantity NUMERIC(14, 3),
            unit_price NUMERIC(14, 2),
            total_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
            note TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(expense_id) REFERENCES expenses(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_expense_items_expense_id ON expense_items(expense_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_expense_items_id ON expense_items(id)")

    pending_items = count_pending_receipt_items(cursor)
    cursor.execute(
        """
        INSERT INTO expense_items (
            expense_id,
            line_no,
            name,
            quantity,
            unit_price,
            total_amount,
            note,
            created_at
        )
        SELECT
            pr.expense_id,
            pri.line_no,
            pri.name,
            pri.quantity,
            pri.unit_price,
            pri.total_amount,
            NULL,
            CURRENT_TIMESTAMP
        FROM purchase_receipts pr
        JOIN purchase_receipt_items pri ON pri.receipt_id = pr.id
        WHERE pr.expense_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM expense_items ei
              WHERE ei.expense_id = pr.expense_id
          )
        ORDER BY pr.expense_id, pri.line_no
        """
    )
    return pending_items


def main() -> None:
    parser = argparse.ArgumentParser(description="Migration v18: expense line items.")
    parser.add_argument("--dry-run", action="store_true", help="Run migration in a transaction and roll it back.")
    args = parser.parse_args()

    db_path = get_db_path()
    print(f"[v18] Using DB: {db_path}")
    if args.dry_run:
        print("[v18] Dry-run mode: changes will be rolled back.")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN")
        pending_items = run_migration(conn)
        if args.dry_run:
            conn.rollback()
            print(f"[v18] Would copy receipt items into expense_items: {pending_items}")
            print("[v18] Dry-run completed, no changes committed.")
            return

        conn.commit()
        print(f"[v18] Copied receipt items into expense_items: {pending_items}")
        print("[v18] Migration completed successfully.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
