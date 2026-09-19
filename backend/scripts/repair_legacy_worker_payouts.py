"""Link legacy salary cash expenses to workers so they count as worker payouts.

Записи, сделанные до появления модуля выплат, лежат в кассе обычными наличными
расходами: у них нет строки в worker_payouts, поэтому они не попадают в
статистику выплат и открываются обычным редактором операции. Скрипт находит
такие расходы по зарплатной категории и точному совпадению описания с именем
работника и создаёт для них выплату поверх существующих записей.

Деньги не меняются: дата, сумма, проект, договор и категория берутся из самого
расхода. Ставок и дней за старой записью нет, поэтому начислено = выдано,
остаток нулевой.

В отличие от остальных repair-скриптов по умолчанию работает в режиме
предпросмотра: запись в БД включается флагом --apply.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from backend.config import get_settings

PAYOUT_TYPES = ("regular", "weekly", "monthly", "trip_advance", "trip_final")


def get_db_path() -> Path:
    url = get_settings().database_url
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            raw = Path(url[len(prefix) :])
            return raw.resolve() if raw.is_absolute() else (ROOT_DIR / raw).resolve()
    return (ROOT_DIR / "prospel.db").resolve()


def find_salary_category_ids(cursor: sqlite3.Cursor) -> list[int]:
    cursor.execute(
        """
        SELECT id FROM transaction_categories
        WHERE category_type = 'expense'
          AND (LOWER(COALESCE(name_sr, '')) LIKE '%zarad%' OR LOWER(COALESCE(name_ru, '')) LIKE '%зарп%')
        ORDER BY id
        """
    )
    return [int(row[0]) for row in cursor.fetchall()]


def load_workers(cursor: sqlite3.Cursor, *, include_inactive: bool) -> dict[str, list[sqlite3.Row]]:
    sql = "SELECT id, name, is_active FROM workers"
    if not include_inactive:
        sql += " WHERE is_active = 1"
    cursor.execute(sql)
    by_name: dict[str, list[sqlite3.Row]] = {}
    for row in cursor.fetchall():
        key = str(row["name"] or "").strip().lower()
        if key:
            by_name.setdefault(key, []).append(row)
    return by_name


def find_candidates(cursor: sqlite3.Cursor, category_ids: list[int], args: argparse.Namespace) -> list[sqlite3.Row]:
    placeholders = ", ".join("?" for _ in category_ids)
    conditions = [
        "ce.entry_type = 'expense'",
        "ce.expense_id IS NOT NULL",
        f"e.category_id IN ({placeholders})",
        "wp.id IS NULL",
        "ROUND(ABS(COALESCE(ce.amount, 0)), 2) > 0",
    ]
    params: list[object] = list(category_ids)
    if args.date_from:
        conditions.append("date(ce.date) >= date(?)")
        params.append(args.date_from)
    if args.date_to:
        conditions.append("date(ce.date) <= date(?)")
        params.append(args.date_to)
    if args.entry_id:
        conditions.append(f"ce.id IN ({', '.join('?' for _ in args.entry_id)})")
        params.extend(args.entry_id)

    cursor.execute(
        f"""
        SELECT
            ce.id AS cash_entry_id,
            ce.date AS date,
            ROUND(ABS(COALESCE(ce.amount, 0)), 2) AS amount,
            ce.description AS description,
            ce.note AS note,
            e.id AS expense_id,
            e.project_id AS project_id,
            e.contract_id AS contract_id,
            e.category_id AS category_id
        FROM cash_entries ce
        JOIN expenses e ON e.id = ce.expense_id
        LEFT JOIN worker_payouts wp ON wp.cash_entry_id = ce.id OR wp.expense_id = ce.expense_id
        WHERE {" AND ".join(conditions)}
        ORDER BY ce.date, ce.id
        """,
        params,
    )
    return cursor.fetchall()


def run(args: argparse.Namespace) -> int:
    db_path = get_db_path()
    print(f"[legacy-payouts] Using DB: {db_path}")
    print(f"[legacy-payouts] Mode: {'APPLY (changes will be committed)' if args.apply else 'dry-run (preview only)'}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    linked = 0
    linked_amount = Decimal("0.00")
    skipped_no_worker = 0
    skipped_ambiguous = 0

    try:
        conn.execute("BEGIN")
        cursor = conn.cursor()

        category_ids = find_salary_category_ids(cursor)
        if not category_ids:
            print("[legacy-payouts] Salary category was not found; nothing to do.")
            conn.rollback()
            return 1
        print(f"[legacy-payouts] Salary category ids: {category_ids}")

        workers_by_name = load_workers(cursor, include_inactive=args.include_inactive_workers)
        candidates = find_candidates(cursor, category_ids, args)
        created_at = datetime.utcnow().isoformat(sep=" ")

        for row in candidates:
            name_key = str(row["description"] or "").strip().lower()
            matches = workers_by_name.get(name_key, [])
            if not matches:
                skipped_no_worker += 1
                if args.verbose:
                    print(
                        f"[SKIPPED] cash #{row['cash_entry_id']} {row['date']} {row['amount']} "
                        f"reason=no worker named {row['description']!r}"
                    )
                continue
            if len(matches) > 1:
                skipped_ambiguous += 1
                print(
                    f"[SKIPPED] cash #{row['cash_entry_id']} {row['date']} {row['amount']} "
                    f"reason=several workers named {row['description']!r}"
                )
                continue

            worker = matches[0]
            if args.worker_id and int(worker["id"]) not in args.worker_id:
                continue

            amount = Decimal(str(row["amount"])).quantize(Decimal("0.01"))
            label = "LINKED" if args.apply else "WOULD-LINK"
            print(
                f"[{label}] cash #{row['cash_entry_id']} {row['date']} {amount} "
                f"-> worker #{worker['id']} {worker['name']} type={args.payout_type}"
            )
            cursor.execute(
                """
                INSERT INTO worker_payouts (
                    worker_id, cash_entry_id, expense_id, payout_type, date,
                    work_days, trip_days, lodging_nights,
                    regular_day_rate, weekly_rate, monthly_rate,
                    trip_pricing_mode, trip_work_day_rate, trip_per_diem_rate,
                    trip_food_rate, trip_advance_day_rate, lodging_night_rate, lodging_amount,
                    advance_paid, gross_amount, cash_paid_amount, remaining_amount,
                    description, note, project_id, contract_id, category_id, created_at
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    0, 0, 0,
                    0, 0, 0,
                    'allowances', 0, 0,
                    0, 0, 0, 0,
                    0, ?, ?, 0,
                    ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    int(worker["id"]),
                    int(row["cash_entry_id"]),
                    int(row["expense_id"]),
                    args.payout_type,
                    row["date"],
                    str(amount),
                    str(amount),
                    str(row["description"] or worker["name"])[:500],
                    row["note"],
                    row["project_id"],
                    row["contract_id"],
                    row["category_id"],
                    created_at,
                ),
            )
            linked += 1
            linked_amount += amount

        if args.apply:
            conn.commit()
        else:
            conn.rollback()

        print("[legacy-payouts] Summary:")
        print(f"  candidates: {len(candidates)}")
        print(f"  {'linked' if args.apply else 'would_link'}: {linked}")
        print(f"  linked_amount: {linked_amount}")
        print(f"  skipped_no_worker: {skipped_no_worker}")
        print(f"  skipped_ambiguous: {skipped_ambiguous}")
        if not args.apply:
            print("[legacy-payouts] Dry-run finished, nothing was written. Re-run with --apply to commit.")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create worker payouts for legacy salary cash expenses matched by worker name."
    )
    parser.add_argument("--apply", action="store_true", help="Commit changes (without it the run is a preview).")
    parser.add_argument(
        "--payout-type",
        default="regular",
        choices=PAYOUT_TYPES,
        help="Payout type stored for linked records (default: regular).",
    )
    parser.add_argument("--date-from", help="Limit to cash entries from this date (YYYY-MM-DD).")
    parser.add_argument("--date-to", help="Limit to cash entries up to this date (YYYY-MM-DD).")
    parser.add_argument("--entry-id", action="append", type=int, help="Limit to a cash entry id. Can be repeated.")
    parser.add_argument("--worker-id", action="append", type=int, help="Limit to a worker id. Can be repeated.")
    parser.add_argument(
        "--include-inactive-workers",
        action="store_true",
        help="Also match archived workers (old payouts often belong to them).",
    )
    parser.add_argument("--verbose", action="store_true", help="Print entries skipped because no worker matched.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
