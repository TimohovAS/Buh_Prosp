"""Delete the duplicated Zarade salary expenses created on 2026-05-02.

This is a one-time manual migration. It intentionally refuses to run unless it
finds exactly two safe targets on the same date:
- one row with amount +300000
- one row with amount -300000

The previous version matched the exact project name and exact mojibake text,
which was too brittle for the production DB.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


TARGET_DATE = "2026-05-02"
TARGET_AMOUNT = 300000.0


def _read_env_database_url(root: Path) -> str | None:
    env_path = root / ".env"
    if not env_path.exists():
        return None
    for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "DATABASE_URL":
            return value.strip().strip('"').strip("'")
    return None


def _db_path_from_url(root: Path, url: str) -> Path:
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    for prefix in prefixes:
        if url.startswith(prefix):
            raw_path = url[len(prefix) :]
            path = Path(raw_path)
            return path if path.is_absolute() else root / path
    raise RuntimeError(f"Unsupported DATABASE_URL for this migration: {url}")


def get_db_path(root: Path) -> Path:
    url = os.environ.get("DATABASE_URL") or _read_env_database_url(root) or "sqlite+aiosqlite:///./prospel.db"
    return _db_path_from_url(root, url).resolve()


def print_rows(rows: list[sqlite3.Row]) -> None:
    for row in rows:
        print(
            "  "
            f"id={row['id']} date={row['date']} paid_date={row['paid_date']} "
            f"amount={row['amount']} status={row['status']} source={row['source']} "
            f"project={row['project_name']!r} category={row['category_name']!r} "
            f"description={row['description']!r} "
            f"reversal_of_id={row['reversal_of_id']} reversed_expense_id={row['reversed_expense_id']}"
        )


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    db_path = get_db_path(root)
    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path}")
        return 1

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA foreign_keys = ON")
        rows = list(
            con.execute(
                """
                SELECT
                    e.id,
                    e.date,
                    e.paid_date,
                    e.description,
                    e.amount,
                    e.status,
                    e.source,
                    e.reversal_of_id,
                    e.reversed_expense_id,
                    p.name AS project_name,
                    COALESCE(tc.name_ru, e.category) AS category_name
                FROM expenses e
                LEFT JOIN projects p ON p.id = e.project_id
                LEFT JOIN transaction_categories tc ON tc.id = e.category_id
                WHERE
                    (date(e.date) = ? OR date(e.paid_date) = ?)
                    AND ROUND(ABS(CAST(e.amount AS REAL)), 2) = ?
                    AND (
                        e.description LIKE '%Zarade%'
                        OR p.name LIKE '%Zarade%'
                    )
                ORDER BY e.id
                """,
                (TARGET_DATE, TARGET_DATE, TARGET_AMOUNT),
            )
        )

        print(f"[ProspEl] Database: {db_path}")
        print("[ProspEl] Matching candidates:")
        print_rows(rows)

        amounts = sorted(round(float(row["amount"]), 2) for row in rows)
        if len(rows) != 2 or amounts != [-TARGET_AMOUNT, TARGET_AMOUNT]:
            print()
            print("[ERROR] Refusing to delete: expected exactly two target rows with amounts -300000 and 300000.")
            print(f"[ERROR] Found target rows: {len(rows)}, amounts: {amounts}")
            return 1

        backup_dir = root / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / f"manual_delete_bad_zarade_{datetime.now():%Y%m%d_%H%M%S}.db"
        shutil.copy2(db_path, backup_path)
        print(f"[ProspEl] Backup created: {backup_path}")

        ids = [int(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)

        with con:
            con.execute(
                f"UPDATE expenses SET reversed_expense_id = NULL WHERE reversed_expense_id IN ({placeholders})",
                ids,
            )
            con.execute(
                f"UPDATE expenses SET reversal_of_id = NULL WHERE reversal_of_id IN ({placeholders})",
                ids,
            )
            con.execute(
                f"UPDATE incoming_invoices SET expense_id = NULL, settled_amount = 0, status = 'unpaid' "
                f"WHERE expense_id IN ({placeholders}) AND status != 'cancelled'",
                ids,
            )
            con.execute(
                f"UPDATE monthly_obligations SET expense_id = NULL WHERE expense_id IN ({placeholders})",
                ids,
            )
            con.execute(
                f"UPDATE planned_expense_payments SET expense_id = NULL WHERE expense_id IN ({placeholders})",
                ids,
            )
            con.execute(
                f"UPDATE cash_entries SET expense_id = NULL WHERE expense_id IN ({placeholders})",
                ids,
            )
            con.execute(
                f"UPDATE purchase_receipts SET expense_id = NULL, status = 'new' WHERE expense_id IN ({placeholders})",
                ids,
            )
            con.execute(
                f"""
                UPDATE bank_transactions
                SET matched_type = NULL, matched_id = NULL, status = 'unmatched'
                WHERE matched_type = 'expense' AND matched_id IN ({placeholders})
                """,
                ids,
            )
            con.execute(f"DELETE FROM expenses WHERE id IN ({placeholders})", ids)

        print(f"[ProspEl] Deleted expense ids: {ids}")
        print("[ProspEl] Done.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
