from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
import html
import sys

sys.stdout.reconfigure(encoding="utf-8")


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.row is not None and self.cell is not None:
            self.row.append(html.unescape("".join(self.cell).strip()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def read_table(path: str) -> list[dict[str, str]]:
    parser = TableParser()
    parser.feed(Path(path).read_text(encoding="utf-8-sig", errors="replace"))
    header = parser.rows[0]
    return [dict(zip(header, row)) for row in parser.rows[1:] if len(row) == len(header)]


def money(value: str | None) -> Decimal:
    return Decimal(str(value or "0").replace(" ", "").replace(",", "."))


rows = read_table(r"D:\Downloads\bank_transactions_2026-07-01.xls")
inflows_2026 = [row for row in rows if row.get("Дата", "").startswith("2026-") and money(row.get("Сумма (RSD)")) > 0]

by_status: dict[str, Decimal] = defaultdict(Decimal)
by_project: dict[str, Decimal] = defaultdict(Decimal)
for row in inflows_2026:
    amount = money(row.get("Сумма (RSD)"))
    by_status[row.get("Статус", "")] += amount
    by_project[row.get("Проект", "")] += amount

print(f"total_inflows_2026={sum(money(row.get('Сумма (RSD)')) for row in inflows_2026)}")
print("\nBY_STATUS")
for key, value in sorted(by_status.items(), key=lambda item: (-item[1], item[0])):
    print(f"{value}|{key}")

print("\nBY_PROJECT")
for key, value in sorted(by_project.items(), key=lambda item: (-item[1], item[0])):
    print(f"{value}|{key}")

print("\nINFLOW_ROWS")
for row in inflows_2026:
    print("|".join([
        row.get("Дата", ""),
        row.get("Референс", ""),
        row.get("Сумма (RSD)", ""),
        row.get("Статус", ""),
        row.get("Проект", ""),
        row.get("Контрагент", ""),
        row.get("Назначение", ""),
    ]))
