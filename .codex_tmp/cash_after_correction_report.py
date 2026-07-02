from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from html.parser import HTMLParser
from pathlib import Path


DEFAULT_EXPORT = Path(r"D:\Downloads\cash_register_2026-07-01.xls")
DEFAULT_OUT = Path(".codex_tmp/cash_after_correction_report.md")
MONEY = Decimal("0.01")


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            text = html.unescape("".join(self._cell)).strip()
            text = re.sub(r"\s+", " ", text)
            self._row.append(text)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


@dataclass
class CashRow:
    index: int
    date: str
    kind: str
    description: str
    source: str
    project: str
    inflow: Decimal
    outflow: Decimal
    balance_after: Decimal

    @property
    def net(self) -> Decimal:
        return self.inflow - self.outflow


def money(value: Decimal) -> str:
    value = value.quantize(MONEY, rounding=ROUND_HALF_UP)
    raw = f"{value:,.2f}"
    return raw.replace(",", " ").replace(".00", "")


def parse_decimal(value: str) -> Decimal:
    value = value.strip().replace("\xa0", "").replace(" ", "")
    value = value.replace("RSD", "").replace(",", ".")
    if not value or value == "-":
        return Decimal("0")
    return Decimal(value)


def read_cash_rows(path: Path) -> list[CashRow]:
    parser = TableParser()
    parser.feed(path.read_text(encoding="utf-8"))
    if not parser.rows:
        raise RuntimeError(f"No table rows found in {path}")

    headers = parser.rows[0]
    h = {name: i for i, name in enumerate(headers)}

    def cell(row: list[str], name: str) -> str:
        return row[h[name]] if name in h and h[name] < len(row) else ""

    rows: list[CashRow] = []
    for idx, row in enumerate(parser.rows[1:]):
        rows.append(
            CashRow(
                index=idx,
                date=cell(row, "Дата"),
                kind=cell(row, "Тип"),
                description=cell(row, "Описание"),
                source=cell(row, "Источник"),
                project=cell(row, "Проект"),
                inflow=parse_decimal(cell(row, "Приток")),
                outflow=parse_decimal(cell(row, "Отток")),
                balance_after=parse_decimal(cell(row, "Остаток после операции")),
            )
        )
    return rows


def find_correction(rows: list[CashRow]) -> int:
    candidates = [
        i
        for i, row in enumerate(rows)
        if row.date == "2026-06-26"
        and "26.06.26" in row.description
        and row.inflow > 0
    ]
    if not candidates:
        raise RuntimeError("Could not find the 2026-06-26 correction row")
    return candidates[0]


def build_report(rows: list[CashRow], baseline: Decimal, actual_cash: Decimal) -> str:
    corr_idx = find_correction(rows)
    correction = rows[corr_idx]
    newer_rows_desc = rows[:corr_idx]
    newer_rows_chrono = list(reversed(newer_rows_desc))

    delta_at_control = baseline - correction.balance_after
    balance_before_correction = correction.balance_after - correction.net
    required_correction_net = baseline - balance_before_correction

    lines: list[str] = []
    lines.append("# Cash balance diagnostic after 2026-06-26 correction")
    lines.append("")
    lines.append(f"Export rows: {len(rows)}")
    lines.append(f"Control baseline entered manually: {money(baseline)} RSD")
    lines.append(
        f"Program balance after correction row: {money(correction.balance_after)} RSD"
    )
    lines.append(f"Delta at control point: {money(delta_at_control)} RSD")
    lines.append(
        f"Correction row amount now: {money(correction.net)} RSD; amount needed for {money(baseline)} RSD: {money(required_correction_net)} RSD"
    )
    lines.append("")
    lines.append("## Operations after correction")
    lines.append("")
    lines.append(
        "| Date | Type | Description / source | In | Out | Program balance | Balance from 9 090 | Difference |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|")

    running = baseline
    suspect_without = baseline
    for row in newer_rows_chrono:
        running += row.net
        is_food_receipt = "Sprite" in row.description or "Gurmanska" in row.description
        if not is_food_receipt:
            suspect_without += row.net
        desc = row.description
        if len(desc) > 80:
            desc = desc[:77] + "..."
        source = row.source if row.source and row.source != "—" else ""
        detail = desc if not source else f"{desc}<br>{source}"
        diff = running - row.balance_after
        lines.append(
            f"| {row.date} | {row.kind} | {detail} | {money(row.inflow)} | {money(row.outflow)} | {money(row.balance_after)} | {money(running)} | {money(diff)} |"
        )

    lines.append("")
    lines.append("## Totals")
    lines.append("")
    lines.append(f"Program current balance: {money(rows[0].balance_after)} RSD")
    lines.append(f"Balance from 9 090 with every post-correction row: {money(running)} RSD")
    lines.append(
        f"Balance from 9 090 without the 1 020 food receipt row: {money(suspect_without)} RSD"
    )
    lines.append(f"Physical cash provided by user: {money(actual_cash)} RSD")
    lines.append(f"Physical minus full replay: {money(actual_cash - running)} RSD")
    lines.append(f"Physical minus replay without food receipt: {money(actual_cash - suspect_without)} RSD")
    return "\n".join(lines) + "\n"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--baseline", type=Decimal, default=Decimal("9090"))
    parser.add_argument("--actual-cash", type=Decimal, default=Decimal("101090"))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    rows = read_cash_rows(args.export)
    report = build_report(rows, args.baseline, args.actual_cash)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(report)
    print(f"Report saved to: {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
