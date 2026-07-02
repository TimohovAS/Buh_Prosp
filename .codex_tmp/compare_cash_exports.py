from __future__ import annotations

import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

from cash_after_correction_report import CashRow, find_correction, money, read_cash_rows


OLD_EXPORT = Path(r"D:\Downloads\cash_register_2026-07-01 (1).xls")
NEW_EXPORT = Path(r"D:\Downloads\cash_register_2026-07-01.xls")


def key(row: CashRow) -> tuple[str, str, str, str, Decimal, Decimal]:
    return (
        row.date,
        row.kind,
        row.description,
        row.source,
        row.inflow,
        row.outflow,
    )


def source_key(row: CashRow) -> str:
    if row.source and row.source != "—":
        return row.source
    return f"{row.date}|{row.kind}|{row.description}|{row.inflow}|{row.outflow}"


def summarize(label: str, rows: list[CashRow]) -> None:
    corr = rows[find_correction(rows)]
    print(f"{label}: rows={len(rows)} current={money(rows[0].balance_after)} correction_balance={money(corr.balance_after)} correction_amount={money(corr.net)}")


def print_rows(title: str, rows: list[CashRow]) -> None:
    print()
    print(title)
    for row in rows:
        print(
            f"{row.date} | {row.kind} | in={money(row.inflow)} | out={money(row.outflow)} | bal={money(row.balance_after)} | {row.source} | {row.description}"
        )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    old = read_cash_rows(OLD_EXPORT)
    new = read_cash_rows(NEW_EXPORT)
    summarize("OLD_9AM", old)
    summarize("NEW", new)

    old_counter = Counter(key(row) for row in old)
    new_counter = Counter(key(row) for row in new)

    removed: list[CashRow] = []
    added: list[CashRow] = []

    for row in old:
        k = key(row)
        if old_counter[k] > new_counter[k]:
            removed.append(row)
            old_counter[k] -= 1
    old_counter = Counter(key(row) for row in old)
    for row in new:
        k = key(row)
        if new_counter[k] > old_counter[k]:
            added.append(row)
            new_counter[k] -= 1

    print_rows("REMOVED_FROM_9AM_EXPORT", removed)
    print_rows("ADDED_IN_NEW_EXPORT", added)

    old_by_source = {source_key(row): row for row in old}
    new_by_source = {source_key(row): row for row in new}
    changed_by_source = []
    for sk, old_row in old_by_source.items():
        new_row = new_by_source.get(sk)
        if not new_row:
            continue
        if (
            old_row.kind != new_row.kind
            or old_row.date != new_row.date
            or old_row.inflow != new_row.inflow
            or old_row.outflow != new_row.outflow
            or old_row.balance_after != new_row.balance_after
        ):
            changed_by_source.append((old_row, new_row))

    print()
    print("SAME_SOURCE_CHANGED")
    for old_row, new_row in changed_by_source[:40]:
        print(
            f"{old_row.source}: {old_row.date}/{old_row.kind}/in={money(old_row.inflow)}/out={money(old_row.outflow)}/bal={money(old_row.balance_after)} -> "
            f"{new_row.date}/{new_row.kind}/in={money(new_row.inflow)}/out={money(new_row.outflow)}/bal={money(new_row.balance_after)}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
