"""One-time repair: restore BankTransaction -> Expense links for existing bank-import expenses."""
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
            raw = url[len(prefix):]
            path = Path(raw)
            if not path.is_absolute():
                return (ROOT_DIR / path).resolve()
            return path.resolve()
    return (ROOT_DIR / "prospel.db").resolve()


DB_PATH = get_db_path()


def main() -> None:
    print(f"[repair-bank-expense] Using DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    linked = 0
    skipped_ambiguous = 0
    skipped_conflict = 0

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, bank_reference, ROUND(ABS(COALESCE(amount, 0)), 2) AS amount_abs, project_id
            FROM expenses
            WHERE source = 'bank_import'
              AND bank_reference IS NOT NULL
              AND TRIM(bank_reference) <> ''
              AND status <> 'reversed'
              AND reversal_of_id IS NULL
            ORDER BY date, id
            """
        )
        expenses = cursor.fetchall()

        for expense in expenses:
            cursor.execute(
                """
                SELECT id, status, matched_type, matched_id
                FROM bank_transactions
                WHERE bank_reference = ?
                  AND direction = 'out'
                  AND ROUND(ABS(COALESCE(amount, 0)), 2) = ?
                """,
                (expense["bank_reference"], expense["amount_abs"]),
            )
            candidates = cursor.fetchall()

            if len(candidates) != 1:
                skipped_ambiguous += 1
                continue

            tx = candidates[0]
            matched_type = tx["matched_type"]
            matched_id = tx["matched_id"]
            if matched_type not in (None, "", "expense") or (matched_type == "expense" and matched_id not in (None, expense["id"])):
                skipped_conflict += 1
                continue

            cursor.execute(
                """
                UPDATE bank_transactions
                SET status = 'matched',
                    matched_type = 'expense',
                    matched_id = ?,
                    project_id = ?
                WHERE id = ?
                """,
                (expense["id"], expense["project_id"], tx["id"]),
            )
            linked += 1

        conn.commit()
        print(f"[repair-bank-expense] Linked: {linked}")
        print(f"[repair-bank-expense] Skipped ambiguous: {skipped_ambiguous}")
        print(f"[repair-bank-expense] Skipped conflicts: {skipped_conflict}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
