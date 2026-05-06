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


def main() -> None:
    print(f"[v15] Using DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE expenses
            SET amount = ABS(amount)
            WHERE amount < 0
              AND reversal_of_id IS NULL
              AND COALESCE(status, '') != 'reversed'
            """
        )
        normalized_expenses = cursor.rowcount

        cursor.execute(
            """
            UPDATE cash_entries
            SET amount = ABS(amount)
            WHERE amount < 0
            """
        )
        normalized_cash_entries = cursor.rowcount

        cursor.execute(
            """
            UPDATE incoming_invoice_settlements
            SET amount = ABS(amount)
            WHERE amount < 0
              AND settlement_type IN ('bank', 'cash', 'offset')
            """
        )
        normalized_settlements = cursor.rowcount

        conn.commit()
        print(f"[v15] Normalized expenses: {normalized_expenses}")
        print(f"[v15] Normalized cash entries: {normalized_cash_entries}")
        print(f"[v15] Normalized incoming invoice settlements: {normalized_settlements}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
