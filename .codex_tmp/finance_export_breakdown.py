from __future__ import annotations

from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
import html


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


bank_rows = read_table(r"D:\Downloads\bank_transactions_2026-07-01.xls")
cash_rows = read_table(r"D:\Downloads\cash_register_2026-07-01.xls")

cash_out = sum(money(row.get("Отток")) for row in cash_rows if row.get("Дата", "").startswith("2026-"))
cash_in = sum(money(row.get("Приток")) for row in cash_rows if row.get("Дата", "").startswith("2026-"))

bank_2026 = [row for row in bank_rows if row.get("Дата", "").startswith("2026-")]
bank_cash_transfers = [
    row for row in bank_2026
    if row.get("Проект") == "_Gotovina / Наличка" and money(row.get("Сумма (RSD)")) < 0
]
bank_expenses = [
    row for row in bank_2026
    if money(row.get("Сумма (RSD)")) < 0
    and row.get("Статус") == "Связано (Расходы)"
    and row.get("Проект") != "_Gotovina / Наличка"
]
bank_obligations = [
    row for row in bank_2026
    if money(row.get("Сумма (RSD)")) < 0
    and row.get("Статус") == "Связано (Налоги и взносы)"
]
bank_owner_or_loan = [
    row for row in bank_2026
    if money(row.get("Сумма (RSD)")) < 0
    and row.get("Статус") in {"Возврат собственных средств", "Погашение полученного займа"}
]
bank_unmatched_out = [
    row for row in bank_2026
    if money(row.get("Сумма (RSD)")) < 0
    and row.get("Статус") == "Без связи"
]

bank_expenses_sum = sum(abs(money(row.get("Сумма (RSD)"))) for row in bank_expenses)
bank_obligations_sum = sum(abs(money(row.get("Сумма (RSD)"))) for row in bank_obligations)
cash_transfer_sum = sum(abs(money(row.get("Сумма (RSD)"))) for row in bank_cash_transfers)
owner_or_loan_sum = sum(abs(money(row.get("Сумма (RSD)"))) for row in bank_owner_or_loan)
unmatched_sum = sum(abs(money(row.get("Сумма (RSD)"))) for row in bank_unmatched_out)

print(f"cash_in_2026={cash_in}")
print(f"cash_out_2026={cash_out}")
print(f"bank_linked_expenses_ex_cash_transfers_2026={bank_expenses_sum}")
print(f"bank_obligations_2026={bank_obligations_sum}")
print(f"bank_cash_transfers_2026={cash_transfer_sum}")
print(f"bank_owner_or_loan_out_2026={owner_or_loan_sum}")
print(f"bank_unmatched_out_2026={unmatched_sum}")
print(f"finance_cash_expense_expected_from_exports={cash_out + bank_expenses_sum + bank_obligations_sum}")
print("\nBANK EXPENSES EX CASH TRANSFERS")
for row in bank_expenses:
    print("|".join([
        row.get("Дата", ""),
        row.get("Референс", ""),
        row.get("Сумма (RSD)", ""),
        row.get("Проект", ""),
        row.get("Назначение", ""),
    ]))

