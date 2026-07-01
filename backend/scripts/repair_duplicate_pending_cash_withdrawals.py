"""Remove pending cash withdrawals already represented by linked bank withdrawals."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from decimal import Decimal, InvalidOperation
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


def parse_amount(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(" ", "").replace(",", ".")).copy_abs().quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"Invalid amount: {value}") from exc


def build_pending_query(args: argparse.Namespace) -> tuple[str, list[object]]:
    conditions = [
        "entry_type = 'pending_withdrawal'",
        "direction = 'in'",
        "bank_transaction_id IS NULL",
        "expense_id IS NULL",
    ]
    params: list[object] = []

    if args.entry_id:
        placeholders = ", ".join("?" for _ in args.entry_id)
        conditions.append(f"id IN ({placeholders})")
        params.extend(args.entry_id)
    if args.date:
        conditions.append("date = ?")
        params.append(args.date)
    if args.amount is not None:
        conditions.append("ROUND(ABS(COALESCE(amount, 0)), 2) = ?")
        params.append(float(args.amount))

    sql = f"""
        SELECT
            id,
            date,
            ROUND(ABS(COALESCE(amount, 0)), 2) AS amount_abs,
            COALESCE(currency, 'RSD') AS currency,
            description
        FROM cash_entries
        WHERE {' AND '.join(conditions)}
        ORDER BY date, id
    """
    return sql, params


def find_duplicate_withdrawals(
    cursor: sqlite3.Cursor,
    pending: sqlite3.Row,
    *,
    max_days: int,
    bank_reference: str | None,
) -> list[sqlite3.Row]:
    conditions = [
        "w.entry_type = 'withdrawal'",
        "w.direction = 'in'",
        "w.bank_transaction_id IS NOT NULL",
        "ROUND(ABS(COALESCE(w.amount, 0)), 2) = ?",
        "COALESCE(w.currency, 'RSD') = ?",
        "date(w.date) >= date(?)",
        "date(w.date) <= date(?, ?)",
    ]
    params: list[object] = [
        pending["amount_abs"],
        pending["currency"],
        pending["date"],
        pending["date"],
        f"+{max_days} days",
    ]

    if bank_reference:
        conditions.append("b.bank_reference = ?")
        params.append(bank_reference)

    cursor.execute(
        f"""
        SELECT
            w.id,
            w.date,
            w.amount,
            COALESCE(w.currency, 'RSD') AS currency,
            w.bank_transaction_id,
            w.expense_id,
            b.bank_reference,
            b.purpose
        FROM cash_entries w
        JOIN bank_transactions b ON b.id = w.bank_transaction_id
        WHERE {' AND '.join(conditions)}
        ORDER BY ABS(julianday(w.date) - julianday(?)), w.id
        LIMIT 2
        """,
        [*params, pending["date"]],
    )
    return cursor.fetchall()


def run(args: argparse.Namespace) -> int:
    db_path = get_db_path()
    print(f"[repair-cash-pending] Using DB: {db_path}")
    if args.dry_run:
        print("[repair-cash-pending] Dry-run mode: database changes will not be committed.")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    deleted = 0
    would_delete = 0
    affected_amount = Decimal("0.00")
    skipped_no_match = 0
    skipped_ambiguous = 0

    try:
        conn.execute("BEGIN")
        cursor = conn.cursor()
        pending_sql, pending_params = build_pending_query(args)
        cursor.execute(pending_sql, pending_params)
        pending_entries = cursor.fetchall()

        for pending in pending_entries:
            duplicates = find_duplicate_withdrawals(
                cursor,
                pending,
                max_days=args.max_days,
                bank_reference=args.bank_reference,
            )
            if not duplicates:
                skipped_no_match += 1
                continue
            if len(duplicates) > 1:
                skipped_ambiguous += 1
                print(
                    f"[SKIPPED] pending #{pending['id']} {pending['date']} "
                    f"{pending['amount_abs']} {pending['currency']} reason=ambiguous linked withdrawals"
                )
                continue

            withdrawal = duplicates[0]
            label = "WOULD-DELETE" if args.dry_run else "DELETED"
            print(
                f"[{label}] pending #{pending['id']} {pending['date']} "
                f"{pending['amount_abs']} {pending['currency']} duplicate_of="
                f"withdrawal #{withdrawal['id']} bank_ref={withdrawal['bank_reference'] or '-'}"
            )
            if args.dry_run:
                would_delete += 1
            else:
                cursor.execute("DELETE FROM cash_entries WHERE id = ?", (pending["id"],))
                deleted += 1
            affected_amount += Decimal(str(pending["amount_abs"])).quantize(Decimal("0.01"))

        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()

        print("[repair-cash-pending] Summary:")
        print(f"  candidates: {len(pending_entries)}")
        print(f"  deleted: {deleted}")
        print(f"  would_delete: {would_delete}")
        print(f"  removed_inflow_amount: {affected_amount}")
        print(f"  skipped_no_match: {skipped_no_match}")
        print(f"  skipped_ambiguous: {skipped_ambiguous}")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Remove pending cash withdrawal rows duplicated by linked bank withdrawal rows."
    )
    parser.add_argument("--dry-run", action="store_true", help="Print candidate deletes without committing.")
    parser.add_argument("--entry-id", action="append", type=int, help="Limit to a pending cash entry id. Can be repeated.")
    parser.add_argument("--date", help="Limit pending entries to YYYY-MM-DD.")
    parser.add_argument("--amount", type=parse_amount, help="Limit pending entries to an absolute amount.")
    parser.add_argument("--bank-reference", help="Require the duplicate withdrawal to use this bank reference.")
    parser.add_argument("--max-days", type=int, default=14, help="Maximum days from pending entry date to bank withdrawal date.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
