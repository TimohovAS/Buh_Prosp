from __future__ import annotations

import sqlite3
import sys
from decimal import Decimal
from pathlib import Path


def dec(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def money(value) -> str:
    return f"{dec(value):,.2f}".replace(",", " ")


def print_rows(title: str, rows: list[sqlite3.Row], columns: list[str], limit: int | None = None) -> None:
    print(f"\n## {title}")
    if not rows:
        print("(none)")
        return
    rows_to_print = rows[:limit] if limit else rows
    print(" | ".join(columns))
    print(" | ".join("---" for _ in columns))
    for row in rows_to_print:
        values = []
        for col in columns:
            value = row[col]
            if col.endswith("amount") or col in {"amount", "bank_amount", "cash_amount", "pending_amount", "withdrawal_amount"}:
                value = money(value)
            values.append("" if value is None else str(value))
        print(" | ".join(values))
    if limit and len(rows) > limit:
        print(f"... {len(rows) - limit} more")


db_path = Path(sys.argv[1])
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

try:
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN direction = 'in' THEN amount ELSE 0 END), 0) AS total_in,
            COALESCE(SUM(CASE WHEN direction = 'out' THEN amount ELSE 0 END), 0) AS total_out,
            COALESCE(SUM(CASE WHEN direction = 'in' THEN amount ELSE -amount END), 0) AS balance
        FROM cash_entries
        """
    )
    totals = cursor.fetchone()

    cursor.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN direction = 'in' THEN amount ELSE 0 END), 0) AS total_in,
            COALESCE(SUM(CASE WHEN direction = 'out' THEN amount ELSE 0 END), 0) AS total_out,
            COALESCE(SUM(CASE WHEN direction = 'in' THEN amount ELSE -amount END), 0) AS balance
        FROM cash_entries
        WHERE entry_type <> 'pending_withdrawal'
        """
    )
    confirmed_totals = cursor.fetchone()

    cursor.execute(
        """
        SELECT
            COUNT(*) AS count,
            COALESCE(SUM(amount), 0) AS amount
        FROM cash_entries
        WHERE entry_type = 'pending_withdrawal'
          AND direction = 'in'
          AND bank_transaction_id IS NULL
          AND expense_id IS NULL
        """
    )
    pending_total = cursor.fetchone()

    print("# Cash/Bank Reconciliation Snapshot")
    print(f"DB: {db_path}")
    print(f"cash balance all entries: {money(totals['balance'])}")
    print(f"cash balance excluding pending: {money(confirmed_totals['balance'])}")
    print(f"pending withdrawals: count={pending_total['count']} amount={money(pending_total['amount'])}")
    print(f"cash total_in all/confirmed: {money(totals['total_in'])} / {money(confirmed_totals['total_in'])}")
    print(f"cash total_out all/confirmed: {money(totals['total_out'])} / {money(confirmed_totals['total_out'])}")

    cursor.execute(
        """
        SELECT
            b.id AS bank_id,
            b.date,
            b.bank_reference,
            b.amount AS bank_amount,
            b.status,
            b.matched_type,
            b.matched_id,
            COALESCE(p.code, '') AS project_code,
            COALESCE(p.name, '') AS project_name,
            e.id AS expense_id,
            e.source AS expense_source,
            e.category AS expense_category,
            c.id AS cash_entry_id,
            c.entry_type AS cash_entry_type,
            c.amount AS cash_amount,
            c.date AS cash_date,
            b.purpose
        FROM bank_transactions b
        LEFT JOIN expenses e ON b.matched_type = 'expense' AND b.matched_id = e.id
        LEFT JOIN projects p ON COALESCE(e.project_id, b.project_id) = p.id
        LEFT JOIN cash_entries c ON c.bank_transaction_id = b.id
        WHERE b.direction = 'out'
          AND (
            LOWER(COALESCE(b.purpose, '')) LIKE '%atm%'
            OR LOWER(COALESCE(b.purpose, '')) LIKE '%gotovin%'
            OR LOWER(COALESCE(b.purpose, '')) LIKE '%podiz%'
            OR e.source = 'cash_transfer'
            OR e.category = 'cash'
            OR p.code = 'INT-CASH'
          )
        ORDER BY b.date DESC, b.id DESC
        """
    )
    bank_cash_rows = cursor.fetchall()
    print_rows(
        "Bank rows that look like cash withdrawals/transfers",
        bank_cash_rows,
        [
            "bank_id",
            "date",
            "bank_reference",
            "bank_amount",
            "status",
            "matched_type",
            "matched_id",
            "project_code",
            "expense_source",
            "expense_category",
            "cash_entry_id",
            "cash_entry_type",
            "cash_amount",
            "cash_date",
        ],
    )

    cursor.execute(
        """
        SELECT
            c.id,
            c.date,
            c.entry_type,
            c.direction,
            c.amount,
            COALESCE(c.currency, 'RSD') AS currency,
            c.bank_transaction_id,
            c.expense_id,
            b.bank_reference,
            b.status AS bank_status,
            b.amount AS bank_amount,
            e.source AS expense_source,
            e.category AS expense_category,
            c.description
        FROM cash_entries c
        LEFT JOIN bank_transactions b ON b.id = c.bank_transaction_id
        LEFT JOIN expenses e ON e.id = c.expense_id
        WHERE c.entry_type IN ('withdrawal', 'pending_withdrawal')
        ORDER BY c.date DESC, c.id DESC
        """
    )
    cash_withdrawals = cursor.fetchall()
    print_rows(
        "Cash withdrawal/pending rows",
        cash_withdrawals,
        [
            "id",
            "date",
            "entry_type",
            "direction",
            "amount",
            "currency",
            "bank_transaction_id",
            "expense_id",
            "bank_reference",
            "bank_status",
            "bank_amount",
            "expense_source",
            "expense_category",
        ],
    )

    cursor.execute(
        """
        SELECT
            p.id AS pending_id,
            p.date AS pending_date,
            p.amount AS pending_amount,
            w.id AS withdrawal_id,
            w.date AS withdrawal_date,
            w.amount AS withdrawal_amount,
            w.bank_transaction_id,
            w.expense_id,
            b.bank_reference,
            b.amount AS bank_amount
        FROM cash_entries p
        JOIN cash_entries w
          ON w.entry_type = 'withdrawal'
         AND w.direction = 'in'
         AND w.bank_transaction_id IS NOT NULL
         AND ROUND(ABS(COALESCE(w.amount, 0)), 2) = ROUND(ABS(COALESCE(p.amount, 0)), 2)
         AND COALESCE(w.currency, 'RSD') = COALESCE(p.currency, 'RSD')
         AND date(w.date) >= date(p.date)
         AND date(w.date) <= date(p.date, '+14 days')
        JOIN bank_transactions b ON b.id = w.bank_transaction_id
        WHERE p.entry_type = 'pending_withdrawal'
          AND p.direction = 'in'
          AND p.bank_transaction_id IS NULL
          AND p.expense_id IS NULL
        ORDER BY p.date DESC, p.id DESC
        """
    )
    duplicate_pending = cursor.fetchall()
    print_rows(
        "Pending rows duplicated by linked bank withdrawals",
        duplicate_pending,
        [
            "pending_id",
            "pending_date",
            "pending_amount",
            "withdrawal_id",
            "withdrawal_date",
            "withdrawal_amount",
            "bank_transaction_id",
            "expense_id",
            "bank_reference",
            "bank_amount",
        ],
    )

    cursor.execute(
        """
        SELECT
            b.id AS bank_id,
            b.date,
            b.bank_reference,
            b.amount AS bank_amount,
            b.status,
            b.matched_type,
            b.matched_id,
            e.source AS expense_source,
            e.category AS expense_category,
            p.code AS project_code,
            p.name AS project_name
        FROM bank_transactions b
        LEFT JOIN expenses e ON b.matched_type = 'expense' AND b.matched_id = e.id
        LEFT JOIN projects p ON COALESCE(e.project_id, b.project_id) = p.id
        LEFT JOIN cash_entries c ON c.bank_transaction_id = b.id
        WHERE b.direction = 'out'
          AND c.id IS NULL
          AND (
            e.source = 'cash_transfer'
            OR e.category = 'cash'
            OR p.code = 'INT-CASH'
            OR LOWER(COALESCE(b.purpose, '')) LIKE '%atm%'
          )
        ORDER BY b.date DESC, b.id DESC
        """
    )
    bank_without_cash = cursor.fetchall()
    print_rows(
        "Cash-looking bank rows without cash entry",
        bank_without_cash,
        [
            "bank_id",
            "date",
            "bank_reference",
            "bank_amount",
            "status",
            "matched_type",
            "matched_id",
            "expense_source",
            "expense_category",
            "project_code",
        ],
    )

finally:
    conn.close()
