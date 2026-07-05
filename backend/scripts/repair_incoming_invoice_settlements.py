"""Repair historical incoming invoice settlements.

This one-time script fixes invoices imported before the
incoming_invoice_settlements journal existed. It is intentionally conservative:
by default it only prints a plan. Pass --apply to write changes.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


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


def dec(value) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def same_money(left, right) -> bool:
    return abs(dec(left) - dec(right)) <= Decimal("0.01")


def money(value) -> str:
    return f"{dec(value):.2f}"


def load_candidates(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        con.execute(
            """
            WITH settlement_totals AS (
                SELECT incoming_invoice_id, COUNT(*) AS settlement_count, COALESCE(SUM(amount), 0) AS settlement_sum
                FROM incoming_invoice_settlements
                GROUP BY incoming_invoice_id
            )
            SELECT
                ii.id AS invoice_id,
                ii.counterparty_name,
                ii.amount AS invoice_amount,
                ii.settled_amount,
                ii.status AS invoice_status,
                ii.expense_id,
                e.source AS expense_source,
                e.amount AS expense_amount,
                e.status AS expense_status,
                e.date AS expense_date,
                e.paid_date AS expense_paid_date,
                e.bank_reference AS expense_bank_reference,
                e.description AS expense_description,
                COALESCE(st.settlement_count, 0) AS settlement_count,
                COALESCE(st.settlement_sum, 0) AS settlement_sum
            FROM incoming_invoices ii
            JOIN expenses e ON e.id = ii.expense_id
            LEFT JOIN settlement_totals st ON st.incoming_invoice_id = ii.id
            WHERE
                ii.status IN ('paid', 'partial')
                AND ROUND(COALESCE(ii.settled_amount, 0), 2) > 0
                AND COALESCE(st.settlement_count, 0) = 0
                AND ROUND(COALESCE(st.settlement_sum, 0), 2) != ROUND(COALESCE(ii.settled_amount, 0), 2)
                AND e.source = 'bank_import'
            ORDER BY ii.id
            """
        )
    )


def find_bank_payments(con: sqlite3.Connection, expense_id: int, expected_amount: Decimal) -> list[sqlite3.Row]:
    rows = list(
        con.execute(
            """
            SELECT id, date, amount, direction, status, matched_type, matched_id, counterparty_name, purpose, bank_reference
            FROM bank_transactions
            WHERE matched_type = 'expense' AND matched_id = ?
            ORDER BY date, id
            """,
            (expense_id,),
        )
    )
    exact = [row for row in rows if same_money(abs(dec(row["amount"])), expected_amount)]
    return exact or rows


def find_cash_payments(con: sqlite3.Connection, expense_id: int, expected_amount: Decimal) -> list[sqlite3.Row]:
    rows = list(
        con.execute(
            """
            SELECT id, date, amount, direction, entry_type, description
            FROM cash_entries
            WHERE expense_id = ?
            ORDER BY date, id
            """,
            (expense_id,),
        )
    )
    exact = [row for row in rows if same_money(abs(dec(row["amount"])), expected_amount)]
    return exact or rows


def build_plan(con: sqlite3.Connection) -> tuple[list[dict], list[dict]]:
    repairs: list[dict] = []
    unresolved: list[dict] = []
    for invoice in load_candidates(con):
        expense_id = int(invoice["expense_id"])
        expected_amount = dec(invoice["settled_amount"])
        bank_payments = find_bank_payments(con, expense_id, expected_amount)
        cash_payments = find_cash_payments(con, expense_id, expected_amount)

        exact_bank = [row for row in bank_payments if same_money(abs(dec(row["amount"])), expected_amount)]
        exact_cash = [row for row in cash_payments if same_money(abs(dec(row["amount"])), expected_amount)]

        if len(exact_bank) == 1 and not exact_cash:
            tx = exact_bank[0]
            repairs.append(
                {
                    "invoice": invoice,
                    "settlement_type": "bank",
                    "amount": expected_amount,
                    "date": tx["date"],
                    "bank_transaction_id": int(tx["id"]),
                    "cash_entry_id": None,
                    "note": f"v17 repair: historical bank settlement for expense #{expense_id}",
                }
            )
        elif len(exact_cash) == 1 and not exact_bank:
            cash = exact_cash[0]
            repairs.append(
                {
                    "invoice": invoice,
                    "settlement_type": "cash",
                    "amount": expected_amount,
                    "date": cash["date"],
                    "bank_transaction_id": None,
                    "cash_entry_id": int(cash["id"]),
                    "note": f"v17 repair: historical cash settlement for expense #{expense_id}",
                }
            )
        else:
            unresolved.append(
                {
                    "invoice": invoice,
                    "bank_payments": bank_payments,
                    "cash_payments": cash_payments,
                    "reason": "expected exactly one exact bank or cash payment",
                }
            )
    return repairs, unresolved


def print_plan(repairs: list[dict], unresolved: list[dict]) -> None:
    print(f"[v17] Repairable invoices: {len(repairs)}")
    for item in repairs:
        invoice = item["invoice"]
        target = (
            f"bank_transaction_id={item['bank_transaction_id']}"
            if item["settlement_type"] == "bank"
            else f"cash_entry_id={item['cash_entry_id']}"
        )
        print(
            "  "
            f"invoice={invoice['invoice_id']} expense={invoice['expense_id']} "
            f"amount={money(item['amount'])} type={item['settlement_type']} {target} "
            f"date={item['date']} source={invoice['expense_source']}"
        )

    print(f"[v17] Unresolved invoices: {len(unresolved)}")
    for item in unresolved:
        invoice = item["invoice"]
        print(
            "  "
            f"invoice={invoice['invoice_id']} expense={invoice['expense_id']} "
            f"settled={money(invoice['settled_amount'])} amount={money(invoice['invoice_amount'])} "
            f"bank_candidates={len(item['bank_payments'])} cash_candidates={len(item['cash_payments'])} "
            f"reason={item['reason']}"
        )


def apply_repairs(con: sqlite3.Connection, repairs: list[dict]) -> None:
    with con:
        for item in repairs:
            invoice = item["invoice"]
            invoice_id = int(invoice["invoice_id"])
            expense_id = int(invoice["expense_id"])
            amount = money(item["amount"])

            con.execute(
                """
                INSERT INTO incoming_invoice_settlements (
                    incoming_invoice_id,
                    settlement_type,
                    amount,
                    date,
                    note,
                    bank_transaction_id,
                    cash_entry_id,
                    income_id,
                    created_at,
                    created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, CURRENT_TIMESTAMP, NULL)
                """,
                (
                    invoice_id,
                    item["settlement_type"],
                    amount,
                    item["date"],
                    item["note"],
                    item["bank_transaction_id"],
                    item["cash_entry_id"],
                ),
            )
            con.execute(
                """
                UPDATE expenses
                SET source = 'incoming_invoice'
                WHERE id = ? AND source = 'bank_import'
                """,
                (expense_id,),
            )

            settlement_sum = con.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM incoming_invoice_settlements
                WHERE incoming_invoice_id = ?
                """,
                (invoice_id,),
            ).fetchone()[0]
            invoice_amount = dec(invoice["invoice_amount"])
            new_status = "paid" if dec(settlement_sum) + Decimal("0.01") >= invoice_amount else "partial"
            con.execute(
                """
                UPDATE incoming_invoices
                SET settled_amount = ?, status = ?
                WHERE id = ? AND status != 'cancelled'
                """,
                (money(settlement_sum), new_status, invoice_id),
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair historical incoming invoice settlement rows.")
    parser.add_argument("--apply", action="store_true", help="write repairs to the database")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    db_path = get_db_path(root)
    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path}")
        return 1

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        repairs, unresolved = build_plan(con)
        print(f"[v17] Database: {db_path}")
        print_plan(repairs, unresolved)

        if unresolved:
            print("[ERROR] Refusing to apply while unresolved invoices remain.")
            print("[ERROR] Resolve them manually or update the repair logic after reviewing the dry-run output.")
            return 1
        if not repairs:
            print("[v17] Nothing to repair.")
            return 0
        if not args.apply:
            print("[v17] Dry-run only. Run with --apply to write changes.")
            return 0

        backup_dir = root / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / f"manual_repair_incoming_invoice_settlements_{datetime.now():%Y%m%d_%H%M%S}.db"
        shutil.copy2(db_path, backup_path)
        print(f"[v17] Backup created: {backup_path}")

        apply_repairs(con, repairs)
        print(f"[v17] Applied repairs: {len(repairs)}")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
