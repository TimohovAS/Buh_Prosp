"""Парсер банковских изводов (формат Alta Banka .xls)."""
from io import BytesIO
from typing import Any

import xlrd


def _parse_amount(s: Any) -> float:
    """5,122.16 или 120,000.00 -> float."""
    if not s or not str(s).strip():
        return 0.0
    s = str(s).replace(",", "").replace(" ", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_date(s: Any) -> str | None:
    """DD.MM.YYYY из строки с переносами -> YYYY-MM-DD."""
    if not s or not str(s).strip():
        return None
    for part in str(s).split("\n"):
        part = part.strip()
        if len(part) == 10 and part[2] == "." and part[5] == ".":
            try:
                d, m, y = map(int, part.split("."))
                return f"{y:04d}-{m:02d}-{d:02d}"
            except ValueError:
                pass
    return None


def parse_izvod_xls(content: bytes) -> list[dict]:
    """
    Парсинг извода банка (.xls).
    Возвращает список транзакций: {date, reference, description, payer_beneficiary, type, amount, debit, credit}.
    type: 'income' | 'expense'
    """
    wb = xlrd.open_workbook(file_contents=content)
    sh = wb.sheet_by_index(0)
    result = []

    for r in range(20, sh.nrows):
        c1 = sh.cell_value(r, 1)
        c2 = sh.cell_value(r, 2)
        c5 = sh.cell_value(r, 5)
        c9 = sh.cell_value(r, 9)
        c22 = sh.cell_value(r, 22)  # zaduženje (debit) — деньги уходят
        c26 = sh.cell_value(r, 26)  # odobrenje (credit) — деньги приходят

        if not c1 or not str(c1).strip():
            continue
        if "\n" not in str(c1) and not str(c1).replace(".", "").replace(",", "").replace(" ", "").isdigit():
            continue

        debit = _parse_amount(c22)
        credit = _parse_amount(c26)
        if debit <= 0 and credit <= 0:
            continue

        tx_type = "expense" if debit > 0 else "income"
        amount = debit if debit > 0 else credit

        date_val = _parse_date(c1)
        if not date_val:
            continue

        result.append({
            "date": date_val,
            "reference": str(c2).strip() if c2 else "",
            "description": (str(c5).strip() or "")[:500],
            "payer_beneficiary": (str(c9).replace("\n", " ").strip() or "")[:200],
            "type": tx_type,
            "amount": round(amount, 2),
            "debit": round(debit, 2),
            "credit": round(credit, 2),
        })

    return result
