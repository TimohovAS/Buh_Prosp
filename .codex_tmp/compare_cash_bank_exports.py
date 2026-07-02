from __future__ import annotations

from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
import html
import re


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None
        self.in_cell = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self.current_row = []
        elif tag in {"td", "th"} and self.current_row is not None:
            self.current_cell = []
            self.in_cell = True

    def handle_data(self, data: str) -> None:
        if self.in_cell and self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.in_cell and self.current_cell is not None and self.current_row is not None:
            self.current_row.append(html.unescape("".join(self.current_cell).strip()))
            self.current_cell = None
            self.in_cell = False
        elif tag == "tr" and self.current_row is not None:
            self.rows.append(self.current_row)
            self.current_row = None


def read_table(path: str) -> tuple[list[str], list[dict[str, str]]]:
    parser = TableParser()
    parser.feed(Path(path).read_text(encoding="utf-8-sig", errors="replace"))
    header = parser.rows[0]
    rows = [dict(zip(header, row)) for row in parser.rows[1:] if len(row) == len(header)]
    return header, rows


def money(value: str | int | float | Decimal | None) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(" ", "").replace(",", "."))
    except Exception:
        return Decimal("0")


def cash_ref(row: dict[str, str]) -> str:
    match = re.search(r"(\d{8,})", row.get("Источник", ""))
    return match.group(1) if match else ""


cash_header, cash_rows = read_table(r"D:\Downloads\cash_register_2026-07-01.xls")
bank_header, bank_rows = read_table(r"D:\Downloads\bank_transactions_2026-07-01.xls")

cash_by_ref = {cash_ref(row): row for row in cash_rows if cash_ref(row)}
bank_cash_rows = [row for row in bank_rows if row.get("Проект") == "_Gotovina / Наличка"]
matched = [row for row in bank_cash_rows if row.get("Референс") in cash_by_ref]
missing = [row for row in bank_cash_rows if row.get("Референс") not in cash_by_ref]

print(f"cash rows: {len(cash_rows)}")
print(f"bank rows: {len(bank_rows)}")
print(f"bank cash rows: {len(bank_cash_rows)}")
print(f"matched bank cash refs in cash: {len(matched)}")
print(f"missing bank cash refs in cash: {len(missing)}")

print("\nMISSING_BANK_CASH_REFS")
for row in missing:
    print("|".join([
        row.get("Дата", ""),
        row.get("Референс", ""),
        row.get("Сумма (RSD)", ""),
        row.get("Назначение", ""),
        row.get("Статус", ""),
    ]))

print("\nMATCHED_DATE_DIFFS")
for row in matched:
    cash_row = cash_by_ref[row.get("Референс")]
    if row.get("Дата") != cash_row.get("Дата"):
        print("|".join([
            row.get("Референс", ""),
            f"bank={row.get('Дата', '')}",
            f"cash={cash_row.get('Дата', '')}",
            row.get("Сумма (RSD)", ""),
            cash_row.get("Приток", ""),
            cash_row.get("Описание", ""),
        ]))

bank_refs = {row.get("Референс") for row in bank_rows}
cash_withdrawals = [row for row in cash_rows if row.get("Тип") == "Снятие из банка"]
extra_cash = [(cash_ref(row), row) for row in cash_withdrawals if cash_ref(row) not in bank_refs]

print("\nCASH_WITHDRAWALS_WITHOUT_EXPORTED_BANK_ROW")
for ref, row in extra_cash:
    print("|".join([
        row.get("Дата", ""),
        ref,
        row.get("Приток", ""),
        row.get("Описание", ""),
        row.get("Источник", ""),
    ]))

inflow = sum((money(row.get("Приток")) for row in cash_rows), Decimal("0"))
outflow = sum((money(row.get("Отток")) for row in cash_rows), Decimal("0"))
print("\nCASH_TOTALS")
print(f"in={inflow}")
print(f"out={outflow}")
print(f"net={inflow - outflow}")
print(f"first_balance_after={cash_rows[0].get('Остаток после операции', '') if cash_rows else ''}")

