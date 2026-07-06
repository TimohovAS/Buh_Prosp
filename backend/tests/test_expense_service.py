from decimal import Decimal

import pytest

from backend.expense_service import (
    build_expense_item_models,
    expense_amount_from_items,
    expense_description_from_items,
    normalize_expense_items,
)


def test_normalize_expense_items_computes_total_from_quantity_and_unit_price():
    items = normalize_expense_items(
        [
            {
                "name": "Service",
                "quantity": Decimal("2"),
                "unit_price": Decimal("125.50"),
                "total_amount": Decimal("999.00"),
                "note": "  scheduled  ",
            }
        ]
    )

    assert items == [
        {
            "name": "Service",
            "quantity": Decimal("2"),
            "unit_price": Decimal("125.50"),
            "total_amount": Decimal("251.00"),
            "note": "scheduled",
        }
    ]
    assert expense_amount_from_items(items, Decimal("1.00")) == Decimal("251.00")
    assert expense_description_from_items(items, None) == "Service"

    models = build_expense_item_models(items)
    assert models[0].line_no == 1
    assert models[0].name == "Service"
    assert models[0].total_amount == Decimal("251.00")


def test_expense_item_helpers_use_fallbacks_without_items():
    assert normalize_expense_items([{}]) == []
    assert expense_amount_from_items([], Decimal("45.00")) == Decimal("45.00")
    assert expense_description_from_items([], " Manual description ") == "Manual description"


def test_normalize_expense_items_rejects_payload_without_name():
    with pytest.raises(ValueError, match="Expense item name is required"):
        normalize_expense_items([{"quantity": Decimal("1"), "unit_price": Decimal("10")}])
