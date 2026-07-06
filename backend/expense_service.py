"""Business helpers for expenses."""

from backend.decimal_utils import ZERO_DECIMAL, to_decimal
from backend.models import ExpenseItem


def _item_field(item, key: str):
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _to_optional_decimal(value):
    if value in (None, ""):
        return None
    return to_decimal(value)


def normalize_expense_items(items) -> list[dict]:
    normalized = []
    for item in items or []:
        name = str(_item_field(item, "name") or "").strip()
        quantity = _to_optional_decimal(_item_field(item, "quantity"))
        unit_price = _to_optional_decimal(_item_field(item, "unit_price"))
        note = str(_item_field(item, "note") or "").strip() or None
        amount_value = _item_field(item, "total_amount")
        if quantity is not None and unit_price is not None:
            amount = to_decimal(quantity * unit_price)
        else:
            amount = to_decimal(amount_value if amount_value not in (None, "") else ZERO_DECIMAL)

        has_payload = (
            bool(name) or quantity is not None or unit_price is not None or amount != ZERO_DECIMAL or bool(note)
        )
        if not has_payload:
            continue
        if not name:
            raise ValueError("Expense item name is required")

        normalized.append(
            {
                "name": name[:500],
                "quantity": quantity,
                "unit_price": unit_price,
                "total_amount": amount,
                "note": note,
            }
        )
    return normalized


def expense_amount_from_items(items: list[dict], fallback) -> object:
    if not items:
        return to_decimal(fallback or ZERO_DECIMAL)
    total = ZERO_DECIMAL
    for item in items:
        total += to_decimal(item["total_amount"] or ZERO_DECIMAL)
    return total


def expense_description_from_items(items: list[dict], fallback: str | None) -> str:
    text = str(fallback or "").strip()
    if text:
        return text[:500]
    if items:
        return "; ".join(item["name"] for item in items)[:500]
    return ""


def build_expense_item_models(items: list[dict]) -> list[ExpenseItem]:
    return [
        ExpenseItem(
            line_no=index + 1,
            name=item["name"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            total_amount=item["total_amount"],
            note=item["note"],
        )
        for index, item in enumerate(items)
    ]
